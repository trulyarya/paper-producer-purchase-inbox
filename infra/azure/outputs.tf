# ============================================================================
# OUTPUTS - Values needed by deploy.sh and application
# ============================================================================
# This file contains all output values from the Terraform deployment.
# Outputs expose information about deployed resources for use by:
# - deploy.sh script (resource names, endpoints)
# - Container App environment variables (Azure service endpoints)
# - CI/CD pipelines (resource identifiers)

# ----------------------------------------------------------------------------
# Resource Group
# ----------------------------------------------------------------------------

output "resource_group_name" {
  description = "Name of the Azure resource group containing all resources"
  value       = azurerm_resource_group.main.name
}

# Basic deployment context (expose inputs so shell scripts don't have to "parse" tfvars)
output "location" {
  description = "Deployment location/region"
  value       = var.location
}

output "project_name" {
  description = "Project name used for resource naming"
  value       = var.project_name
}

output "environment_name" {
  description = "Environment name (dev/test/prod)"
  value       = var.environment_name
}


# ----------------------------------------------------------------------------
# Azure OpenAI / AI (Cognitive) Services
# ----------------------------------------------------------------------------

output "azure_ai_services_endpoint" {
  description = "Azure AI Services endpoint (Cognitive Services)"
  value       = azurerm_cognitive_account.main.endpoint
}

output "azure_openai_endpoint" {
  description = "Azure OpenAI chat/completions endpoint (custom subdomain)"
  value       = "https://${azurerm_cognitive_account.main.custom_subdomain_name}.openai.azure.com/"
}

output "azure_ai_project_endpoint" {
  description = "Azure AI Foundry project endpoint used by agent framework"
  value       = "https://${azurerm_cognitive_account.main.custom_subdomain_name}.services.ai.azure.com/api/projects/${azapi_resource.project.name}"
}

output "azure_openai_chat_deployment_name" {
  description = "Name of the GPT chat deployment"
  value       = azurerm_cognitive_deployment.gpt4_1.name
}

output "azure_openai_embedding_deployment_name" {
  description = "Name of the embedding deployment"
  value       = azurerm_cognitive_deployment.embedding.name
}

output "azure_openai_name" {
  description = "Name of the Azure OpenAI account"
  value       = azurerm_cognitive_account.main.name
}

output "azure_ai_services_resource_id" {
  description = "Resource ID of the Azure AI Services account"
  value       = azurerm_cognitive_account.main.id
}


# ----------------------------------------------------------------------------
# Azure AI Search
# ----------------------------------------------------------------------------

output "search_service_endpoint" {
  description = "Endpoint URL for Azure AI Search service"
  value       = "https://${azurerm_search_service.main.name}.search.windows.net"
}

output "search_service_name" {
  description = "Name of the Azure AI Search service"
  value       = azurerm_search_service.main.name
}

output "search_service_resource_id" {
  description = "Resource ID of the Azure AI Search service"
  value       = azurerm_search_service.main.id
}

output "search_service_principal_id" {
  description = "Managed identity principal ID of Azure AI Search (for role assignments)"
  value       = azurerm_search_service.main.identity[0].principal_id
}


# ----------------------------------------------------------------------------
# Storage Account
# ----------------------------------------------------------------------------

output "storage_account_name" {
  description = "Name of the Azure Storage Account for invoice PDFs"
  value       = azurerm_storage_account.main.name
}

output "storage_account_url" {
  description = "Primary blob endpoint URL for the storage account"
  value       = azurerm_storage_account.main.primary_blob_endpoint
}

output "invoices_container_name" {
  description = "Name of the blob container for storing invoice PDFs"
  value       = azurerm_storage_container.invoices.name
}

output "storage_account_resource_id" {
  description = "Resource ID of the Azure Storage Account"
  value       = azurerm_storage_account.main.id
}


# ----------------------------------------------------------------------------
# Application Insights
# ----------------------------------------------------------------------------

output "applicationinsights_connection_string" {
  description = "Application Insights connection string for telemetry"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID for Container Apps diagnostics"
  value       = azurerm_log_analytics_workspace.main.workspace_id
}

output "log_analytics_workspace_key" {
  description = "Log Analytics shared key (needed by az containerapp up)"
  value       = azurerm_log_analytics_workspace.main.primary_shared_key
  sensitive   = true
}


# ----------------------------------------------------------------------------
# Azure Container Registry
# ----------------------------------------------------------------------------

output "acr_name" {
  description = "Name of the Azure Container Registry"
  value       = azurerm_container_registry.main.name
}

output "acr_login_server" {
  description = "Login server URL for Azure Container Registry"
  value       = azurerm_container_registry.main.login_server
}

output "acr_resource_id" {
  description = "Resource ID of the Azure Container Registry"
  value       = azurerm_container_registry.main.id
}


# ----------------------------------------------------------------------------
# GitHub Actions Identity
# ----------------------------------------------------------------------------

output "github_actions_client_id" {
  description = "Client ID of the Azure AD app for GitHub Actions (OIDC authentication)"
  value       = azuread_application.github_actions.client_id
}

output "github_actions_object_id" {
  description = "Object ID of the GitHub Actions service principal"
  value       = azuread_service_principal.github_actions.object_id
}
