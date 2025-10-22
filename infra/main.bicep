// ============================================================================
// MAIN BICEP FILE - Order-to-Cash Email Intake Demo
// ============================================================================
// This is the entry point that orchestrates all Azure resources needed

targetScope = 'resourceGroup' // Deploy resources into a resource group (not subscription or tenant level)

// ----------------------------------------------------------------------------
// PARAMETERS - Values you provide when deploying
// ----------------------------------------------------------------------------

@description('The main identifier for all resources (e.g., "paperco" or "o2cdemo")') // Shows in Azure Portal
@minLength(3) // Must be at least 3 characters
@maxLength(10) // Cannot exceed 10 characters
param projectName string // User input: your project identifier

@description('Azure region where resources will be deployed') // Helps document the parameter
param location string = resourceGroup().location // Defaults to the resource group's location

@description('Environment name (dev, test, prod)') // Describes the purpose
@allowed([ // Only these values are permitted
  'dev'
  'test'
  'prod'
])
param environmentName string = 'dev' // Default environment is 'dev'

@description('Your email address for notifications') // Used for tagging resources
param adminEmail string // User input: admin contact email

// ----------------------------------------------------------------------------
// VARIABLES - Computed values used throughout the deployment
// ----------------------------------------------------------------------------

// Create consistent naming for all resources
var uniqueSuffix = uniqueString(resourceGroup().id) // Generates a unique hash from resource group ID (always same for same RG)
var resourcePrefix = '${projectName}-${environmentName}' // Combines project name and environment (e.g., "paperco-dev")

// Resource names
var storageAccountName = toLower(replace('${projectName}${environmentName}${take(uniqueSuffix, 8)}', '-', '')) // Storage names: lowercase, no hyphens, max 24 chars
var searchServiceName = '${resourcePrefix}-search-${uniqueSuffix}' // Example: paperco-dev-search-abc123xyz
var containerAppEnvName = '${resourcePrefix}-cae-${uniqueSuffix}' // CAE = Container Apps Environment
var logAnalyticsName = '${resourcePrefix}-logs-${uniqueSuffix}' // For monitoring and diagnostics
var aiAccountName = toLower('${resourcePrefix}-aoai-${take(uniqueSuffix, 8)}') // Azure AI Foundry account name
var aiProjectName = toLower('${resourcePrefix}-project') // Azure AI Foundry project name
var projectDisplayName = '${resourcePrefix} project' // Friendly project display name
var projectDescription = 'Azure AI project for ${resourcePrefix}' // Simple description for the project
var accountSkuName = 'S0' // Default SKU for Azure AI Foundry accounts
var deploymentSkuName = 'Standard' // Default deployment SKU name
var deploymentSkuCapacity = 50 // Default deployment capacity

// Tags for resource organization
var commonTags = { // Applied to all resources for tracking and management
  Project: 'O2C-Email-Intake' // Project identifier
  Environment: environmentName // dev, test, or prod
  ManagedBy: 'Bicep' // Indicates this was deployed via IaC
  Owner: adminEmail // Who to contact about these resources
}

// ----------------------------------------------------------------------------
// MODULE 1: Log Analytics Workspace (needed for Container Apps)
// ----------------------------------------------------------------------------

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2025-02-01' = { // Resource type and API version
  name: logAnalyticsName // The computed variable name
  location: location // Same region as other resources
  tags: commonTags // Apply standard tags
  properties: { // Configuration settings
    sku: { // Pricing tier
      name: 'PerGB2018' // Pay per GB ingested (most common option)
    }
    retentionInDays: 30 // How long to keep logs (30 days for demo, can be up to 730)
  }
}

// ----------------------------------------------------------------------------
// MODULE 2: Storage Account (for invoice PDFs)
// ----------------------------------------------------------------------------

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' = { // Storage account resource
  name: storageAccountName // Must be globally unique across all of Azure
  location: location // Azure region
  tags: commonTags // Standard tags
  sku: { // Storage redundancy option
    name: 'Standard_LRS' // Locally redundant storage (3 copies in one datacenter, cheapest for demo)
  }
  kind: 'StorageV2' // General purpose v2 (modern, recommended type)
  properties: { // Storage account settings
    accessTier: 'Hot' // Optimized for frequent access (vs 'Cool' for archival)
    supportsHttpsTrafficOnly: true // Force HTTPS for security
    minimumTlsVersion: 'TLS1_2' // Minimum encryption version
    allowBlobPublicAccess: false // Disable anonymous public access for security
  }
}

// Create blob container for invoices
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-01-01' = { // Blob service (child of storage account)
  parent: storageAccount // This belongs to the storage account above
  name: 'default' // Always named 'default' for blob services
}

resource invoicesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = { // Container (like a folder)
  parent: blobService // This belongs to the blob service
  name: 'invoices' // Container name (where PDF files will be stored)
  properties: { // Container settings
    publicAccess: 'None' // Private access only (no anonymous access)
  }
}

// ----------------------------------------------------------------------------
// MODULE 3: Azure AI Foundry project (OpenAI account + GPT deployments)
// ----------------------------------------------------------------------------

