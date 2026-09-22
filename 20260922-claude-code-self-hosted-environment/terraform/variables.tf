variable "project_id" {
  description = "GCP project that hosts the verification BigQuery table"
  type        = string
  default     = "nnyn-dev"
}

variable "bigquery_dataset" {
  description = "BigQuery dataset containing the verification table"
  type        = string
  default     = "house_monitor"
}

variable "bigquery_table" {
  description = "BigQuery table the self-hosted session must be able to read"
  type        = string
  default     = "co2"
}

variable "service_account_id" {
  description = "Service account account_id (GCP limit: 6-30 chars, lowercase/digits/hyphen)"
  type        = string
  default     = "test-claude-self-hosted-env"
}

variable "service_account_display_name" {
  description = "Human-readable name for the verification service account"
  type        = string
  default     = "test-claude-self-hosted-environment"
}
