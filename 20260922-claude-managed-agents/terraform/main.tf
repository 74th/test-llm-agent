terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
}

# Service account the verification containers use to reach BigQuery. Its key
# is issued out-of-band by a human (see terraform/README.md) - Terraform
# never generates or stores the key material (design.md D8).
resource "google_service_account" "verification" {
  project      = var.project_id
  account_id   = var.service_account_id
  display_name = "Claude Managed Agents self-hosted verification"
  description  = "Read-only BigQuery access for the CMA self-hosted container verification harness. See openspec/changes/verify-managed-agents-custom-container."
}

# Project-level: lets the service account run query jobs (jobUser does not
# grant read access to any data by itself).
resource "google_project_iam_member" "bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.verification.email}"
}

# Dataset-level, via *_member (not *_binding) so this only adds our service
# account to the existing dataset's IAM policy instead of replacing it -
# `house_monitor` is a pre-existing dataset this change does not manage.
resource "google_bigquery_dataset_iam_member" "bigquery_data_viewer" {
  project    = var.project_id
  dataset_id = var.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.verification.email}"
}
