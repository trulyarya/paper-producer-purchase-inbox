"""Tear down Azure + GCP infra in one go, as simply as possible."""
import subprocess
from pathlib import Path
import sys
from loguru import logger


REPO_ROOT = Path(__file__).resolve().parent
AZURE_INFRA_DIR = REPO_ROOT / "infra" / "azure"
GCP_INFRA_DIR = REPO_ROOT / "infra" / "gcp"


def run_command(command: list[str], working_dir: Path | None = None) -> None:
    """Run a shell command with logging."""
    logger.info("$ " + " ".join(command))
    subprocess.run(command, cwd=working_dir, check=True)


def read_tfvar_value(tfvars_path: Path, key: str) -> str:
    """Tiny helper to pull key=value from terraform.tfvars without extra deps."""
    if not tfvars_path.exists():
        return ""
    for raw in tfvars_path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        lhs, rhs = line.split("=", 1)
        if lhs.strip() == key:
            return rhs.strip().strip('"')
    return ""


def main() -> None:
    """Main cleanup flow."""
    logger.info("-" * 60)
    logger.info("PaperCo O2C - DESTROY ALL RESOURCES")
    logger.info("-" * 60)
    logger.warning("This will delete Azure and GCP infrastructure created by Terraform!\n")

    confirmation = input("Type 'destroy' to confirm: ").strip().lower()
    if confirmation != "destroy":
        logger.info("Aborted by user.")
        return

    logger.info("Confirmation received. Starting cleanup...\n")

    if subprocess.run(["which", "terraform"], capture_output=True).returncode != 0:
        logger.error("terraform not found in PATH.")
        sys.exit(1)
    

    # -----------------------------------
    # ---------- Azure destroy ----------
    # -----------------------------------
    logger.info("=== [1/2] Destroying Azure infrastructure... ===")
    
    azure_state = AZURE_INFRA_DIR / "terraform.tfstate"
    if azure_state.exists():
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

        run_command(["terraform", "init", "-upgrade"], working_dir=AZURE_INFRA_DIR)
        run_command(
            [
                "terraform",
                "destroy",
                "-auto-approve",
                "-var",
                f"subscription_id={subscription_id}",
                "-var",
                f"admin_email={admin_email}",
            ],
            working_dir=AZURE_INFRA_DIR,
        )

        logger.success("Azure infrastructure destroyed!")
    else:
        logger.info("Skipping Azure: no terraform.tfstate found.")

    logger.info("")


    # -----------------------------------
    # ---------- GCP destroy ------------
    # -----------------------------------
    logger.info("=== [2/2] Destroying GCP project... ===")
    
    project_id = read_tfvar_value(GCP_INFRA_DIR / "terraform.tfvars", "project_id")
    gcp_state = GCP_INFRA_DIR / "terraform.tfstate"
    
    if gcp_state.exists():
        run_command(["terraform", "init", "-upgrade"], working_dir=GCP_INFRA_DIR)
        run_command(["terraform", "destroy", "-auto-approve"], working_dir=GCP_INFRA_DIR)
        logger.success("GCP resources destroyed via Terraform.")
    else:
        logger.info("Skipping Terraform GCP destroy: no terraform.tfstate found.")

    if project_id:
        run_command(["gcloud", "projects", "delete", project_id, "--quiet"])
        logger.success(f"GCP project '{project_id}' deleted via gcloud.")
    else:
        logger.info("No project_id found in terraform.tfvars; skipping gcloud delete.")

    logger.success("Cleanup complete!")
    logger.info("To redeploy: run `python deploy.py`")


if __name__ == "__main__":
    main()
