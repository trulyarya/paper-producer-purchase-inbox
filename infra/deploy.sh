#!/bin/bash

# ============================================================================
# Quick Deploy Script for Azure Infrastructure
# ============================================================================
# This script automates the deployment of your Azure resources
# Make sure to edit main.bicepparam first with your details!

set -e  # Exit on any error

echo "========================================"
echo "     O2C Email Intake - Azure Deploy    "
echo "========================================"
echo ""

# Configuration
RESOURCE_GROUP="paperco-o2c-inbox-resourcegroup"
LOCATION="swedencentral"
DEPLOYMENT_NAME="papercoinfra"

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo "Azure CLI is not installed!"
    echo "Please install from: https://aka.ms/azure-cli"
    exit 1
fi

echo "✓ Azure CLI found"

# Check if logged in
echo ""
echo "Checking Azure login status..."
if ! az account show &> /dev/null; then
    echo "Please login to Azure:"
    
    az login

fi

SUBSCRIPTION=$(az account show --query name -o tsv)
echo "✓ Logged in to: $SUBSCRIPTION"

# Create resource group
echo ""
echo "Creating resource group: $RESOURCE_GROUP"


az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none


echo "✓ Resource group created"

# Deploy Bicep template
echo ""
echo "Deploying Azure resources (this takes 5-10 minutes)..."
echo ""


az deployment group create \
    --name "$DEPLOYMENT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --template-file main.bicep \
    --parameters main.bicepparam \
    --output table


echo ""
echo "========================================"
echo "      ✓ Deployment Complete!            "
echo "========================================"
echo ""

# Get outputs
echo "Deployment Outputs:"
echo ""


az deployment group show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$DEPLOYMENT_NAME" \
    --query properties.outputs \
    --output json


echo ""
echo "   Next Steps:"
echo "1. Save the outputs above - you'll need them!"
echo "2. Get API keys and store in Key Vault (see README.md)"
echo "3. Configure your FastAPI application with these values"
echo ""
echo "To view in Azure Portal:"
echo "https://portal.azure.com/#@/resource/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP"
echo ""
