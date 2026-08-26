# arqedia-infra

AWS infrastructure for ARQEDIA ? a multi-tenant, customer-configurable due
diligence service.

- **Account:** ARQEDIA 667523685221, member of the eBL Finance organization
- **Region:** us-east-2 (Ohio). eu-central-1 to follow.
- **State:** s3://arqedia-tfstate-667523685221, native S3 locking, no DynamoDB

## Layout

- `bootstrap/` ? creates the state bucket. Runs once, local state, then left alone.
- root ? the main stack. State lives in S3.

## Running

    terraform init
    terraform validate
    terraform plan -out main.tfplan
    terraform apply main.tfplan

PowerShell splits `-out=file` at the equals sign. Use a space: `-out file`.

## Accounts

`terraform` here always targets ARQEDIA via the `arqedia` AWS profile, and the
provider refuses any other account. eBL infrastructure lives in `ebl-infra` and
is entirely separate.



Push summary — arqedia-infra initial commit: bootstrap state backend (S3, versioned, encrypted, public access blocked, native locking), root config with backend wired and region/scope as variables, README and .gitignore. Nothing sensitive committed.

Pre-build is now complete except two items:

Centralize root access and move the ARQEDIA root email off personal Gmail
AWS Budgets alert

Both are console jobs, neither blocks anything technical.
