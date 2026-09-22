variable "project_id" {
  description = "GCP project that owns the target dataset/table and where the service account is created."
  type        = string
  default     = "nnyn-dev"
}

variable "dataset_id" {
  description = "BigQuery dataset containing the target table."
  type        = string
  default     = "house_monitor"
}

variable "table_id" {
  description = "BigQuery table the service account may read (documentation only - IAM here is scoped at the dataset level, see design.md D8)."
  type        = string
  default     = "co2"
}

variable "service_account_id" {
  description = "Service account account_id (the part before @project.iam.gserviceaccount.com)."
  type        = string
  default     = "test-claude-managed-agents"
}
