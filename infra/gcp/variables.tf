
variable "project_id" {
  description = "Base GCP project ID prefix (a random suffix will be added after)."
  type        = string
  default     = "paperco-gmail-demo"
}

variable "project_name" {
  description = "Friendly display name for the project."
  type        = string
}
