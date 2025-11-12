#!/bin/bash

# ============================================================================
# Terraform Deploy Script - Complete Infrastructure
# ============================================================================
# Deploys BOTH Azure AI infrastructure AND GCP Gmail setup
# Make sure to edit terraform.tfvars in both /azure and /gcp folders first!

set -e

echo "============================================="
echo "  PaperCo O2C - Full Infrastructure Deploy"
echo "============================================="
echo ""

# Check if Terraform is installed
if ! command -v terraform &> /dev/null; then
    echo "Terraform is not installed!"
    echo "Install from: https://www.terraform.io/downloads"
    exit 1
fi

echo "✓ Terraform found ($(terraform version -json | grep -o '"terraform_version":"[^"]*' | cut -d'"' -f4))"

# ============================================================================
# PART 1: Azure Infrastructure
# ============================================================================

echo ""
echo "============================================="
echo "  [1/2] Azure Infrastructure"
echo "============================================="
echo ""

# Check Azure CLI
if ! command -v az &> /dev/null; then
    echo "Azure CLI is not installed!"
    echo "Install from: https://aka.ms/azure-cli"
    exit 1
fi

echo "✓ Azure CLI found"

# Check Azure login
echo "Checking Azure login status..."
if ! az account show &> /dev/null; then
    echo "Please login to Azure:"
    az login
fi

SUBSCRIPTION=$(az account show --query name -o tsv)
echo "✓ Logged in to: $SUBSCRIPTION"

# Check Azure terraform.tfvars
if [ ! -f "azure/terraform.tfvars" ]; then
    echo ""
    echo "ERROR: azure/terraform.tfvars not found!"
    echo "Please create it and fill in your Azure details."
    exit 1
fi

echo "✓ azure/terraform.tfvars found"

# Deploy Azure
echo ""
echo "Initializing Terraform..."
cd azure
terraform init

echo ""
echo "Validating Terraform configuration..."
terraform validate

echo ""
echo "============================================="
echo "  Azure Deployment Plan Preview"
echo "============================================="
echo ""
terraform plan

echo ""
read -p "Apply this plan? (yes/no): " -r
echo ""

if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo ""
    echo "Deploying Azure resources (this takes 5-10 minutes)..."
    terraform apply -auto-approve
    
    echo ""
    echo "✓ Azure deployment complete!"
    echo ""
    echo "Azure Outputs:"
    terraform output
else
    echo "Azure deployment skipped."
fi

cd ..

# ============================================================================
# PART 2: GCP Gmail Setup
# ============================================================================

echo ""
echo "============================================="
echo "  [2/2] GCP Gmail Setup"
echo "============================================="
echo ""

# Check gcloud CLI
if ! command -v gcloud &> /dev/null; then
    echo "Google Cloud SDK is not installed!"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

echo "✓ gcloud CLI found"

# Check GCP login
echo "Checking GCP login status..."
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
    echo "Please login to Google Cloud:"
    gcloud auth login
fi

ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")
echo "✓ Logged in as: $ACCOUNT"

# Set application default credentials
echo "Setting up application default credentials..."
gcloud auth application-default login

# Check GCP terraform.tfvars
if [ ! -f "gcp/terraform.tfvars" ]; then
    echo ""
    echo "ERROR: gcp/terraform.tfvars not found!"
    echo "Please create it and fill in your GCP project details."
    exit 1
fi

echo "✓ gcp/terraform.tfvars found"

# Deploy GCP
echo ""
echo "Initializing Terraform..."
cd gcp
terraform init

echo ""
echo "Validating Terraform configuration..."
terraform validate

echo ""
echo "============================================="
echo "  GCP Deployment Plan Preview"
echo "============================================="
echo ""
terraform plan

echo ""
read -p "Apply this plan? (yes/no): " -r
echo ""

if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo ""
    echo "Deploying GCP resources..."
    terraform apply -auto-approve
    
    echo ""
    echo "✓ GCP deployment complete!"
    echo ""
    echo "GCP Outputs:"
    terraform output
else
    echo "GCP deployment skipped."
fi

cd ..

# ============================================================================
# DEPLOYMENT COMPLETE
# ============================================================================

echo ""
echo "============================================="
echo "      ✓ Full Deployment Complete!"
echo "============================================="
echo ""
echo "Next Steps:"
echo "1. Configure Gmail API OAuth credentials in GCP Console"
echo "2. Download credentials.json to /cred folder"
echo "3. Update your .env file with Azure connection strings"
echo "4. Run your application to test the setup"
echo ""
