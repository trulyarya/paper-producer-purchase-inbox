
# Configure the Google Cloud provider and Random provider,
#   to manage GCP resources and generate random values.
terraform {
  required_providers {
    
    google = {
      source = "hashicorp/google"
    }
    
    random = {
      source = "hashicorp/random"
    }

  }
}


# Generate a random suffix to ensure unique project ID names,
# to be appended to the base project_id
resource "random_id" "project_suffix" {
  byte_length = 4
}

resource "google_project" "gmail_paperco_project" {
  name            = var.project_name # Required: Friendly name for the project
  project_id      = "${var.project_id}-${random_id.project_suffix.hex}"   # Required: Unique project ID
  deletion_policy = "DELETE"
}

resource "google_project_service" "gmail_api" {
  project = google_project.gmail_paperco_project.project_id
  service = "gmail.googleapis.com"
}
