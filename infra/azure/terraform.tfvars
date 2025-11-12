# ============================================================================
# TERRAFORM VARIABLES FILE - Values for your deployment
# ============================================================================
# This file contains the actual values you'll use when deploying
# Fill in your details below

# Azure subscription ID (get via: az account show --query id -o tsv)
subscription_id = "YOUR_SUBSCRIPTION_ID_HERE"

# Resource group name (will be created if it doesn't exist)
resource_group_name = "paperco-o2c-rg"

# Your project identifier (3-10 characters, lowercase letters/numbers)
# Example: 'paperco' or 'o2cdemo'
project_name = "papierdemo"

# Azure region where everything will be deployed
# Common options: 'eastus', 'eastus2', 'westus2', 'westeurope', 'swedencentral'
location = "swedencentral"

# Environment: dev, test, or prod
environment_name = "dev"

# Your email for tagging resources
admin_email = "FILL_IN_YOUR_EMAIL_HERE"

# Optional: Azure AD Object ID for local development access
# Get via: az ad signed-in-user show --query id -o tsv
developer_object_id = ""
