# Azure Infrastructure - Terraform Deployment

This directory contains Terraform configuration to deploy all Azure resources needed for the PaperCo O2C Email Intake project.

## Resources Created

- **Resource Group** - Container for all resources
- **Log Analytics Workspace** - For monitoring and diagnostics
- **Application Insights** - For application telemetry
- **Storage Account** - For invoice PDF storage
  - Blob container: `invoices`
- **Azure AI Services Account** - OpenAI endpoint with:
  - GPT-4 deployment (`gpt-4.1`)
  - Text Embedding deployment (`text-embedding-3-large`)
- **Azure AI Search** - For semantic SKU/customer search
- **Container Apps Environment** - For hosting the Python application

## Prerequisites

1. **Azure CLI** installed and authenticated

   ```bash
   az login
   az account set --subscription "YOUR_SUBSCRIPTION_NAME_OR_ID"
   ```

2. **Terraform** installed (version >= 1.0)

   ```bash
   # macOS
   brew install terraform
   
   # Verify installation
   terraform version
   ```

3. **Permissions** - You need at least `Contributor` role on the subscription or resource group

## Configuration

1. **Edit `terraform.tfvars`** with your values:

   ```hcl
   subscription_id     = "YOUR_SUBSCRIPTION_ID"  # Get via: az account show --query id -o tsv
   resource_group_name = "paperco-o2c-rg"
   project_name        = "papierdemo"
   location            = "swedencentral"
   environment_name    = "dev"
   admin_email         = "your-email@example.com"
   ```

2. **(Optional)** Get your Azure AD Object ID for local development access:

  ```bash
  az ad signed-in-user show --query id -o tsv
  ```

  Add to `terraform.tfvars`:
  
  ```hcl
  developer_object_id = "YOUR_OBJECT_ID_HERE"
  ```

## Deployment

### Initialize Terraform

```bash
cd infra/azure
terraform init
```

This downloads the Azure provider and sets up the backend.

### Preview Changes

```bash
terraform plan
```

Review the resources that will be created. You should see ~15 resources.

### Deploy

```bash
terraform apply
```

Type `yes` when prompted. Deployment takes ~5-10 minutes.

### View Outputs

```bash
terraform output
```

Important outputs:

- `openai_endpoint` - Use for `AZURE_OPENAI_ENDPOINT` in `.env`
- `search_service_endpoint` - Use for `AZURE_SEARCH_ENDPOINT` in `.env`
- `app_insights_connection_string` - Use for `APPLICATIONINSIGHTS_CONNECTION_STRING` in `.env`

### Get Sensitive Output

```bash
terraform output -raw app_insights_connection_string
```

## Retrieve API Keys

After deployment, get the keys needed for your `.env` file:

```bash
# Azure OpenAI API Key
az cognitiveservices account keys list \
  --name $(terraform output -raw openai_name) \
  --resource-group $(terraform output -raw resource_group_name) \
  --query key1 -o tsv

# Azure AI Search Admin Key
az search admin-key show \
  --service-name $(terraform output -raw search_service_name) \
  --resource-group $(terraform output -raw resource_group_name) \
  --query primaryKey -o tsv

# Storage Account Connection String
az storage account show-connection-string \
  --name $(terraform output -raw storage_account_name) \
  --resource-group $(terraform output -raw resource_group_name) \
  --query connectionString -o tsv
```

## Update .env File

After deployment, update your `.env` file with the outputs:

```bash
# Azure OpenAI / AI Services
AZURE_OPENAI_ENDPOINT="<from terraform output openai_endpoint>"
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="gpt-4.1"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME="text-embedding-3-large"

# Azure AI Search
AZURE_SEARCH_ENDPOINT="<from terraform output search_service_endpoint>"

# Azure Storage
AZURE_STORAGE_CONNECTION_STRING="<from az storage command above>"

# Application Insights
APPLICATIONINSIGHTS_CONNECTION_STRING="<from terraform output app_insights_connection_string>"
```

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

Type `yes` when prompted.

## Troubleshooting

### Error: "Resource group already exists"

If the resource group already exists, Terraform will import it automatically.

### Error: "Cognitive Services quota exceeded"

You may need to request a quota increase for Azure OpenAI in your subscription.

### Error: "Storage account name not available"

Storage account names must be globally unique. Try changing `project_name` in `terraform.tfvars`.

### Error: "Insufficient permissions"

Ensure you have `Contributor` role on the subscription or resource group.

## Differences from Bicep

This Terraform configuration is functionally equivalent to the Bicep templates but uses Terraform's declarative syntax and state management:

- **State Management**: Terraform maintains a state file (`terraform.tfstate`) locally or in a remote backend
- **Provider Configuration**: Uses the `azurerm` provider instead of ARM templates
- **Resource Dependencies**: Terraform automatically handles dependencies based on references
- **Outputs**: Similar to Bicep outputs but accessed via `terraform output` command

## Next Steps

After successful deployment:

1. Configure Gmail OAuth credentials (see `/infra/gcp-gmail-setup/`)
2. Set up Airtable base and API key
3. Configure Slack webhook
4. Index your Airtable data into Azure AI Search
5. Run the workflow pipeline

See the main [README.md](../../README.md) for full setup instructions.
