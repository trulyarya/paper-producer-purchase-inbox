#!/bin/bash

# ============================================================================
# Cleanup Script - Delete All Azure Resources
# ============================================================================
# WARNING: This will DELETE everything in the resource group!
# Use this when you're done with the demo to avoid ongoing costs.

set -e # This command is used to exit on error, which is good practice for destructive scripts

RESOURCE_GROUP="paperco-o2c-demo-rg"

echo "========================================"
echo "     RESOURCE DELETION WARNING          "
echo "========================================"
echo ""
echo "This will permanently delete:"
echo "  - Resource Group: $RESOURCE_GROUP"
echo "  - ALL resources inside (OpenAI, Storage, Key Vault, etc.)"
echo "  - ALL data (invoices, logs, secrets)"
echo ""
echo "This action CANNOT be undone!"
echo ""
read -p "Type 'DELETE' to confirm: " -r
echo ""

if [[ ! $REPLY == "DELETE" ]]; then
    echo "Cancelled. No resources were deleted."
    exit 0
fi

echo ""
echo "Deleting resource group..."


az group delete \
    --name "$RESOURCE_GROUP" \
    --yes \
    --no-wait


echo ""
echo "✓ Deletion initiated for resource group: $RESOURCE_GROUP"
echo ""
echo "The resource group is being deleted in the background."
echo "This may take a few minutes to complete."
echo ""
echo "You can check the status with:"
echo "  az group show --name $RESOURCE_GROUP"