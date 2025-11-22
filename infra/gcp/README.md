# GCP Gmail Quickstart (Terraform, Personal/Free Path)

This tiny Terraform stack bootstraps a personal GCP project for Gmail API use without attaching billing. It:

- Creates a project (if it doesn’t exist) via `gcloud`.
- Enables the Gmail API for that project.

Limitations (by Google, not Terraform):

- OAuth Desktop client credentials can’t be created via Terraform or `gcloud`. You’ll click once in the Console to create and download `credentials.json`.

## Prerequisites

- Install gcloud: <https://cloud.google.com/sdk/docs/install>
  - macOS: `brew install --cask google-cloud-sdk`
- Authenticate: `gcloud auth login` (choose your personal Google account)
- Install Terraform: <https://developer.hashicorp.com/terraform/downloads>
  - macOS: `brew install hashicorp/tap/terraform`

## Usage

From the repo root:

```bash
terraform -chdir=infra/gcp init
terraform -chdir=infra/gcp apply -auto-approve
```

Notes:

- Accept the Cloud Terms of Service once via the Console: https://console.cloud.google.com/terms/cloud
- If you don’t pass a project ID, Terraform auto-generates one like `gmail-<random>`.
- Outputs will include direct links to the Console pages you need next.

## Create OAuth Desktop Credentials (one-time click)

Google moved OAuth creation into the “Google Auth Platform” wizard (cannot be automated; no API or Terraform resource exists). Follow these exact manual steps:

1. Open the `oauth_consent_screen_url` output (or `https://console.cloud.google.com/apis/credentials/consent?project=<YOUR_PROJECT_ID>`).  
2. You’ll see “Google Auth Platform noch nicht konfiguriert / Get started”. Click **Erste Schritte / Get started**.  
3. Consent screen wizard:  
   - User type: **External**, then **Create**.  
   - Fill App name + support email + developer email → **Save and Continue**.  
   - Scopes: click **Save and Continue** (no extra scopes required).  
   - Test users: add the Gmail account(s) you’ll use → **Save and Continue** → **Return to Dashboard**.  
4. Back on the left menu, choose **Clients → Create Credentials → OAuth client ID**.  
5. Application type: **Desktop app**. Name it, click **Create**, then **Download JSON**.  
6. Place the file at `cred/credentials.json` in this repo.

Finally, run once to generate the token (creates `cred/token.json`):

```bash
pip install -r requirements.txt
python -m src.emailing.gmail_tools
```

### If the consent screen says `Error 403: access_denied`

1. In Google Cloud Console, open **Google Auth Platform → Zielgruppe / Test users** for the same project (`https://console.cloud.google.com/auth/config/clients?project=<YOUR_PROJECT_ID>`).  
2. Click **Add users** and enter every Gmail account you plan to use (the one that just failed). Save.  
3. Delete any stale token locally: `rm cred/token.json`.  
4. Re-run `python -m src.emailing.gmail_tools` and complete the browser consent again; now that the account is on the Test-Users list, Google will issue tokens instead of denying access.

## Variables

- `project_id` (string, default ""): leave empty to auto-generate.
- `project_name` (string, default "PaperCo Gmail Demo"): display name only.
- `gcloud_path` (string, default `gcloud`): override if needed.

### If you see “Callers must accept Terms of Service” error during `terraform apply`

1. Make sure the account you used with `gcloud auth login` is the same one you use in the browser (`gcloud auth list` shows the active account).  
2. While signed into that account, open <https://console.cloud.google.com/terms/cloud> and click the acceptance button.  
3. If you already created a project manually, grab its ID from the dashboard and rerun Terraform with `terraform apply -auto-approve -var="project_id=<your-project-id>"` so it reuses the existing project instead of creating a new one.  
4. Retry `terraform apply`; the `null_resource.ensure_project` step will now pass.

## Clean Up

```bash
terraform destroy -auto-approve
```

Then optionally delete the project from the Console.
