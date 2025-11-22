# ============================================================================
# TERRAFORM VARIABLES FILE - Values for your deployment
# ============================================================================
# HOW IT WORKS:
#   1. deploy.py passes subscription_id and admin_email via -var flags
#   2. Terraform creates AI services (OpenAI, Search, Storage)
#   3. az containerapp up creates Container Apps infrastructure and deploys app
#   4. GitHub Actions handles ongoing deployments (push to main = new image)
#
# NOTE: subscription_id and admin_email are injected by deploy.py at runtime

# Resource group name (will be created if it doesn't exist)
resource_group_name = "paperco-o2c-resource-group"

# Your project identifier (3-10 characters, lowercase letters/numbers)
# Example: 'paperco' or 'o2cdemo'
project_name = "papierdemo"

# Azure region where everything will be deployed
# Common options: 'eastus', 'eastus2', 'westus2', 'westeurope', 'swedencentral'
location = "swedencentral"

# Environment: dev, test, or prod
environment_name = "dev"

# Optional: Azure AD Object ID for local development access
# Get via: az ad signed-in-user show --query id -o tsv
developer_object_id = ""

# GitHub repository details for CI/CD automation
# Leave empty - these will be auto-detected from your current repository
# during deployment (via GITHUB_REPOSITORY environment variable)
github_owner = ""
github_repo  = ""
