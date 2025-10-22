# Azure Infrastructure Deployment Guide

This folder contains Bicep infrastructure-as-code for the O2C Email Intake Demo.

## Files

```txt
infra/
├── main.bicep           # Infrastructure template
├── main.bicepparam      # Configuration values (EDIT THIS)
├── deploy.sh            # Automated deployment script
├── cleanup.sh           # Resource deletion script
└── README.md            # This file
```

## Resources Deployed

- **Azure AI Foundry (AIServices account)** - GPT-5-mini and text-embedding-3-large models with project
- **Azure AI Search** - Vector search (Basic tier)
- **Storage Account** - Blob storage for invoice PDFs
- **Container Apps Environment** - FastAPI hosting platform
- **Log Analytics Workspace** - Monitoring and logging

## Prerequisites

1. Azure CLI installed - Check with `az --version` or install from <https://aka.ms/azure-cli>
2. Azure subscription with Owner or Contributor access
3. Azure AI Foundry / OpenAI access approval - Apply at <https://aka.ms/oai/access>

## Quick Deployment

```bash
# 1. Login to Azure
az login

# 2. Edit configuration
# Open main.bicepparam and update projectName, adminEmail, location

# 3. Deploy using script
cd infra
./deploy.sh
```

The deployment takes 5-10 minutes.

## Manual Deployment Steps

If you prefer manual control:

```bash
# 1. Login to Azure
az login

# 2. Set subscription (if you have multiple)
az account list --output table
az account set --subscription "YOUR-SUBSCRIPTION-ID"

# 3. Create resource group
az group create \
  --name rg-paperco-o2c-demo \
  --location eastus

# 4. Deploy Bicep template
az deployment group create \
  --resource-group rg-paperco-o2c-demo \
  --template-file main.bicep \
  --parameters main.bicepparam

# 5. Get outputs
az deployment group show \
  --resource-group rg-paperco-o2c-demo \
  --name main \
  --query properties.outputs
```

## Post-Deployment Configuration

### Retrieve API Keys

```bash
# Azure AI Foundry account key
az cognitiveservices account keys list \
  --resource-group rg-paperco-o2c-demo \
  --name <openAiName-from-outputs>

# Azure AI Search admin key
az search admin-key show \
  --resource-group rg-paperco-o2c-demo \
  --service-name <searchServiceName-from-outputs>

# Storage connection string
az storage account show-connection-string \
  --resource-group rg-paperco-o2c-demo \
  --name <storageAccountName-from-outputs>
```

## Understanding the Bicep File

The `main.bicep` file is organized into sections:

1. **Parameters** - Input values (projectName, location, environmentName, adminEmail)
2. **Variables** - Computed resource names using uniqueString() for global uniqueness, includes AI Foundry account and project names
3. **Resources** - Azure services deployed in dependency order:
   - Log Analytics Workspace
   - Storage Account with blob container
   - Azure AI Foundry account (AIServices) with project and model deployments
   - Azure AI Search service
   - Container Apps Environment
4. **Outputs** - Endpoint URLs and resource names needed for application configuration

### Key Bicep Concepts

**Resource Declaration:**

```bicep
resource storageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' = {
  name: storageAccountName
  location: location
  properties: { ... }
}
```

**Parent-Child Relationships:**

```bicep
resource blobContainer 'Microsoft.Storage/.../containers@2025-01-01' = {
  parent: storageAccount  // Child resource
  name: 'invoices'
}
```

**Dependencies:**

```bicep
resource embeddingDeployment '...' = {
  dependsOn: [
    gpt4Deployment  // Wait for this to complete first
  ]
}
```

## Cost Estimate

Monthly cost running 24/7 with minimal usage: **$115-170**

- Azure AI Search (Basic): ~$75
- Azure AI Foundry / OpenAI (pay-per-token): ~$20-50
- Container Apps: ~$15-30
- Storage and Log Analytics: ~$5-15

Use `./cleanup.sh` to delete resources when not in use.

## Resource Cleanup

```bash
# Delete all resources
cd infra
./cleanup.sh

# Or manually delete the resource group
az group delete \
  --name rg-paperco-o2c-demo \
  --yes \
  --no-wait
```

## Troubleshooting

**Invalid model error:**

- Ensure the model name and version in main.bicep match available Azure AI models
- Current deployment uses gpt-5-mini (2025-08-07) and text-embedding-3-large

**Service quota exceeded (Search):**

- You already have a free Search service in your subscription
- The template uses Basic tier by default (line ~214)

**AI Foundry deployment failed:**

- You need Azure AI Foundry / OpenAI access approval - apply at <https://aka.ms/oai/access>
- Typical approval time is 1-2 business days

**Region doesn't support Azure AI:**

- Use regions: eastus, eastus2, westeurope, or swedencentral

**Storage account name already exists:**

- Change `projectName` in main.bicepparam to make it globally unique

**Insufficient permissions:**

- You need Contributor or Owner role on the subscription

**Concurrent deployment errors:**

- Models are deployed sequentially (text-embedding-3-large waits for gpt-5-mini)
- If issues persist, reduce deployment capacity or try again

## Architecture

```txt
┌─────────────────────────────────────────────────────────┐
│         Resource Group: rg-paperco-o2c-demo             │
├─────────────────────────────────────────────────────────┤
│  Azure AI Foundry Account (AIServices)                  │
│  - Project: paperco-dev-project                         │
│  - GPT-5-mini (50 capacity, DataZoneStandard)           │
│  - text-embedding-3-large (50 capacity, Standard)       │
├─────────────────────────────────────────────────────────┤
│  Azure AI Search             Storage Account            │
│  - Basic tier                - Standard_LRS             │
│  - Vector index              - Blob: invoices           │
│  - Semantic search           - TLS 1.2 enforced         │
├─────────────────────────────────────────────────────────┤
│  Container Apps Environment                             │
│  - FastAPI hosting                                      │
│  - Integrated with Log Analytics                        │
├─────────────────────────────────────────────────────────┤
│  Log Analytics Workspace                                │
│  - 30-day retention                                     │
│  - PerGB2018 pricing tier                               │
└─────────────────────────────────────────────────────────┘
```

## Next Steps

After deployment:

1. Save output values (endpoints, resource names)
2. Retrieve API keys for Azure AI Foundry and Search
3. Set up Airtable base with tables for products, customers, inventory, orders, and invoices
4. Create Airtable API key and configure access
5. Build FastAPI application with agent implementations
6. Configure Gmail and Slack integrations
7. Deploy container app to Azure Container Apps

## Learn More

- Bicep Documentation: <https://learn.microsoft.com/azure/azure-resource-manager/bicep/>
- Azure AI Foundry: <https://learn.microsoft.com/azure/ai-studio/>
- Azure OpenAI: <https://learn.microsoft.com/azure/ai-services/openai/>
- Azure AI Search: <https://learn.microsoft.com/azure/search/>
- Container Apps: <https://learn.microsoft.com/azure/container-apps/>
