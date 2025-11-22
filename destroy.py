"""
Tear down all infrastructure (Azure + GCP) in a single go.

The script mirrors the old cleanup.sh flow but keeps things readable and safe:
1) Asks for a clear "destroy" confirmation.
2) Auto-fetches the Azure subscription ID and admin email (so Terraform will not prompt).
3) Runs `terraform destroy -auto-approve` for Azure and GCP if state files exist.
"""

import subprocess
from pathlib import Path
import sys
from loguru import logger


REPO_ROOT = Path(__file__).resolve().parent
AZURE_INFRA_DIR = REPO_ROOT / "infra" / "azure"
GCP_INFRA_DIR = REPO_ROOT / "infra" / "gcp"


def run_command(
        command: list[str],
        working_dir: Path | None = None) -> None:
    """Execute shell command with logging; re-raises on failure.
    Args:
        command: List of command parts (executable + args).
        working_dir: Optional working directory to run the command in.
    """
    logger.info("$ " + " ".join(command))
    subprocess.run(command, cwd=working_dir, check=True)


def main() -> None:
    """Main cleanup flow kept simple and beginner-friendly."""
    logger.info("-" * 60)
    logger.info("PaperCo O2C - DESTROY ALL RESOURCES")
    logger.info("-" * 60)
    logger.warning(
        "This will delete Azure and GCP infrastructure created by Terraform!\n")

    confirmation = input("Type 'destroy' to confirm: ").strip().lower()
    if confirmation != "destroy":
        logger.info("Aborted by user.")
        return

    logger.info("Confirmation received. Starting cleanup...\n")

    # Quick tooling checks before we kick off.
    for cli, hint in [(
        "terraform", "Install: https://developer.hashicorp.com/terraform/install"
    )]:
        if subprocess.run(["which", cli], capture_output=True).returncode != 0:
            logger.error(f"{cli} not found in PATH. {hint}")
            sys.exit(1)
    

    # -----------------------------------
    # ---------- Azure destroy ----------
    # -----------------------------------
    logger.info("=== [1/2] Destroying Azure infrastructure... ===")
    
    azure_state = AZURE_INFRA_DIR / "terraform.tfstate"
    if azure_state.exists():
        if subprocess.run(["which", "az"], capture_output=True).returncode != 0:
            logger.error("Azure CLI not found. Install: "
                         "https://learn.microsoft.com/cli/azure/install-azure-cli")
            sys.exit(1)

        try:
            subscription_id = subprocess.run(
                ["az", "account", "show", "--query", "id", "-o", "tsv"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            
            admin_email = subprocess.run(
                ["az", "account", "show", "--query", "user.name", "-o", "tsv"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            
            logger.success("Azure context OK "
                           f"(subscription={subscription_id}, admin={admin_email})")
        
        except subprocess.CalledProcessError:
            logger.error("Azure CLI not logged in. Run 'az login' "
                         "and pick the right subscription.")
            sys.exit(1)

        destroy_cmd = [
            "terraform", "destroy", "-auto-approve",
            "-var", f"subscription_id={subscription_id}",
            "-var", f"admin_email={admin_email}",
        ]

        try:
            run_command(
                ["terraform", "init", "-upgrade"],
                working_dir=AZURE_INFRA_DIR)
            
            run_command(
                destroy_cmd,
                working_dir=AZURE_INFRA_DIR)
            
            logger.success("Azure infrastructure destroyed!")
        
        except subprocess.CalledProcessError as exc:
            logger.warning(f"Azure destroy failed (exit code {exc.returncode}). "
                           "Check logs and continue.")
    
    else:
        logger.warning("Skipping Azure: no terraform.tfstate found!")

    logger.info("")


    # -----------------------------------
    # ---------- GCP destroy ------------
    # -----------------------------------
    logger.info("=== [2/2] Destroying GCP project... ===")
    
    gcp_state = GCP_INFRA_DIR / "terraform.tfstate"
    
    if gcp_state.exists():
        try:
            run_command(
                ["terraform", "init", "-upgrade"],
                working_dir=GCP_INFRA_DIR)
            
            run_command(
                ["terraform", "destroy", "-auto-approve"],
                working_dir=GCP_INFRA_DIR)
            
            logger.success("GCP project destroyed!")
        
        except subprocess.CalledProcessError as exc:
            logger.warning(f"GCP destroy failed (exit code {exc.returncode}). "
                           "Check logs and continue.")

    else:
        logger.warning("Skipping GCP: no terraform.tfstate found!")

    logger.success("Cleanup complete!")
    logger.info("To redeploy: run `python deploy.py`")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Cleanup interrupted by user!")
