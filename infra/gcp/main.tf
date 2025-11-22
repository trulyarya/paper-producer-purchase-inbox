
provider "google" {
}

resource "google_project" "gmail_paperco_project" {
  name       = var.project_name # Required: Friendly name for the project
  project_id = var.project_id   # Required: Unique project ID
  deletion_policy = "DELETE"
}

resource "google_project_service" "gmail_api" {
  project = google_project.gmail_paperco_project.project_id
  service = "gmail.googleapis.com"
}
