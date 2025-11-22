# ============================================================================
# MAIN TERRAFORM FILE - Order-to-Cash Email Intake Demo
# ============================================================================
# This file creates ONLY the AI services (OpenAI, Search, Storage).
# Container Apps infrastructure is created by 'az containerapp up' command.

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
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.6"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
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

# Azure AD provider for creating service principals and federated credentials
provider "azuread" {
  # Uses az cli authentication by default
}

# GitHub provider for managing repository secrets (requires GITHUB_TOKEN env var)
provider "github" {
  owner = var.github_owner
}


# ----------------------------------------------------------------------------
# DATA SOURCES - Reference existing Azure context
# ----------------------------------------------------------------------------

data "azurerm_client_config" "current" {}


# ----------------------------------------------------------------------------
# LOCAL VARIABLES - Computed values
# ----------------------------------------------------------------------------

locals {
  unique_suffix   = substr(md5(var.resource_group_name), 0, 8)
  resource_prefix = "${var.project_name}-${var.environment_name}"

  # Role IDs from Microsoft documentation:
  # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles
  
     #   Storage Blob Data Contributor:
  storage_blob_data_contributor_role_id = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
     #   Cognitive Services OpenAI Contributor:
  azure_oai_contributor_role_id         = "a001fd3d-188f-4b5d-821b-7da978bf7442"

  # Resource names
  storage_name    = lower(replace("${var.project_name}${var.environment_name}${local.unique_suffix}", "-", ""))
  ai_account_name = lower("${local.resource_prefix}-azopai-${substr(local.unique_suffix, 0, 8)}")
  ai_project_name = lower("${local.resource_prefix}-project")
  search_name     = "${local.resource_prefix}-search-${local.unique_suffix}"
  appinsights_name = "${local.resource_prefix}-appinsights"

  common_tags = {
    Project     = "O2C-Email-Intake"
    Environment = var.environment_name
    ManagedBy   = "Terraform"
    Owner       = var.admin_email
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
# STORAGE ACCOUNT (for invoice PDFs)
# ----------------------------------------------------------------------------

resource "azurerm_storage_account" "main" {
  name                            = local.storage_name
  location                        = azurerm_resource_group.main.location
  resource_group_name             = azurerm_resource_group.main.name
  tags                            = local.common_tags
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = true
  access_tier                     = "Hot"
}

resource "azurerm_storage_container" "invoices" {
  name                  = "invoices"
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "blob"
}


# ----------------------------------------------------------------------------
# APPLICATION INSIGHTS (for telemetry and monitoring)
# ----------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${local.resource_prefix}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}

resource "azurerm_application_insights" "main" {
  name                = local.appinsights_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "other"
  tags                = local.common_tags
}


# ----------------------------------------------------------------------------
# AZURE AI FOUNDRY (OpenAI account + GPT deployments)
# ----------------------------------------------------------------------------

resource "azurerm_cognitive_account" "main" {
  name                          = local.ai_account_name
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = local.ai_account_name
  public_network_access_enabled = true
  project_management_enabled    = true

  identity {
    type = "SystemAssigned"
  }

  tags = merge(local.common_tags, { Type = "AIServices" })
}

resource "azapi_resource" "project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = local.ai_project_name
  parent_id = azurerm_cognitive_account.main.id
  location  = azurerm_resource_group.main.location
  


  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      displayName = "${local.resource_prefix} Project"
      description = "AI Project for ${local.resource_prefix}"
    }
  }

  tags = local.common_tags
}

resource "azurerm_cognitive_deployment" "gpt4_1" {
  name                 = "gpt-4.1"
  cognitive_account_id = azurerm_cognitive_account.main.id

  model {
    format  = "OpenAI"
    name    = "gpt-4.1"
    version = "2025-04-14"
  }

  sku {
    name     = "DataZoneStandard"
    capacity = 50
  }

  depends_on = [azapi_resource.project]
}

resource "azurerm_cognitive_deployment" "embedding" {
  name                 = "text-embedding-3-large"
  cognitive_account_id = azurerm_cognitive_account.main.id

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-large"
    version = "1"
  }

  sku {
    name     = "Standard"
    capacity = 50
  }

  depends_on = [azurerm_cognitive_deployment.gpt4_1]
}


# ----------------------------------------------------------------------------
# AZURE AI SEARCH (for SKU vector search)
# ----------------------------------------------------------------------------

resource "azurerm_search_service" "main" {
  name                          = local.search_name
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  tags                          = local.common_tags
  sku                           = "basic"
  local_authentication_enabled  = false
  public_network_access_enabled = true
  partition_count               = 1
  replica_count                 = 1
  semantic_search_sku           = "standard"

  identity {
    type = "SystemAssigned"
  }
}


