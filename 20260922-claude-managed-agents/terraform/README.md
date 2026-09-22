# Terraform: verification service account

Creates a GCP service account in `nnyn-dev` (by default) with exactly two
grants: `roles/bigquery.jobUser` at the project level (run query jobs) and
`roles/bigquery.dataViewer` on the existing `house_monitor` dataset (read the
`co2` table and any other table in that dataset). It does not manage the
dataset or table themselves, and it does not grant project-wide
`dataViewer` (see design.md D8 for why dataset-level, not table-level).

## Apply

```bash
cd terraform
terraform init
terraform plan   # confirm: only new resources are the service account + 2 IAM bindings
terraform apply
```

Requires a GCP identity with `roles/iam.serviceAccountAdmin` and
`roles/bigquery.dataOwner` (or equivalent) on `nnyn-dev`, and
`gcloud auth application-default login` (or `GOOGLE_APPLICATION_CREDENTIALS`
pointing at a credential with those permissions) before running `terraform
plan`/`apply`.

## Issuing the key

Terraform deliberately does **not** create a service account key - key
material would then sit in `terraform.tfstate` in plaintext. Issue it by hand
after `apply`:

```bash
gcloud iam service-accounts keys create secrets/gcp-sa-key.json \
  --iam-account "$(terraform output -raw service_account_email)"
```

`secrets/` is gitignored. Never commit `secrets/gcp-sa-key.json`.

## Tearing down

```bash
terraform destroy
gcloud iam service-accounts keys delete <KEY_ID> \
  --iam-account "$(terraform output -raw service_account_email)"
```

`terraform destroy` removes the service account and its two IAM bindings; it
does not touch the `house_monitor` dataset or the `co2` table. Delete any
keys you issued separately - `terraform destroy` does not know about keys it
didn't create.
