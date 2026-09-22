output "service_account_email" {
  description = "Email of the verification service account. Use with `gcloud iam service-accounts keys create` to issue a key (not managed by Terraform)."
  value       = google_service_account.verification.email
}
