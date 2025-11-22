# Outputs for easy access to important URLs and information after deployment

output "project_id" {
  value       = google_project.gmail_paperco_project.project_id
  description = "Finished project ID."
}

output "console_project_url" {
  value       = "https://console.cloud.google.com/home/dashboard?project=${google_project.gmail_paperco_project.project_id}"
  description = "Shortcut to the project dashboard."
}

output "oauth_consent_screen_url" {
  value       = "https://console.cloud.google.com/apis/credentials/consent?project=${google_project.gmail_paperco_project.project_id}"
  description = "Configure OAuth consent screen FIRST before creating credentials."
}

output "oauth_credentials_url" {
  value       = "https://console.cloud.google.com/apis/credentials/oauthclient?project=${google_project.gmail_paperco_project.project_id}"
  description = "Create the Desktop OAuth client JSON here AFTER consent screen setup."
}

output "oauth_credentials_local_path" {
  value       = "${path.module}/../cred/credentials.json"
  description = "Where to save the downloaded Desktop OAuth client JSON."
}

output "credentials_list_url" {
  value       = "https://console.cloud.google.com/apis/credentials?project=${google_project.gmail_paperco_project.project_id}"
  description = "List of all credentials."
}

output "manual_setup_instructions" {
  value       = <<-DESC

MANUAL STEPS REQUIRED:

1. Configure OAuth Consent Screen:
   ${google_project.gmail_paperco_project.project_id} → https://console.cloud.google.com/apis/credentials/consent?project=${google_project.gmail_paperco_project.project_id}
   - User Type: External
   - Add your email as "test user"
   - Add scope: https://www.googleapis.com/auth/gmail.readonly

2. Create OAuth Desktop Client:
   ${google_project.gmail_paperco_project.project_id} → https://console.cloud.google.com/apis/credentials/oauthclient?project=${google_project.gmail_paperco_project.project_id}
   - Application type: Desktop app
   - Name: PaperCo Gmail Desktop Client
   - Download JSON file manually and save it to: `cred/credentials.json`
   - When you first run the app, it will open a browser window for you to authenticate and authorize access, which will generate the necessary `token.json` file.

DESC
  description = "Step-by-step manual setup instructions."
}

