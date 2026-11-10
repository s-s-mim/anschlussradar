using 'main.bicep'

param env = 'dev'
param location = 'germanywestcentral'

// az ad signed-in-user show --query id -o tsv
param adminObjectId = '<your Entra object id>'
param adminLogin = '<your sign-in e-mail>'

param budgetEmail = '<your e-mail>'
param monthlyBudget = 10
param budgetStartDate = '2026-11-01'

// From the Data Explorer web UI -> My cluster
param kustoQueryUri = 'https://<cluster>.<region>.kusto.windows.net'
param kustoIngestUri = 'https://ingest-<cluster>.<region>.kusto.windows.net'
param kustoAppId = '<app registration client id>'
