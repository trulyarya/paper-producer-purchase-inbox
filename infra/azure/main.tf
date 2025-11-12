# ============================================================================
# MAIN TERRAFORM FILE - Order-to-Cash Email Intake Demo
# ============================================================================
# This is the entry point that orchestrates all Azure resources needed

terraform {
  required_version = ">= 1.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.0"
    }
  }
}

# AzureRM is the main Azure provider
provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
  }
  subscription_id = var.subscription_id
}

# AzAPI provider for resources not yet in azurerm e.g. Cognitive Projects
provider "azapi" {
  subscription_id = var.subscription_id
}


# ----------------------------------------------------------------------------
# DATA SOURCES - Reference existing Azure context
# ----------------------------------------------------------------------------

# Get info about the current Azure client (subscription ID, tenant ID, etc.)
data "azurerm_client_config" "current" {}


# ----------------------------------------------------------------------------
# VARIABLES - Computed values used throughout the deployment
# ----------------------------------------------------------------------------

# Create consistent naming for all resources (locals means "local variables")
locals {
  unique_suffix  = substr(md5(var.resource_group_name), 0, 8) # Generates a unique hash from resource group name (always same for same RG)
  resource_prefix = "${var.project_name}-${var.environment_name}" # Combines project name and environment (e.g., "paperco-dev")

  # Built-in Azure role definition IDs (these are constant across all Azure subscriptions)
  # visit https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles for more info on built-in roles & GUIDs.
  storage_blob_data_contributor_role_id = "ba92f5b4-2d11-453d-a403-e96b0029c9fe" # Allows read/write/delete access to blob containers & data
  azure_ai_user_role_id                = "b24988ac-6180-42a0-ab88-20f7382dd24c" # Azure AI User role (for AI Search to call AI Foundry/OpenAI)

  # RESOURCE NAMES:
  
  # Storage name to be lowercase, no hyphens, max 24 chars
  storage_account_name    = lower(replace("${var.project_name}${var.environment_name}${local.unique_suffix}", "-", ""))
  search_service_name     = "${local.resource_prefix}-search-${local.unique_suffix}" # Example: paperco-dev-search-abc123xyz
  container_app_env_name  = "${local.resource_prefix}-cae-${local.unique_suffix}" # CAE = Container Apps Environment
  log_analytics_name      = "${local.resource_prefix}-logs-${local.unique_suffix}" # For monitoring and diagnostics
  app_insights_name       = "${local.resource_prefix}-ai-${local.unique_suffix}" # Application Insights for monitoring
  ai_account_name         = lower("${local.resource_prefix}-aoai-${substr(local.unique_suffix, 0, 8)}") # Azure AI Foundry account name
  ai_project_name         = lower("${local.resource_prefix}-project") # Azure AI Foundry project name
  project_display_name    = "${local.resource_prefix} project" # Friendly project display name
  project_description     = "Azure AI project for ${local.resource_prefix}" # Simple description for the project
  account_sku_name        = "S0" # Default SKU for Azure AI Foundry accounts
  deployment_sku_name     = "Standard" # Default deployment SKU name
  deployment_sku_capacity = 50 # Default deployment capacity

  # Tags for resource organization
  common_tags = { # Applied to all resources for tracking and management
    Project     = "O2C-Email-Intake" # Project identifier
    Environment = var.environment_name # dev, test, or prod
    ManagedBy   = "Terraform" # Indicates this was deployed via IaC
    Owner       = var.admin_email # Who to contact about these resources
  }
}


# ----------------------------------------------------------------------------
# RESOURCE GROUP
# ----------------------------------------------------------------------------

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags
}


# ----------------------------------------------------------------------------
# MODULE 1a: Log Analytics Workspace (needed for Container Apps)
# ----------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "main" {
  name                = local.log_analytics_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
  sku                 = "PerGB2018" # Pay-as-you-go per GB ingested
  retention_in_days   = 30 # Keep logs for 30 days (can be up to 730)
}


# ----------------------------------------------------------------------------
# MODULE 1b: Application Insights (for application monitoring)
# ----------------------------------------------------------------------------

resource "azurerm_application_insights" "main" {
  name                = local.app_insights_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.main.id
}


# ----------------------------------------------------------------------------
# MODULE 2: Storage Account (for invoice PDFs)
# ----------------------------------------------------------------------------

resource "azurerm_storage_account" "main" {
  name                            = local.storage_account_name
  location                        = azurerm_resource_group.main.location
  resource_group_name             = azurerm_resource_group.main.name
  tags                            = local.common_tags
  account_kind                    = "StorageV2" # General purpose v2 (modern, recommended type)
  account_tier                    = "Standard" # Standard or Premium
  account_replication_type        = "LRS" # Locally Redundant Storage (cheapest option)
  min_tls_version                 = "TLS1_2" # Security: minimum TLS version
  https_traffic_only_enabled      = true # Security: force HTTPS
  allow_nested_items_to_be_public = true # Enable blob-level public access (required for anonymous blob access)
  access_tier                     = "Hot" # Optimized for frequent access (vs 'Cool' for archival)
}

# Create blob container for invoices
resource "azurerm_storage_container" "invoices" {
  name                  = "invoices"
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "blob" # Allow anonymous read access to individual blobs (but not container listing)
}


# ----------------------------------------------------------------------------
# MODULE 3: Azure AI Foundry project (OpenAI account + GPT deployments)
# ----------------------------------------------------------------------------

