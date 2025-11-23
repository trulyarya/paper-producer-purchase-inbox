"""
Container-app deployment helper.

Secure deployment workflow:
1. Collects secrets interactively from Airtable/Slack setup (never written to disk)
2. Uses Terraform outputs for Azure resource names
3. Stores secrets in Azure Container App secrets (encrypted at rest)
4. Handles Gmail credentials.json securely via Azure Storage mount
5. Assigns managed identity + RBAC roles

Usage: python deploy.py
"""

import os
import subprocess
import sys
from pathlib import Path
from loguru import logger

from scripts.airtable_setup import airtable_setup_flow
from scripts.slack_setup import slack_setup_flow


REPO_ROOT = Path(__file__).resolve().parent  # Base repo path
AZURE_INFRA_DIR = REPO_ROOT / "infra" / "azure"  # Terraform lives here
GCP_INFRA_DIR = REPO_ROOT / "infra" / "gcp"  # GCP Terraform lives here
CREDENTIALS_FILE = REPO_ROOT / "cred" / "credentials.json"  # Gmail OAuth credentials (local only)
TOKEN_FILE = REPO_ROOT / "cred" / "token.json"  # Gmail refresh token (must exist before deployment)


# Non-sensitive configuration (safe to pass as env vars):
#   Telemetry flags needed for monitoring and diagnostics
TELEMETRY_ENV_KEYS = [
    "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
    "ENABLE_TELEMETRY",
    "ENABLE_OTEL",
    "ENABLE_SENSITIVE_DATA",
]

# Sensitive secrets (must be stored in Container App secrets)
SENSITIVE_SECRET_KEYS = [
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "AIRTABLE_API_KEY",
    "AIRTABLE_BASE_ID",
    "SLACK_BOT_TOKEN",
    "SLACK_APPROVAL_CHANNEL",
    "GMAIL_CREDENTIALS_JSON",  # OAuth client credentials
    "GMAIL_TOKEN_JSON",  # OAuth refresh token (generated locally before deployment)
]

# Map Terraform output names to keys:
TERRAFORM_OUTPUT_KEYS = {
    "location": "LOCATION",  # Azure region slug
    "project_name": "PROJECT_NAME",  # Prefix for names (e.g., papco)
    "environment_name": "ENVIRONMENT",  # Suffix like dev/prod
    "resource_group_name": "RESOURCE_GROUP",  # Container App RG
    "azure_ai_services_endpoint": "AZURE_AI_SERVICES_ENDPOINT",  # Content safety endpoint
    "azure_openai_endpoint": "AZURE_OPENAI_ENDPOINT",  # Chat completions endpoint
    "azure_ai_project_endpoint": "AZURE_AI_PROJECT_ENDPOINT",  # Azure AI proj endpoint
    "search_service_endpoint": "SEARCH_ENDPOINT",  # Azure Cognitive Search endpoint
    "storage_account_url": "STORAGE_URL",  # Blob storage URL
    "storage_account_name": "STORAGE_NAME",  # Plain account name (handy for scripts)
    "invoices_container_name": "INVOICE_CONTAINER",  # Blob container storing invoices
    "azure_ai_services_resource_id": "AZURE_AI_RESOURCE_ID",  # RBAC scope for AI services
    "search_service_resource_id": "SEARCH_ID",  # RBAC scope for search
    "storage_account_resource_id": "STORAGE_ID",  # RBAC scope for storage
    "azure_openai_chat_deployment_name": "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME",  # GPT deployment name
    "azure_openai_embedding_deployment_name": "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME",  # Embedding deployment
    "applicationinsights_connection_string": "APPLICATIONINSIGHTS_CONNECTION_STRING",  # App Insights for telemetry
    "log_analytics_workspace_id": "LOG_ANALYTICS_WORKSPACE_ID",  # For Container Apps diagnostics
    "log_analytics_workspace_key": "LOG_ANALYTICS_WORKSPACE_KEY",  # For Container Apps diagnostics
    "acr_login_server": "ACR_LOGIN_SERVER",  # Azure Container Registry URL
    "acr_name": "ACR_NAME",  # ACR name for docker push
    "acr_resource_id": "ACR_RESOURCE_ID",  # RBAC scope for ACR
}

