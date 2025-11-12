#!/bin/bash

# ============================================================================
# Terraform Cleanup Script - Complete Infrastructure
# ============================================================================
# WARNING: This will DELETE ALL resources from BOTH Azure AND GCP!
# Use this when you're done to avoid ongoing costs.

set -e

echo "========================================"
echo "     RESOURCE DELETION WARNING"
echo "========================================"
echo ""
echo "This will permanently delete:"
echo "  - ALL Azure resources (AI Services, Storage, Search, Container Apps)"
echo "  - ALL GCP resources (Gmail API configurations)"
echo "  - ALL data (invoices, logs, indexes, credentials)"
echo ""
echo "This action CANNOT be undone!"
echo ""
read -p "Type 'DELETE' to confirm: " -r
echo ""

if [[ ! $REPLY == "DELETE" ]]; then
    echo "Cancelled. No resources were deleted."
    exit 0
fi

# Check if Terraform is installed
if ! command -v terraform &> /dev/null; then
    echo "Terraform is not installed!"
    exit 1
fi

# ============================================================================
# PART 1: Destroy GCP Resources (do this first to avoid dependency issues)
# ============================================================================

echo ""
echo "========================================"
echo "  [1/2] Destroying GCP Resources"
echo "========================================"
echo ""

if [ -d "gcp" ]; then
    cd gcp
    
    if [ -f "terraform.tfstate" ]; then
        echo "Destroying GCP resources..."
        terraform destroy -auto-approve
        echo "✓ GCP resources deleted"
    else
        echo "No GCP terraform state found, skipping..."
    fi
    
    cd ..
else
    echo "GCP folder not found, skipping..."
fi

# ============================================================================
# PART 2: Destroy Azure Resources
# ============================================================================

echo ""
echo "========================================"
echo "  [2/2] Destroying Azure Resources"
echo "========================================"
echo ""

if [ -d "azure" ]; then
    cd azure
    
    if [ -f "terraform.tfstate" ]; then
        echo "Destroying Azure resources..."
        terraform destroy -auto-approve
        echo "✓ Azure resources deleted"
    else
        echo "No Azure terraform state found, skipping..."
    fi
    
    cd ..
else
    echo "Azure folder not found, skipping..."
fi

# ============================================================================
# CLEANUP COMPLETE
# ============================================================================

echo ""
echo "========================================"
echo "      ✓ Cleanup Complete!"
echo "========================================"
echo ""
echo "All cloud resources have been deleted."
echo "Terraform states have been cleared."
echo ""
