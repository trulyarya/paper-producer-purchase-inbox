# ============================================================================
# VARIABLES FILE - Input parameters for your deployment
# ============================================================================
# This file defines all variables that can be customized when deploying


# -----------------------------------------------------------------------------
# REQUIRED PARAMETERS - You must provide these values
# -----------------------------------------------------------------------------

variable "subscription_id" {
  description = "Azure subscription ID where resources will be deployed"
  type        = string
}

variable "resource_group_name" {
  description = "Name of resource group to create (must be unique in subscription)"
  type        = string
}

variable "project_name" {
  description = "The main identifier for all resources e.g. 'paperco' or 'o2cdemo'"
  type        = string
  validation {
    condition     = length(var.project_name) >= 3 && length(var.project_name) <= 10
    error_message = "Project name must be between 3 and 10 characters."
  }
}

variable "location" {
  description = "Azure region where resources will be deployed e.g. 'swedencentral'"
  type        = string
}

variable "environment_name" {
  description = "Environment name (dev, test, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment_name)
    error_message = "Environment name must be one of: dev, test, prod."
  }
  default = "dev"
}

variable "admin_email" {
  description = "Your email address for notifications and resource tagging"
  type        = string
}


# -----------------------------------------------------------------------------
# OPTIONAL PARAMETERS - You CAN provide these values in terraform.tfvars
# -----------------------------------------------------------------------------

variable "developer_object_id" {
  description = <<-DESC
Azure AD Object ID of user/service principal for local development access (optional).
Get via: az ad signed-in-user show --query id -o tsv
DESC
  type        = string
  default     = ""
}

variable "github_owner" {
  description = <<-DESC
GitHub repository owner (username or organization).
Leave empty to auto-detect from GITHUB_REPOSITORY environment variable.
DESC
  type        = string
  default     = null
}

variable "github_repo" {
  description = <<-DESC
GitHub repository name (without owner prefix).
Leave empty to auto-detect from GITHUB_REPOSITORY environment variable.
DESC
  type        = string
  default     = null
}