// Azure AI Foundry account (kind AIServices)
resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: aiAccountName
  location: location
  kind: 'AIServices'
  sku: {
    name: accountSkuName
  }
  identity: {
    type: 'SystemAssigned' // Required so projects can create backing workspaces
  }
  properties: {
    // Enable Projects under this account
    allowProjectManagement: true
    // Optional, points default data-plane calls to this project
    defaultProject: aiProjectName
    // Endpoint subdomain must be pre-set before provisioning projects
    customSubDomainName: aiAccountName
    publicNetworkAccess: 'Enabled'
  }
  tags: {
    deployedBy: 'bicep'
  }
}

// Project (child of the account), NOT a hub
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  name: aiProjectName
  parent: aiAccount
  location: location
  identity: {
    type: 'SystemAssigned' // Needed for AML workspace provisioning behind the project
  }
  properties: {
    displayName: projectDisplayName
    description: projectDescription
  }
  tags: {
    deployedBy: 'bicep'
  }
}

// Deployment 1: gpt-5-mini
resource gpt5Mini 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  name: 'gpt-5-mini'
  parent: aiAccount
  sku: {
    name: 'DataZoneStandard'     // or whatever SKU you’re allowed to use
    capacity: 50
  }
  properties: {
    model: {
      name: 'gpt-5-mini'
      format: 'OpenAI'
      publisher: 'OpenAI'
      version: '2025-08-07'
    }
  }
  // Parent establishes dependency on account; we also ensure project exists first for cleanliness
  dependsOn: [
    project
  ]
}

// Deployment 2: text-embedding-3-large
resource textEmbedding3Large 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  name: 'text-embedding-3-large'
  parent: aiAccount
  sku: {
    name: deploymentSkuName
    capacity: deploymentSkuCapacity
  }
  properties: {
    model: {
      name: 'text-embedding-3-large'
      format: 'OpenAI'
      publisher: 'OpenAI'
    }
  }
  // Create sequentially after the first deployment to avoid concurrent deployment hiccups
  dependsOn: [
    gpt5Mini
  ]
}

// ----------------------------------------------------------------------------
// MODULE 4: Azure AI Search (for SKU vector search)
// ----------------------------------------------------------------------------

resource searchService 'Microsoft.Search/searchServices@2025-05-01' = { // Azure AI Search service
  name: searchServiceName // Service name (must be globally unique)
  location: location // Azure region
  tags: commonTags // Standard tags
  sku: { // Pricing tier
    name: 'basic' // Free tier, or Basic tier (~$75/month, sufficient for demo with vector search)
  }
  properties: { // Search service configuration
    replicaCount: 1 // Number of replicas for high availability (1 = single instance)
    partitionCount: 1 // Number of partitions for data storage (1 = up to 2GB storage)
    hostingMode: 'default' // Hosting mode ('default' vs 'highDensity' for many small indexes)
    publicNetworkAccess: 'enabled' // Allow access from internet
    semanticSearch: 'free' // Enable semantic ranking for better search results (free tier available)
  }
}

// ----------------------------------------------------------------------------
// MODULE 5: Container Apps Environment (for hosting FastAPI app)
// ----------------------------------------------------------------------------

resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' = { // Container Apps Environment (hosting platform)
  name: containerAppEnvName // Environment name
  location: location // Azure region
  tags: commonTags // Standard tags
  properties: { // Environment configuration
    appLogsConfiguration: { // Where to send application logs
      destination: 'log-analytics' // Send logs to Log Analytics workspace
      logAnalyticsConfiguration: { // Log Analytics connection settings
        customerId: logAnalytics.properties.customerId // Workspace ID (references the logAnalytics resource)
        sharedKey: logAnalytics.listKeys().primarySharedKey // Workspace key (retrieved at deployment time)
      }
    }
  }
}

// ----------------------------------------------------------------------------
// OUTPUTS - Values you'll need after deployment
// ----------------------------------------------------------------------------

@description('The endpoint URL for Azure OpenAI') // API endpoint for making OpenAI calls
output openAiEndpoint string = aiAccount.properties.endpoint // Example: https://yourname-openai.openai.azure.com/

@description('The name of the Azure OpenAI account') // Account name for reference
output openAiName string = aiAccount.name // Used to retrieve API keys later

@description('The endpoint URL for Azure AI Search') // Search service endpoint
output searchServiceEndpoint string = 'https://${searchService.name}.search.windows.net' // Construct the full URL

@description('The name of the search service') // Service name for reference
output searchServiceName string = searchService.name // Used to retrieve admin keys later

@description('The name of the storage account') // Storage account name
output storageAccountName string = storageAccount.name // Used to access blob storage

@description('The name of the invoices blob container') // Container where PDFs are stored
output invoicesContainerName string = invoicesContainer.name // Should be 'invoices'

@description('The name of the Container Apps Environment') // Environment name for deploying apps
output containerAppEnvironmentName string = containerAppEnvironment.name // Used when deploying container apps

@description('Resource group name') // The resource group containing all resources
output resourceGroupName string = resourceGroup().name // Useful for scripting and automation