# Azure AI Foundry account (unified AI Services endpoint)
resource "azurerm_cognitive_account" "main" {
  name                          = local.ai_account_name
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  kind                          = "AIServices"
  sku_name                      = local.account_sku_name
  custom_subdomain_name         = local.ai_account_name
  public_network_access_enabled = true

  identity {
    type = "SystemAssigned"
  }

  tags = merge(
    local.common_tags,
    {
      Type = "AIServices"
    }
  )
}

# Project (child of the account), NOT a hub
resource "azapi_resource" "project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = local.ai_project_name
  parent_id = azurerm_cognitive_account.main.id
  location  = azurerm_resource_group.main.location

  identity {
    type = "SystemAssigned" # Needed for AML workspace provisioning behind the project
  }

  body = jsonencode({
    properties = {
      displayName = local.project_display_name
      description = local.project_description
    }
  })

  tags = local.common_tags
}

# GPT-4.1 deployment (latest version with DataZoneStandard SKU)
resource "azurerm_cognitive_deployment" "gpt4_1" {
  name                 = "gpt-4.1"
  cognitive_account_id = azurerm_cognitive_account.main.id

  model {
    format  = "OpenAI"
    name    = "gpt-4.1"
    version = "2025-08-07"
  }

  sku {
    name     = "DataZoneStandard"
    capacity = local.deployment_sku_capacity
  }

  depends_on = [
    azapi_resource.project
  ]
}

# Deployment 2: text-embedding-3-large
# Text embedding deployment (for semantic search and vector operations)
resource "azurerm_cognitive_deployment" "embedding" {
  name                 = "text-embedding-3-large"
  cognitive_account_id = azurerm_cognitive_account.main.id

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-large"
    version = "1"
  }

  sku {
    name     = local.deployment_sku_name
    capacity = local.deployment_sku_capacity
  }

  depends_on = [
    azurerm_cognitive_deployment.gpt4_1
  ]
}


# ----------------------------------------------------------------------------
# MODULE 4: Azure AI Search (for SKU vector search)
# ----------------------------------------------------------------------------

resource "azurerm_search_service" "main" {
  name                          = local.search_service_name
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  tags                          = local.common_tags
  sku                           = "free"
  local_authentication_enabled  = false # RBAC-only (no API keys)
  authentication_failure_mode   = "http401WithBearerChallenge"
  public_network_access_enabled = true
  partition_count               = 1
  replica_count                 = 1
  semantic_search_sku           = "standard" # Enable semantic search

  identity {
    type = "SystemAssigned"
  }
}


# ----------------------------------------------------------------------------
# ROLE ASSIGNMENTS: Grant necessary access between resources
# ----------------------------------------------------------------------------

# Grant AI Search identity access to AI Foundry (OpenAI) account
resource "azurerm_role_assignment" "search_to_ai" {
  scope                            = azurerm_cognitive_account.main.id
  role_definition_id               = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.azure_ai_user_role_id}"
  principal_id                     = azurerm_search_service.main.identity[0].principal_id
  skip_service_principal_aad_check = true
}

# Grant AI account's managed identity access to storage blobs
resource "azurerm_role_assignment" "ai_to_storage" {
  scope                            = azurerm_storage_account.main.id
  role_definition_id               = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.storage_blob_data_contributor_role_id}"
  principal_id                     = azurerm_cognitive_account.main.identity[0].principal_id
  skip_service_principal_aad_check = true
}

# Grant developer access to storage blobs for local development (optional)
resource "azurerm_role_assignment" "developer_to_storage" {
  count                            = var.developer_object_id != "" ? 1 : 0 # Only create if developer_object_id is provided
  scope                            = azurerm_storage_account.main.id
  role_definition_id               = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.storage_blob_data_contributor_role_id}"
  principal_id                     = var.developer_object_id
  skip_service_principal_aad_check = false
}


# ----------------------------------------------------------------------------
# MODULE 5: Container Apps Environment (for hosting FastAPI app)
# ----------------------------------------------------------------------------

# Container Apps Environment (hosting platform)
resource "azurerm_container_app_environment" "main" {
  name                       = local.container_app_env_name
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tags                       = local.common_tags
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  internal_load_balancer_enabled = false # Public endpoints allowed
  zone_redundancy_enabled        = false # Single-zone deployment (cheaper)
}


# ----------------------------------------------------------------------------
# OUTPUTS - Values you'll need after deployment e.g. endpoints & resource names
# ----------------------------------------------------------------------------

output "openai_endpoint" {
  description = "The endpoint URL for Azure OpenAI"
  value       = azurerm_cognitive_account.main.endpoint
}

output "search_service_principal_id" {
  description = "principalId of Azure AI Search system-assigned managed identity for role assignment"
  value       = azurerm_search_service.main.identity[0].principal_id
}

output "openai_name" {
  description = "The name of the Azure OpenAI account"
  value       = azurerm_cognitive_account.main.name
}

output "search_service_endpoint" {
  description = "The endpoint URL for Azure AI Search"
  value       = "https://${azurerm_search_service.main.name}.search.windows.net"
}

output "search_service_name" {
  description = "The name of the search service"
  value       = azurerm_search_service.main.name
}

output "storage_account_name" {
  description = "The name of the storage account"
  value       = azurerm_storage_account.main.name
}

output "invoices_container_name" {
  description = "The name of the invoices blob container"
  value       = azurerm_storage_container.invoices.name
}

output "container_app_environment_name" {
  description = "The name of the Container Apps Environment"
  value       = azurerm_container_app_environment.main.name
}

output "app_insights_connection_string" {
  description = "Application Insights connection string"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "resource_group_name" {
  description = "The resource group name"
  value       = azurerm_resource_group.main.name
}
