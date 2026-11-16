// AnschlussRadar infrastructure, one resource group per environment.
//
// Deploy:
//   az group create -n rg-anschlussradar-dev -l germanywestcentral
//   az deployment group create -g rg-anschlussradar-dev -f infra/main.bicep -p infra/main.dev.bicepparam
//
// Not created here: the free Azure Data Explorer cluster (made in the ADX web UI,
// outside any subscription) and the secret values in Key Vault (set once by hand).

targetScope = 'resourceGroup'

@description('Short environment name: dev or prod')
@allowed(['dev', 'prod'])
param env string = 'dev'

@description('Region for most resources')
param location string = resourceGroup().location

@description('Region for the Flex Consumption Function App. Check: az functionapp list-flexconsumption-locations')
param functionLocation string = location

@description('Static Web Apps is offered in a few regions only')
param staticWebAppLocation string = 'westeurope'

@description('Create the Static Web App. If the region refuses new customers, try again later or pick another of: westeurope, centralus, eastus2, westus2, eastasia')
param deployWebApp bool = false

@description('Create the API Function App that serves the web app (phase 4)')
param deployApi bool = false

@description('Extra web addresses allowed to call the API, e.g. https://anschlussradar.de once the domain exists')
param extraWebOrigins array = []

@description('Object ID of the Entra user or group that administers SQL and Key Vault')
param adminObjectId string

@description('Login name shown for the SQL Entra admin, e.g. your e-mail')
param adminLogin string

@description('E-mail address for budget alerts')
param budgetEmail string

@description('Monthly budget in EUR')
param monthlyBudget int = 10

@description('First day of the current month, yyyy-MM-01')
param budgetStartDate string

@description('Data Explorer free cluster URIs, from the ADX web UI (My cluster)')
param kustoQueryUri string = ''
param kustoIngestUri string = ''

@description('Object ID of the GitHub Actions service principal that writes models (empty to skip)')
param deployPrincipalId string = ''

@description('Entra app registration that has Ingestor and Viewer rights on the ADX database')
param kustoAppId string = ''
param kustoTenantId string = tenant().tenantId

var prefix = 'ar'
var suffix = uniqueString(resourceGroup().id)
var tags = {
  project: 'anschlussradar'
  env: env
}

// ---------------------------------------------------------------------------
// Monitoring
// ---------------------------------------------------------------------------

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${prefix}-${env}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: json('0.2') }
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${prefix}-${env}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    SamplingPercentage: 25
  }
}

// ---------------------------------------------------------------------------
// Storage: raw data lake (bronze) and the Functions account
// ---------------------------------------------------------------------------

resource rawStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'st${prefix}raw${env}${take(suffix, 6)}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    accessTier: 'Hot'
  }
}

resource rawBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: rawStorage
  name: 'default'
}

resource rawContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: rawBlob
  name: 'raw'
}

resource rawLifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: rawStorage
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'cool-after-30-days'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: { blobTypes: ['blockBlob'], prefixMatch: ['raw/'] }
            actions: { baseBlob: { tierToCool: { daysAfterModificationGreaterThan: 30 } } }
          }
        }
      ]
    }
  }
}

// Trained models. Derived from open data, no personal data: single blobs can be read
// anonymously by the API (Static Web Apps managed functions have no managed identity).
// Listing is not allowed, and writing needs Entra ID.
resource modelStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'st${prefix}mdl${env}${take(suffix, 6)}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: true
    allowSharedKeyAccess: false
    accessTier: 'Hot'
  }
}

resource modelBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: modelStorage
  name: 'default'
}

resource modelContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: modelBlob
  name: 'models'
  properties: { publicAccess: 'Blob' }
}

resource modelWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployPrincipalId)) {
  scope: modelStorage
  name: guid(modelStorage.id, deployPrincipalId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource modelAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: modelStorage
  name: guid(modelStorage.id, adminObjectId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: adminObjectId
  }
}

resource funcStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'st${prefix}fn${env}${take(suffix, 6)}'
  location: functionLocation
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
  }
}

resource funcBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: funcStorage
  name: 'default'
}

resource deployContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: funcBlob
  name: 'deployments'
}

// ---------------------------------------------------------------------------
// Key Vault (RBAC). Secrets: db-client-id, db-api-key, kusto-app-secret
// ---------------------------------------------------------------------------

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${prefix}-${env}-${take(suffix, 6)}'
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// ---------------------------------------------------------------------------
// Ingestion Function App, Flex Consumption
// ---------------------------------------------------------------------------

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'asp-${prefix}-ingest-${env}'
  location: functionLocation
  tags: tags
  kind: 'functionapp'
  sku: { tier: 'FlexConsumption', name: 'FC1' }
  properties: { reserved: true }
}