# Roles to assign to the Container App managed identity:
ROLE_ASSIGNMENTS = [
    # Azure OpenAI chat/embeddings (data-plane):
    ("Cognitive Services OpenAI Contributor", "AZURE_AI_RESOURCE_ID", "Azure AI chat/embeddings"),
    # Azure Content Safety data-plane (text:analyze, text:shieldPrompt):
    ("Cognitive Services User", "AZURE_AI_RESOURCE_ID", "Azure AI Content Safety"),
    # Azure AI Search data-plane (read/query and index + upload data for indexing):
    ("Search Index Data Contributor", "SEARCH_ID", "Search data"),
    # Azure AI Search control and data plane. Needed for creating indexes, skillsets, etc.:
    ("Search Service Contributor", "SEARCH_ID", "Search service management"),
    # Needed for invoice blobs:
    ("Storage Blob Data Contributor", "STORAGE_ID", "Storage account"),
    # ACR pull access for Container App managed identity:
    ("AcrPull", "ACR_RESOURCE_ID", "Container Registry"),
]

# Helper function to run shell commands with logging
def run_command(
        command: list[str],
        working_dir: Path | None = None,
        capture_output: bool = False
) -> str:
    """Execute shell command with logging.
    Args:
        command (list[str]): Command and arguments to run.
        working_dir (Path | None): Optional working directory.
        capture_output (bool): Whether to capture and return stdout.
    Returns:
        str: Captured stdout if requested, else empty string.
    """
    logger.info(f"$ {' '.join(command)}")
    result = subprocess.run(command, cwd=working_dir, check=True,
                            text=True, capture_output=capture_output)
    
    return result.stdout.strip() if capture_output else ""


# Helper function to log each step's header
def log_step(num: int, title: str) -> None:
    """Print formatted step header."""
    logger.info("="*60)
    logger.info(f"STEP {num}: {title}")
    logger.info("="*60)


