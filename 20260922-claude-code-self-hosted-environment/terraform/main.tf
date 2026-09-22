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

# Existing table — created and managed outside this change. Referenced only to
# attach a table-level IAM binding; never created, modified, or destroyed here.
data "google_bigquery_table" "verification" {
  project    = var.project_id
  dataset_id = var.bigquery_dataset
  table_id   = var.bigquery_table
}

resource "google_service_account" "verification" {
  project      = var.project_id
  account_id   = var.service_account_id
  display_name = var.service_account_display_name
}

# Query execution is billed/run as a job, so it needs a project-level role.
# Deliberately not dataset- or project-level dataViewer — see the table-level
# binding below, which is scoped to exactly one table.
resource "google_project_iam_member" "verification_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.verification.email}"
}

# Table-level read access only. Any other table in this dataset (or any other
# dataset) must remain unreadable by this service account.
resource "google_bigquery_table_iam_member" "verification_table_viewer" {
  project    = var.project_id
  dataset_id = data.google_bigquery_table.verification.dataset_id
  table_id   = data.google_bigquery_table.verification.table_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.verification.email}"
}

# No google_service_account_key resource here on purpose: it would write the
# private key in plaintext into tfstate. The key is issued by a human via
# `gcloud iam service-accounts keys create` (see README.md).