var kvRef = 'VaultName=${vault.name};SecretName='

resource ingestApp 'Microsoft.Web/sites@2024-04-01' = {
  name: 'func-${prefix}-ingest-${env}-${take(suffix, 6)}'
  location: functionLocation
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    keyVaultReferenceIdentity: 'SystemAssigned'
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${funcStorage.properties.primaryEndpoints.blob}deployments'
          authentication: { type: 'SystemAssignedIdentity' }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 40
        instanceMemoryMB: 512
      }
      runtime: { name: 'python', version: '3.11' }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: funcStorage.name }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
        { name: 'DB_CLIENT_ID', value: '@Microsoft.KeyVault(${kvRef}db-client-id)' }
        { name: 'DB_API_KEY', value: '@Microsoft.KeyVault(${kvRef}db-api-key)' }
        { name: 'POLLER_BUDGET_PER_MINUTE', value: '50' }
        { name: 'SINK', value: 'azure' }
        { name: 'HUBS_FILE', value: 'config/hubs.csv' }
        { name: 'BLOB_ACCOUNT_URL', value: rawStorage.properties.primaryEndpoints.blob }
        { name: 'BLOB_CONTAINER', value: 'raw' }
        { name: 'KUSTO_QUERY_URI', value: kustoQueryUri }
        { name: 'KUSTO_INGEST_URI', value: kustoIngestUri }
        { name: 'KUSTO_DATABASE', value: 'anschlussradar' }
        { name: 'KUSTO_APP_ID', value: kustoAppId }
        { name: 'KUSTO_TENANT_ID', value: kustoTenantId }
        { name: 'KUSTO_APP_SECRET', value: '@Microsoft.KeyVault(${kvRef}kusto-app-secret)' }
        // Weather: hub coordinates come from the public station list
        { name: 'MODELS_BASE_URL', value: '${modelStorage.properties.primaryEndpoints.blob}models' }
      ]
    }
  }
}

// Built-in role definition IDs
var roles = {
  blobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  blobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  queueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  tableDataContributor: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  kvSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  kvSecretsOfficer: 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
}

resource funcStorageOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: funcStorage
  name: guid(funcStorage.id, ingestApp.id, roles.blobDataOwner)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobDataOwner)
    principalId: ingestApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource funcStorageQueue 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: funcStorage
  name: guid(funcStorage.id, ingestApp.id, roles.queueDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.queueDataContributor)
    principalId: ingestApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource funcStorageTable 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: funcStorage
  name: guid(funcStorage.id, ingestApp.id, roles.tableDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.tableDataContributor)
    principalId: ingestApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource rawWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: rawStorage
  name: guid(rawStorage.id, ingestApp.id, roles.blobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobDataContributor)
    principalId: ingestApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource secretsReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, ingestApp.id, roles.kvSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.kvSecretsUser)
    principalId: ingestApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource secretsAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, adminObjectId, roles.kvSecretsOfficer)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.kvSecretsOfficer)
    principalId: adminObjectId
  }
}

// You also read raw files from your laptop (backfill, debugging)
resource rawAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: rawStorage
  name: guid(rawStorage.id, adminObjectId, roles.blobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobDataContributor)
    principalId: adminObjectId
  }
}

// ---------------------------------------------------------------------------
// Azure SQL Database, free offer, Entra-only authentication
// ---------------------------------------------------------------------------

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: 'sql-${prefix}-${env}-${take(suffix, 6)}'
  location: location
  tags: tags
  properties: {
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      azureADOnlyAuthentication: true
      login: adminLogin
      sid: adminObjectId
      tenantId: tenant().tenantId
      principalType: 'User'
    }
  }
}

resource sqlAllowAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource sqlDb 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: 'sqldb-${prefix}-${env}'
  location: location
  tags: tags
  sku: { name: 'GP_S_Gen5_2', tier: 'GeneralPurpose' }
  properties: {
    useFreeLimit: true
    freeLimitExhaustionBehavior: 'AutoPause'
    autoPauseDelay: 60
    minCapacity: json('0.5')
    maxSizeBytes: 34359738368
  }
}

// ---------------------------------------------------------------------------
// Static Web App (free plan): only the web pages. The API is its own Function App,
// because Static Web Apps managed functions have no managed identity.
// ---------------------------------------------------------------------------

resource web 'Microsoft.Web/staticSites@2023-12-01' = if (deployWebApp) {
  name: 'stapp-${prefix}-${env}'
  location: staticWebAppLocation
  tags: tags
  sku: { name: 'Free', tier: 'Free' }
  properties: {}
}