# ----------------------------------------------------------------------------
# ROLE ASSIGNMENTS
# ----------------------------------------------------------------------------

resource "azurerm_role_assignment" "search_to_ai" {
  scope                            = azurerm_cognitive_account.main.id
  role_definition_id               = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.azure_oai_contributor_role_id}"
  principal_id                     = azurerm_search_service.main.identity[0].principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "ai_to_storage" {
  scope                            = azurerm_storage_account.main.id
  role_definition_id               = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.storage_blob_data_contributor_role_id}"
  principal_id                     = azurerm_cognitive_account.main.identity[0].principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "developer_to_storage" {
  count                            = var.developer_object_id != "" ? 1 : 0
  scope                            = azurerm_storage_account.main.id
  role_definition_id               = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.storage_blob_data_contributor_role_id}"
  principal_id                     = var.developer_object_id
  skip_service_principal_aad_check = false
}


# ----------------------------------------------------------------------------
# AZURE CONTAINER REGISTRY (ACR) - Stores Docker images
# ----------------------------------------------------------------------------
# Passwordless ACR using system-assigned managed identity

resource "azurerm_container_registry" "main" {
  name                = lower(replace("${var.project_name}${var.environment_name}acr${local.unique_suffix}", "-", ""))
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Basic"
  admin_enabled       = false  # No passwords! Use managed identity or service principal

  identity {
    type = "SystemAssigned"
  }

  tags = local.common_tags
}

# Note: Container App's AcrPull role is assigned by deploy.py after app creation


# ----------------------------------------------------------------------------
# GITHUB ACTIONS INTEGRATION - Federated Identity (OIDC, Passwordless)
# ----------------------------------------------------------------------------
# GitHub Actions proves identity via OIDC, Azure issues temporary tokens

resource "azuread_application" "github_actions" {
  display_name = "${local.resource_prefix}-github-actions"
  tags         = ["CI/CD", "GitHub Actions", "Terraform"]
}

resource "azuread_service_principal" "github_actions" {
  client_id = azuread_application.github_actions.client_id
  tags      = ["CI/CD", "GitHub Actions"]
}

# Federated credential for main branch (allows GitHub Actions to get Azure tokens)
resource "azuread_application_federated_identity_credential" "github_main" {
  application_id = azuread_application.github_actions.id
  display_name   = "GitHub-Actions-Main-Branch"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${var.github_owner}/${var.github_repo}:ref:refs/heads/main"
}

# Federated credential for pull requests
resource "azuread_application_federated_identity_credential" "github_pr" {
  application_id = azuread_application.github_actions.id
  display_name   = "GitHub-Actions-Pull-Requests"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${var.github_owner}/${var.github_repo}:pull_request"
}

# GitHub Actions can push images to ACR
resource "azurerm_role_assignment" "github_to_acr" {
  scope                            = azurerm_container_registry.main.id
  role_definition_name             = "AcrPush"
  principal_id                     = azuread_service_principal.github_actions.object_id
  skip_service_principal_aad_check = true
}

# GitHub Actions can update Container App
resource "azurerm_role_assignment" "github_to_rg" {
  scope                            = azurerm_resource_group.main.id
  role_definition_name             = "Contributor"
  principal_id                     = azuread_service_principal.github_actions.object_id
  skip_service_principal_aad_check = true
}

# Automated secret injection (requires GITHUB_TOKEN env var, optional)
resource "github_actions_secret" "azure_client_id" {
  repository      = var.github_repo
  secret_name     = "AZURE_CLIENT_ID"
  plaintext_value = azuread_application.github_actions.client_id
}

resource "github_actions_secret" "azure_tenant_id" {
  repository      = var.github_repo
  secret_name     = "AZURE_TENANT_ID"
  plaintext_value = data.azurerm_client_config.current.tenant_id
}

resource "github_actions_secret" "azure_subscription_id" {
  repository      = var.github_repo
  secret_name     = "AZURE_SUBSCRIPTION_ID"
  plaintext_value = var.subscription_id
}

resource "github_actions_secret" "acr_name" {
  repository      = var.github_repo
  secret_name     = "ACR_NAME"
  plaintext_value = azurerm_container_registry.main.name
}

resource "github_actions_secret" "acr_login_server" {
  repository      = var.github_repo
  secret_name     = "ACR_LOGIN_SERVER"
  plaintext_value = azurerm_container_registry.main.login_server
}

resource "github_actions_secret" "resource_group" {
  repository      = var.github_repo
  secret_name     = "RESOURCE_GROUP_NAME"
  plaintext_value = azurerm_resource_group.main.name
}

resource "github_actions_secret" "container_app_name" {
  repository      = var.github_repo
  secret_name     = "CONTAINER_APP_NAME"
  plaintext_value = "${var.project_name}-${var.environment_name}-app"
}