# Helper function to check prerequisites, authenticate CLIs, & retrieve necessary values
def check_prerequisites() -> tuple[str, str, str]:
    """Verify required CLIs are installed and authenticated."""
    logger.info("Checking Azure CLI, Terraform, GCP CLI, and GitHub CLI...")
    
    # --- 1. Check for required CLIs ---
    for cli in ["az", "terraform", "gcloud", "gh"]:
        result = subprocess.run(
            f"command -v {cli}",
            shell=True,
            capture_output=True)
        
        if result.returncode != 0:
            logger.error(f"{cli} CLI not installed! Please install it first.")
            if cli == "gh":
                logger.info("Install GitHub CLI: https://cli.github.com/")
            sys.exit(1)
    
    # --- 2. Check Azure login and grab subscription ID (for TF var) ---
    az_subscription_id = subprocess.run([
        "az", "account", "show",
        "--query", "id", "-o", "tsv"
        ], capture_output=True, text=True)
    
    # --- 3. Get Azure account username (which should be the admin user email) ---
    az_email = subprocess.run([
        "az", "account", "show", 
        "--query", "user.name", "-o", "tsv"
        ], capture_output=True, text=True)

    if az_subscription_id.returncode != 0 or az_email.returncode != 0:
        logger.error(
        "Run 'az login' first and select the right subscription on Azure with admin rights..."
        )
        sys.exit(1)

    # --- 3b. Ensure the Container Apps CLI extension is present (needed for --registry-identity) ---
    try:
        logger.info("Ensuring Azure CLI containerapp extension is installed/up-to-date...")
        subprocess.run(
            ["az", "extension", "add", "--name", "containerapp", "--upgrade", "--yes"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.success("Azure CLI containerapp extension is installed/up-to-date.")

    except subprocess.CalledProcessError as exc:
        logger.error(f"Failed to install/upgrade containerapp extension "
                     "for Azure CLI: {exc.stderr or exc}")
        sys.exit(1)
    
    # Store values to pass as Terraform variables
    subscription_id_value = az_subscription_id.stdout.strip()
    admin_email_value = az_email.stdout.strip()
    
    logger.info(
        f"Retrieved subscription_id={subscription_id_value} "
        f"and admin_email={admin_email_value}"
    )
    
    # --- 4. Check GCP CLI application-default login ---
    result = subprocess.run([
        "gcloud", "auth", "application-default", "print-access-token"
        ], capture_output=True)
    if result.returncode != 0:
        logger.error("Run 'gcloud auth application-default login' first...")
        sys.exit(1)
    
    # --- 5. Check GitHub CLI authentication ---
    result = subprocess.run([
        "gh", "auth", "status"
        ], capture_output=True)
    if result.returncode != 0:
        logger.error("Run 'gh auth login' first to authenticate with GitHub...")
        sys.exit(1)
    
    # --- 6. Extract GitHub token for Terraform GitHub provider ---
    github_token = subprocess.run([
        "gh", "auth", "token"
        ], capture_output=True, text=True)
    if github_token.returncode != 0:
        logger.error("Failed to retrieve GitHub token from gh CLI")
        sys.exit(1)
    
    # Store github token value string to pass to Terraform
    github_token_value = github_token.stdout.strip()

    logger.success("Prerequisites OK")
    
    # Return values for use in Terraform commands
    return subscription_id_value, admin_email_value, github_token_value


# GitHub repo detection using `git remote` in github cli:
def detect_github_owner_repo(remote_name: str = "origin") -> tuple[str | None, str | None]:
    """Return (owner, repo) from the git remote URL."""
    remote_url = subprocess.run(
        ["git", "remote", "get-url", remote_name],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()  # git remote URL (empty if command fails)

    # Normalize the URL by removing the ".git" suffix and trailing slashes
    cleaned = remote_url.replace(".git", "").rstrip("/")  # normalize suffix
    
    # If not a GitHub URL, return None
    if "github.com" not in cleaned:
        return None, None
    
    # Exract owner/repo from URL by splitting after "github.com", then splitting on "/"
    tail = cleaned.split("github.com")[-1].lstrip(":/")

    # Split the owner/repo portion by "/"
    parts = tail.split("/", 1)
    
    # Success: We know it's valid if we have exactly 2 non-empty parts
    if len(parts) == 2 and all(parts):  # `all()` checks for non-empty strings
        return parts[0], parts[1]  # returning the owner and repo

    # Failure: If we reach here, parsing has failed!
    return None, None

# Let's set the GitHub owner and repo from the detected remote URL
GITHUB_OWNER, GITHUB_REPO = detect_github_owner_repo()

if GITHUB_OWNER and GITHUB_REPO:
    logger.info(f"Auto-detected GitHub repository from git remote 'origin': "
                f"{GITHUB_OWNER}/{GITHUB_REPO}")
else:
    logger.warning("GitHub repository not detected. Set them as "
                   "github_owner and github_repo manually in terraform.tfvars")


def main():
    """
    Entry point orchestrating the entire deployment flow:
    1. Load optional secrets from .env/environment.
    2. Deploy Azure infra + fetch outputs.
    3. Deploy GCP project for Gmail integration.
    4. Handle Gmail manual steps and validate local config.
    5. Run Airtable + Slack setup helpers (prompts if missing).
    6. Build/deploy Container App, then assign identity/RBAC.
    """
    logger.info("" + "-"*60)
    logger.info("     #### PaperCo O2C - Automated Deployment ####     ")
    logger.info("-"*60 + "\n")
    

    # ================ STEP 1: Validation & Prerequisites ===================
    log_step(1, "Validation & Prerequisites")
    subscription_id, admin_email, github_token = check_prerequisites()


    # ================ STEP 2: Initialize Secrets Collection ================
    log_step(2, "Initialize Secrets Collection")
    logger.info("Secrets collected from setup scripts (never written to disk)")
    collected_secrets = {}
    logger.success("Ready to collect secrets")


    # ================ STEP 3: Deploy Infrastructure & Fetch Outputs ========
    log_step(3, "Deploy Infrastructure & Fetch Outputs")
    logger.info("Deploying Azure AI services + ACR + GitHub OIDC identity with Terraform (~5-10 min)...")
    
    # Set GitHub token as environment variable for Terraform GitHub provider (if available)
    terraform_env_var = os.environ.copy()
    
    if github_token:
        terraform_env_var["GITHUB_TOKEN"] = github_token
        logger.info("GitHub token found - secrets will be auto-created")
    else:
        logger.warning("No GitHub token - you'll need to create secrets manually later")
    
    # Note: Terraform needs init before output
    run_command(["terraform", "init", "-upgrade"], working_dir=AZURE_INFRA_DIR)
    
    # Build the Terraform apply command, including GitHub vars if detected
    terraform_apply_cmd = [
        "terraform", "apply", "-auto-approve",
        "-var", f"subscription_id={subscription_id}",
        "-var", f"admin_email={admin_email}"
    ]
    
    # Add GitHub owner/repo if detected
    if GITHUB_OWNER and GITHUB_REPO:
        terraform_apply_cmd.extend([
            "-var", f"github_owner={GITHUB_OWNER}",
            "-var", f"github_repo={GITHUB_REPO}"
        ])
        logger.info(f"Configuring GitHub Actions for {GITHUB_OWNER}/{GITHUB_REPO}")
    else:
        logger.warning("GitHub repo not detected - GitHub Actions OIDC will need manual configuration! You should set 'github_owner' and 'github_repo' in `terraform.tfvars`")
    
    # Run Terraform with GitHub token in environment (if available)
    subprocess.run(
        terraform_apply_cmd,
        cwd=AZURE_INFRA_DIR,
        env=terraform_env_var,
        check=True
    )
    
    logger.success("Azure AI services + ACR + GitHub Actions identity deployed")
    if github_token:
        logger.info("GitHub secrets automatically written to repository!")
    else:
        logger.warning("GitHub secrets NOT created (gh CLI not authenticated). Create manually or run: gh auth login")
    
    logger.info("Reading Terraform outputs...")
    terraform_outputs = {
        python_key: run_command(["terraform", "output", "-raw", tf_key], AZURE_INFRA_DIR, capture_output=True)
        for tf_key, python_key in TERRAFORM_OUTPUT_KEYS.items()
    }
    logger.success(f"Retrieved {len(terraform_outputs)} Terraform outputs")
    logger.info("ACR and GitHub Actions identity configured successfully!")
    
    # Store Application Insights connection string as secret
    collected_secrets["APPLICATIONINSIGHTS_CONNECTION_STRING"] = terraform_outputs["APPLICATIONINSIGHTS_CONNECTION_STRING"]


    # ================ STEP 4: Deploy GCP Infrastructure ====================
    log_step(4, "Deploy GCP Infrastructure")
    logger.info("Deploying GCP project (3 min)...")
    logger.info(
        "\nReminder (manual requirement by Google):\n"
        "  - You'll still need to configure the OAuth consent screen, and\n"
        "  - create the Desktop OAuth client after this.\n"
        "Terraform only creates the Google project, and enables the Gmail API.\n"
    )

    run_command(["terraform", "init", "-upgrade"], working_dir=GCP_INFRA_DIR)
    run_command(["terraform", "apply", "-auto-approve"], working_dir=GCP_INFRA_DIR)
    
    logger.success("GCP deployed")
  

    # ================ STEP 5: Manual Gmail OAuth Setup =====================
    log_step(5, "Manual Gmail OAuth Setup")
    logger.info("Manual step required:")
    
    manual_instructions = run_command(
        ["terraform", "output", "manual_setup_instructions"],
        working_dir=GCP_INFRA_DIR,
        capture_output=True
    )
    
    logger.info(manual_instructions)
    input("\nComplete Gmail OAuth setup above, then press Enter when you're ready to continue...")


    # ================ STEP 6: Validate Configuration Files =================   
    log_step(6, "Validate Configuration Files")
    logger.info("Validating credentials.json and token.json...")

    # Check for OAuth client credentials file
    if not CREDENTIALS_FILE.exists():
        logger.error("cred/credentials.json not found! Download from GCP Console")
        sys.exit(1)
    
    # Check for OAuth token file (contains refresh_token for unattended access)
    if not TOKEN_FILE.exists():
        logger.warning("token.json not found - Gmail authentication required")
        logger.info("\nGmail OAuth needs browser interaction (impossible in containers).")
        logger.info("Running authentication helper to generate token.json...\n")
        
        # Run the authentication helper script
        try:
            run_command(["python", "scripts/authenticate_gmail.py"], working_dir=REPO_ROOT)
        except subprocess.CalledProcessError:
            logger.error("Authentication failed. Please resolve issues and try again.")
            sys.exit(1)
        
        # Verify token was created
        if not TOKEN_FILE.exists():
            logger.error("Authentication completed but token.json not found")
            sys.exit(1)
        else:
            logger.success("`token.json` created successfully by gmail authentication helper.")

    logger.success("Configuration files found!")


    # ================ STEP 7: Setup Airtable Base & Data ===================
    log_step(7, "Setup Airtable Base & Data")
    logger.info("Setting up a new Airtable base, creating tables, and uploading sample CSV data...\n")
    logger.info(
        "\nNOTE:\n"
        "   1. Create a free Airtable account if you don't have one: https://airtable.com\n"
        "   2. Create a personal access token: https://airtable.com/create/tokens\n"
        "      - Recommended scopes: data.records:read, data.records:write, "
        "schema.bases:read, schema.bases:write\n"
        "   3. You will be prompted to paste your API token, which is saved automatically afterwards.\n"
        "   4. Find your Airtable workspace ID in the workspace URL: "
        "https://airtable.com/workspaces/<wsps...> where you'll be asked to enter it for saving as well.\n"
    )

    input("\nPress Enter when ready to continue...")
    airtable_secrets = airtable_setup_flow()
    if airtable_secrets:
        collected_secrets.update(airtable_secrets)
        logger.info(f"Collected {len(airtable_secrets)} Airtable secrets")
    

    # ================ STEP 8: Setup Slack ==================================
    log_step(8, "Setup Slack")
    logger.info("Setting up Slack bot token and approval channel...\n")
    logger.info(
        "\nNOTE:\n"
        "Make sure to set up a free Slack account and create a Slack App with a bot user:\n"
        "   1. Visit https://api.slack.com/apps → Create New App → From scratch\n"
        "   2. Go to OAuth & Permissions → Bot Token Scopes → add:\n"
        "      - chat:write\n"
        "      - channels:history\n"
        "      - channels:read\n"
        "      - groups:read\n"
        "   3. Click 'Install to Workspace' at top of OAuth page\n"
        "   4. Copy Bot User OAuth Token (xoxb-...)\n"
        "   5. Create channel (e.g., #orders) and invite bot to it\n"
        "   6. Paste the bot token and channel name when prompted in Terminal...\n"
    )
    
    input("\nPress Enter when ready to continue...")
    slack_secrets = slack_setup_flow()
    if slack_secrets:
        collected_secrets.update(slack_secrets)
        logger.info(f"Collected {len(slack_secrets)} Slack secrets")


    # ================ STEP 9: Build, Push & Deploy Container App ===========
    log_step(9, "Build, Push & Deploy Container App")
    
    project_name, environment = terraform_outputs['PROJECT_NAME'], terraform_outputs['ENVIRONMENT']
    resource_group, location = terraform_outputs['RESOURCE_GROUP'], terraform_outputs['LOCATION']
    app_name, container_environment = f"{project_name}-{environment}-app", f"{project_name}-{environment}-env"
    acr_login_server = terraform_outputs['ACR_LOGIN_SERVER']

    logger.info("Deploying Container App with ACR integration...")
    logger.info(f"Container registry: {acr_login_server}")
    
    public_env_vars = {
        "AZURE_OPENAI_ENDPOINT": terraform_outputs["AZURE_OPENAI_ENDPOINT"],
        "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME": terraform_outputs["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME": terraform_outputs["AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"],
        "AZURE_SEARCH_ENDPOINT": terraform_outputs["SEARCH_ENDPOINT"],
        "AZURE_STORAGE_ACCOUNT_URL": terraform_outputs["STORAGE_URL"],
        "AZURE_INVOICE_CONTAINER": terraform_outputs["INVOICE_CONTAINER"],
        "AZURE_AI_PROJECT_ENDPOINT": terraform_outputs["AZURE_AI_PROJECT_ENDPOINT"],
        "CONTENT_SAFETY_ENDPOINT": terraform_outputs["AZURE_AI_SERVICES_ENDPOINT"],
        **{key: "true" for key in TELEMETRY_ENV_KEYS}, # Enable telemetry flags
    }
    
    env_var_args = [f"{key}={value}" for key, value in public_env_vars.items()]
    
    # Use ACR with managed identity (--registry-identity system)
    run_command([
        "az", "containerapp", "up",
        "--name", app_name,
        "--resource-group", resource_group,
        "--location", location,
        "--environment", container_environment,
        "--logs-workspace-id", terraform_outputs["LOG_ANALYTICS_WORKSPACE_ID"],
        "--logs-workspace-key", terraform_outputs["LOG_ANALYTICS_WORKSPACE_KEY"],
        "--source", ".",
        "--ingress", "internal",
        "--revisions-mode", "single",  # only one active revision at a time
        "--registry-server", acr_login_server,
        "--registry-identity", "system",  # use managed identity instead of username/password
        "--env-vars", *env_var_args,
    ], working_dir=REPO_ROOT)
    
    # Set scale and ACR auth via dedicated commands for better CLI compatibility
    # (These two commands could be combined but need a preview extension installed in azure cli.)
    run_command([
        "az", "containerapp", "update",
        "--name", app_name,
        "--resource-group", resource_group,
        "--revisions-mode", "single",  # only one active revision at a time
        "--min-replicas", "0",
        "--max-replicas", "1",
    ], working_dir=REPO_ROOT)
    
    logger.success("Container App deployed!")
    
    logger.info("\nLoading Gmail credentials and token...")
    collected_secrets["GMAIL_CREDENTIALS_JSON"] = CREDENTIALS_FILE.read_text()
    collected_secrets["GMAIL_TOKEN_JSON"] = TOKEN_FILE.read_text()
    logger.success(
        "Gmail credentials and token JSON files ready for encrypted storage...")
    
    logger.info("\nStoring secrets in Container App (encrypted at rest)...")
    
    secret_args = []
    for key in SENSITIVE_SECRET_KEYS:
        value = collected_secrets.get(key)
        if value:
            # Container Apps expects secret names kebab-cased, values stay as-is
            secret_name = key.lower().replace("_", "-")
            secret_args.append(f"{secret_name}={value}")
    
    if secret_args:
        run_command([
            "az", "containerapp", "secret", "set",
            "--name", app_name,
            "--resource-group", resource_group,
            "--secrets", *secret_args,
        ])
        logger.success(f"Stored {len(secret_args)} secrets securely")
    
    logger.info("\nConfiguring secret references...")
    
    secret_env_vars = [
        f"{key}=secretref:{key.lower().replace('_', '-')}"
        for key in SENSITIVE_SECRET_KEYS if collected_secrets.get(key)
    ]
    
    if secret_env_vars:
        # Update the container app to add secret references
        run_command([
            "az", "containerapp", "update",
            "--name", app_name,
            "--resource-group", resource_group,
            "--set-env-vars", *secret_env_vars,
        ])
        logger.success("Container configured to access secrets")
    
    logger.success("\nSecure deployment complete!")
    logger.info("Secrets are encrypted at rest and not visible in Azure Portal")


    # ================ STEP 10: Enable Managed Identity =====================   
    log_step(10, "Enable Managed Identity")
    logger.info(f"Enabling managed identity for {app_name}...")
    run_command([
        "az", "containerapp", "identity", "assign",
        "--name", app_name,
        "--resource-group", resource_group,
        "--system-assigned",
    ])  # Enable built-in managed identity on the container app

    managed_identity_principal_id = run_command([  # Ask Azure what principal ID was created
        "az", "containerapp", "show",
        "--name", app_name,
        "--resource-group", resource_group,
        "--query", "identity.principalId",
        "-o", "tsv",
    ], capture_output=True)

    if not managed_identity_principal_id:
        logger.error("Failed to read managed identity principal ID.")
        sys.exit(1)


    # ================ STEP 11: Grant RBAC Roles ============================
    log_step(11, "Grant RBAC Roles")
    logger.info("Granting Azure resource access...")
    
    for role_name, scope_key, service_description in ROLE_ASSIGNMENTS:
        rbac_scope = terraform_outputs[scope_key]  # Grab resource ID for RBAC scope
        try:
            run_command([
                "az", "role", "assignment", "create",
                "--assignee-object-id", managed_identity_principal_id,
                "--assignee-principal-type", "ServicePrincipal",
                "--role", role_name,
                "--scope", rbac_scope,
            ])
        except subprocess.CalledProcessError as exc:
            # Allow idempotent "already exists" conflicts, fail fast otherwise.
            err_text = getattr(exc, "stderr", "") or ""

            if "RoleAssignmentExists" in err_text or "already exists" in err_text:
                logger.warning(f"{role_name} already assigned for {service_description}.")
            else:
                logger.error(f"Failed to assign {role_name} for {service_description}: {err_text}")
                raise

    # Double-check all required roles are present for the current principal
    for role_name, scope_key, service_description in ROLE_ASSIGNMENTS:
        rbac_scope = terraform_outputs[scope_key]
        
        # Check assigned roles for the managed identity principal
        assigned = run_command([
            "az", "role", "assignment", "list",
            "--assignee-object-id", managed_identity_principal_id,
            "--scope", rbac_scope,
            "--query", "[].roleDefinitionName",
            "-o", "tsv",
        ], capture_output=True).splitlines()
        
        if role_name not in assigned:
            logger.error(f"Missing role {role_name} on {service_description} "
                         f"for principal {managed_identity_principal_id}")
            sys.exit(1)
    
    logger.success("Container App roles assigned!")


    # ================ STEP 12: Activate Managed Identity by Restarting last revision =====
    log_step(12, "Activate Managed Identity")
    
    latest_revision = run_command([
        "az", "containerapp", "show", "--name", app_name, "--resource-group", resource_group,
        "--query", "properties.latestRevisionName", "-o", "tsv"
    ], capture_output=True)

    if latest_revision:
        logger.info(f"Restarting revision {latest_revision}...")
        run_command(["az", "containerapp", "revision", "restart",
                    "--name", app_name, "--resource-group", resource_group, "--revision", latest_revision])
        logger.success("Revision restarted with managed identity")
    else:
        logger.warning("Could not determine latest revision; restart manually")


    # ================ DEPLOYMENT COMPLETE! ================================
    logger.success("-"*60)
    logger.success("Deployment Complete!")
    logger.success("-"*60)
    logger.info("Next steps:")
    logger.info(f"  View app:   az containerapp show -n {app_name} -g {resource_group}")
    logger.info(f"  Check logs: az containerapp logs show -n {app_name} -g {resource_group} --follow")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with exit code {e.returncode}")
        sys.exit(e.returncode)
