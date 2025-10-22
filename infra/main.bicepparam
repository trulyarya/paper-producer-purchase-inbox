// ============================================================================
// PARAMETERS FILE - Values for your deployment
// ============================================================================
// This file contains the actual values you'll use when deploying
// Fill in your details below

using './main.bicep'

// Your project identifier (3-10 characters, lowercase letters/numbers)
// Example: 'paperco' or 'o2cdemo'
param projectName = 'papierdemo'

// Azure region where everything will be deployed
// Common options: 'eastus', 'eastus2', 'westus2', 'westeurope', 'swedencentral'
param location = 'swedencentral'

// Environment: dev, test, or prod
param environmentName = 'dev'

// Your email for tagging resources
param adminEmail = 'arya1984@gmail.com'
