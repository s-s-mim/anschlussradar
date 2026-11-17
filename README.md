# AnschlussRadar

**Wie wahrscheinlich klappt mein Anschluss?** AnschlussRadar zeigt für Zugverbindungen in ganz Deutschland, wie zuverlässig jeder Umstieg ist, auf Basis echter Verspätungsdaten der Deutschen Bahn.

AnschlussRadar predicts how likely a train connection in Germany is to work. It records live data from the Deutsche Bahn Timetables API, builds a history in Azure Data Explorer, trains a model on it, and shows a reliability score next to every connection in a mobile web app.

Full technical documentation (architecture, data model, pipelines, ML, plan): see the project doc.

## Status

| Phase | State |
| --- | --- |
| 1 Setup | ready to run |
| 2 Ingestion and storage | **code in this repo** |
| 3 Data model, quality, IaC | **KQL, Bicep and CI in this repo** |
| 4 API and app v1 | next |
| 5 ML model | **training, promotion and serving code in this repo**; first run after about 3 weeks of data |
| 6, 7 v2 and v3 | later |

## Repository

```
config/hubs.csv            stations recorded continuously
src/anschlussradar/        shared Python package
  db_api/                  API client, XML parser, time handling
  ingest/                  scheduler, polling jobs, local CLI
  storage/                 local and Azure writers
  ml/                      features, training, champion/challenger, serving
functions/ingest/          Azure Function App (timer triggers)
kql/                       Data Explorer tables, views, functions, quality checks
infra/                     Bicep templates
scripts/                   KQL generator and deploy helper
tests/                     unit tests with saved XML responses
.github/workflows/         CI and deployment
```

## Step by step

### Step 1: Get a DB API key (10 minutes)