// ---------------------------------------------------------------------------
// API Function App, Flex Consumption (one app per Flex plan)
// ---------------------------------------------------------------------------

var webOrigins = concat(deployWebApp ? ['https://${web!.properties.defaultHostname}'] : [], extraWebOrigins)

// 'Hat's geklappt?' answers from the web app: one small JSON file each, no personal data.
resource feedbackContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (deployApi) {
  parent: funcBlob
  name: 'feedback'
}

resource apiDeployContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (deployApi) {
  parent: funcBlob
  name: 'deployments-api'
}

resource apiPlan 'Microsoft.Web/serverfarms@2024-04-01' = if (deployApi) {
  name: 'asp-${prefix}-api-${env}'
  location: functionLocation
  tags: tags
  kind: 'functionapp'
  sku: { tier: 'FlexConsumption', name: 'FC1' }
  properties: { reserved: true }
}

resource apiApp 'Microsoft.Web/sites@2024-04-01' = if (deployApi) {
  name: 'func-${prefix}-api-${env}-${take(suffix, 6)}'
  location: functionLocation
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: apiPlan.id
    httpsOnly: true
    keyVaultReferenceIdentity: 'SystemAssigned'
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${funcStorage.properties.primaryEndpoints.blob}deployments-api'
          authentication: { type: 'SystemAssignedIdentity' }
        }
      }
      // A cap on instances is also a cap on cost if someone floods the API.
      scaleAndConcurrency: {
        maximumInstanceCount: 10
        instanceMemoryMB: 2048
      }
      runtime: { name: 'python', version: '3.11' }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      cors: { allowedOrigins: webOrigins }
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: funcStorage.name }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
        { name: 'MODELS_BASE_URL', value: '${modelStorage.properties.primaryEndpoints.blob}models' }
        { name: 'STATIONS_PATH', value: 'stations/stations.json' }
        { name: 'FEEDBACK_ACCOUNT_URL', value: funcStorage.properties.primaryEndpoints.blob }
        { name: 'FEEDBACK_CONTAINER', value: 'feedback' }
        { name: 'HUBS_FILE', value: 'config/hubs.csv' }
        { name: 'TRANSITOUS_CONTACT', value: 'https://github.com/s-s-mim/anschlussradar' }
        { name: 'KUSTO_QUERY_URI', value: kustoQueryUri }
        { name: 'KUSTO_DATABASE', value: 'anschlussradar' }
        { name: 'KUSTO_APP_ID', value: kustoAppId }
        { name: 'KUSTO_TENANT_ID', value: kustoTenantId }
        { name: 'KUSTO_APP_SECRET', value: '@Microsoft.KeyVault(${kvRef}kusto-app-secret)' }
      ]
    }
  }
  dependsOn: [apiDeployContainer]
}

resource apiStorageOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployApi) {
  scope: funcStorage
  name: guid(funcStorage.id, 'api', roles.blobDataOwner)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobDataOwner)
    principalId: apiApp!.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource apiStorageQueue 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployApi) {
  scope: funcStorage
  name: guid(funcStorage.id, 'api', roles.queueDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.queueDataContributor)
    principalId: apiApp!.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource apiStorageTable 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployApi) {
  scope: funcStorage
  name: guid(funcStorage.id, 'api', roles.tableDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.tableDataContributor)
    principalId: apiApp!.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource apiSecretsReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployApi) {
  scope: vault
  name: guid(vault.id, 'api', roles.kvSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.kvSecretsUser)
    principalId: apiApp!.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Budget with alerts at 50, 80 and 100 percent
// ---------------------------------------------------------------------------

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'budget-${prefix}-${env}'
  properties: {
    category: 'Cost'
    amount: monthlyBudget
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      actual50: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 50
        contactEmails: [budgetEmail]
        thresholdType: 'Actual'
      }
      actual80: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        contactEmails: [budgetEmail]
        thresholdType: 'Actual'
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        contactEmails: [budgetEmail]
        thresholdType: 'Forecasted'
      }
    }
  }
}

output ingestAppName string = ingestApp.name
output rawStorageAccount string = rawStorage.name
output keyVaultName string = vault.name
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output sqlDatabase string = sqlDb.name
output staticWebAppName string = deployWebApp ? web.name : ''
output staticWebAppHost string = deployWebApp ? web!.properties.defaultHostname : ''
output apiAppName string = deployApi ? apiApp!.name : ''
output apiBaseUrl string = deployApi ? 'https://${apiApp!.properties.defaultHostName}/api/v1' : ''
output modelsAccountUrl string = modelStorage.properties.primaryEndpoints.blob
output modelsBaseUrl string = '${modelStorage.properties.primaryEndpoints.blob}models'
