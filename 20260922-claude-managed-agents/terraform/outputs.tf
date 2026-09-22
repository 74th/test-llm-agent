output "service_account_email" {
  description = "Email of the service account. Use this to issue a key with `gcloud iam service-accounts keys create` (see terraform/README.md)."
  value       = google_service_account.verification.email
}