1. Create an account at [developers.deutschebahn.com](https://developers.deutschebahn.com/).
2. Create an application, then subscribe it to the **Timetables** API with the free plan.
3. Copy the Client ID and the API key.

### Step 2: Run the poller on your laptop (30 minutes)

You need Python 3.11 or newer.

```bash
git clone https://github.com/<you>/anschlussradar.git
cd anschlussradar
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                             # all tests should pass

cp .env.example .env               # then put your DB_CLIENT_ID and DB_API_KEY in .env
```

Check the station list. Every EVA number in `config/hubs.csv` should come back with the right name:

```bash
python -m anschlussradar.ingest.cli station "Frankfurt Hbf"
```

Load plans and full changes for all hubs once, then poll:

```bash
python -m anschlussradar.ingest.cli bootstrap
python -m anschlussradar.ingest.cli once      # one minute of calls
python -m anschlussradar.ingest.cli loop      # keeps running, Ctrl+C to stop
```

Everything lands in `./data`: raw XML under `data/raw/`, parsed rows under `data/tables/`. Open a few files and compare them with what DB Navigator shows for the same station.

### Step 3: Create the free Data Explorer cluster (15 minutes)

1. Go to [dataexplorer.azure.com/freecluster](https://dataexplorer.azure.com/freecluster) and sign in with your Microsoft account.
2. Create a cluster and a database named `anschlussradar`.
3. Note the **query URI** and the **data ingestion URI** on the My cluster page.
4. In Microsoft Entra ID (Azure portal), create an app registration, e.g. `anschlussradar-ingest`, and a client secret.
5. In the Data Explorer web UI, give the app rights on the database:

```kusto
.add database anschlussradar ingestors ('aadapp=<app client id>;<tenant id>')
.add database anschlussradar viewers ('aadapp=<app client id>;<tenant id>')
.add database anschlussradar admins ('aadapp=<app client id>;<tenant id>')
```

The admin role is needed to run the fact builder commands and the KQL deploy workflow.

6. Create the tables, views and functions:

```bash
pip install -e ".[azure]"
python scripts/apply_kql.py --dry-run     # look at the commands first
python scripts/apply_kql.py               # uses KUSTO_* from .env
```

### Step 4: Deploy the Azure resources (30 minutes)

Install the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), then:

```bash
az login
az group create -n rg-anschlussradar-dev -l germanywestcentral
az functionapp list-flexconsumption-locations -o table   # check your region is listed
```

Copy `infra/main.dev.bicepparam` to `infra/main.dev.local.bicepparam` (ignored by Git, so your e-mail stays private) and fill it in (your object ID comes from `az ad signed-in-user show --query id -o tsv`), then:

```bash
az deployment group create -g rg-anschlussradar-dev \
  -f infra/main.bicep -p infra/main.dev.local.bicepparam
```

Put the three secrets into the new Key Vault:

```bash
KV=$(az deployment group show -g rg-anschlussradar-dev -n main --query properties.outputs.keyVaultName.value -o tsv)
az keyvault secret set --vault-name $KV -n db-client-id --value "<client id>"
az keyvault secret set --vault-name $KV -n db-api-key --value "<api key>"
az keyvault secret set --vault-name $KV -n kusto-app-secret --value "<app secret>"
```

### Step 5: Deploy the Function App from GitHub (20 minutes)

1. Push the repo to GitHub.
2. Create a federated credential so GitHub Actions can log in to Azure without a stored password: [Microsoft guide](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect).
3. In the repo settings add secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, and the variable `INGEST_FUNCTION_APP` (the `ingestAppName` output of step 4).
4. Run the `deploy-ingest` workflow. After a few minutes, the first rows appear:

```kusto
IngestionLog | summarize calls = count(), errors = countif(isnotempty(error_text)) by bin(fetched_at, 5m)
StopChangeEvents | take 20
```

### Step 6: Watch it for a week

- `IngestionLog`: errors and HTTP 429 responses should stay rare.
- `QualityResults`: the freshness check should stay empty.
- Azure Cost Management: should stay near zero.
- Grow `config/hubs.csv` to about 80 hubs once everything is stable.

### Step 7: Turn on weekly retraining (after about 3 weeks of data)

1. Redeploy the Bicep template with `deployPrincipalId` set to the object ID of the GitHub Actions identity, so it may write to the models container.
2. Add the repo variables `MODELS_ACCOUNT_URL` (the `modelsAccountUrl` output), `KUSTO_QUERY_URI`, `KUSTO_APP_ID`, `KUSTO_TENANT_ID`, and the secret `KUSTO_APP_SECRET`.
3. Run the `retrain` workflow once by hand. From then on it runs every Monday at 02:17 UTC.

The job exports training data, trains a logistic regression and a LightGBM model, keeps the better one, and compares it with the live model on the most recent week. It then writes `status.json` and, last, `current.json`, which tells the API which model is live and which stage the app is in. The job summary shows the decision and the metrics.

| Exit code | Meaning | What you do |
| --- | --- | --- |
| 0 | Promoted, or still collecting data | Nothing |
| 2 | Challenger rejected, champion stays live | Check `QualityResults` for last week |
| 3 | The live model dropped a stage, the banner is back | Check the data, then rerun |

To hold a version, set `"pinned": true` in `transfer/current.json` in the models container.

To try training locally on exported data:

```bash
pip install -e ".[azure,ml]"
python -m anschlussradar.ml.export --days 120 --out data/training/transfers.parquet
python -m anschlussradar.ml.train --data data/training/transfers.parquet --store local
```

### Step 8: Put the API and the web app online (phase 4)

The web app starts as a private demo: only people you invite can open it.

1. Add to `infra/main.dev.local.bicepparam`:

   ```
   param deployApi = true
   param deployWebApp = true
   param staticWebAppLocation = 'centralus'
   ```

   Then run the same `az deployment group create` command as in step 4. If West Europe still refuses new Static Web Apps, try `centralus` or `eastus2` and change "in der EU" in the privacy policy (`web/src/pages/Legal.tsx`).
2. Read the outputs: `az deployment group show -g rg-anschlussradar-dev -n main --query properties.outputs`
3. Get the Static Web App deploy token: `az staticwebapp secrets list -n stapp-ar-dev --query properties.apiKey -o tsv`
4. In the GitHub repo settings add the secret `SWA_DEPLOYMENT_TOKEN` (the token) and the variables `API_FUNCTION_APP` (`apiAppName` output), `API_BASE_URL` (`apiBaseUrl` output), `WEB_DEPLOY` = `true` and `WEB_ACCESS` = `demo`.
5. Run the workflows `stations` (builds the station list), `deploy-api` and `deploy-web` by hand once.
6. Invite yourself: Azure portal → the Static Web App → Role management → Invite. Provider GitHub, your GitHub user name, role `demo`. Open the invitation link and accept.

To go public later: fill in `web/src/site.ts`, set `WEB_ACCESS` to `public` and run `deploy-web` again.

### Step 9: Push alerts for watched connections

1. Make the key pair once: `python scripts/make_vapid_keys.py` (if it says `No module named 'cryptography'`, run `pip install cryptography` first). It prints a PUBLIC and a PRIVATE key.
2. Find your Key Vault name: `az keyvault list -g rg-anschlussradar-dev --query [].name -o tsv`
3. Store the private key there, and only there: `az keyvault secret set --vault-name <vault name> --name vapid-private-key --value <PRIVATE>`
4. Add the public key to `infra/main.dev.local.bicepparam`: `param vapidPublicKey = '<PUBLIC>'`, then run the deployment command from step 4 again.

Without these steps the app works as before; only the "Check every day" button reports that alerts are not available.

### Step 10: The question box

The help page searches its own texts on the phone. Questions it can't answer can be sent to you anonymously; they land in the `questions` table next to the watched connections. Redeploy once (the deployment command from step 4) so the API gets `QUESTION_TABLE_URL`.

**Answering questions from your PC**

1. Install the Azure extras once: `pip install -e ".[azure]"`
2. Give your own account write access to the tables (once):
   `az role assignment create --assignee <your sign-in e-mail> --role "Storage Table Data Contributor" --scope <storage account resource ID>`
   The resource ID comes from `az storage account list -g rg-anschlussradar-dev --query "[?contains(name,'fn')].id" -o tsv`.
3. Add the table address to `.env`: `QUESTION_TABLE_URL=https://<storage account>.table.core.windows.net`
4. `python scripts/questions.py list` shows open questions; `python scripts/questions.py answer` lets you answer them one by one. People who asked for a notification get it within 10 minutes. Saved questions are only ever answered by you, also after the AI step is switched on.

Test phase: each person can send 2 questions a day, the whole app at most 50 (`QUESTIONS_PER_DAY` and `QUESTIONS_DAILY_TOTAL` in `src/anschlussradar/api/questions.py`). The app says so next to the send button.

**Switching the AI step on (optional, a few euros a month at most)**

1. Azure portal → Create a resource → Azure OpenAI, region Sweden Central or Germany West Central, resource group `rg-anschlussradar-dev`.
2. In the Foundry portal: Deployments → Deploy model → `gpt-4.1-mini`, deployment type **Data Zone Standard (EU)**, so the data stays in the EU.
3. Let the API use it without a key: `az role assignment create --assignee <API managed identity principal ID> --role "Cognitive Services OpenAI User" --scope <Azure OpenAI resource ID>`. Give your own account the same role if you want `questions.py answer --translate` to translate your answers.
4. Add to `infra/main.dev.local.bicepparam`: `param openAiEndpoint = 'https://<name>.openai.azure.com/'` and `param openAiDeployment = 'gpt-4.1-mini'`, then run the deployment command from step 4 again.

The AI only answers questions asked while it is switched on, at most 300 a day and 10 per person per hour. Questions saved before stay with you. To switch it off again, set both values back to `''` and redeploy.

## Design decisions

- **Raw first.** Every response is stored unchanged before parsing, so a parser bug can be fixed and replayed from Blob Storage.
- **Idempotent.** `event_id` is a hash of the change content, so the same change seen twice is removed downstream.
- **Within the API limit by design.** The scheduler spreads calls so each hub gets recent changes every 2 minutes, one plan and one full resync per hour, at about 43 calls per minute for 80 hubs. The API keeps the remaining share for on-demand calls.
- **Daylight saving is tested.** The API sends local times without an offset; nonexistent and repeated times are flagged, not silently stored.
- **One feature definition.** Training and the API both call `ml/features.py`. Category groups, buffer buckets and the history window are rendered from it into `kql/00_shared.kql`, and a test fails if the two drift apart.
- **Point-in-time history.** A training row only sees outcomes from earlier days, as the API does at request time.
- **Champion and challenger.** A new model goes live only if it is at least as good as the live one on a week neither has seen. `current.json` is written last.
- **Forecasts, not confirmed times.** The Timetables API gives the latest forecast. `StopFacts` stores the last forecast before departure and says so.

## Data and attribution

Timetable data: Deutsche Bahn AG, Timetables API, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## License

MIT
