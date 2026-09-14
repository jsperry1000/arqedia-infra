# providers.tf
#
# CloudFront attaches certificates from us-east-1 only, wherever the rest of the
# stack lives. This alias exists for that one reason.
#
# Mirrors the default provider in versions.tf:21 exactly except for region.
# profile, allowed_account_ids and default_tags are all repeated deliberately —
# an aliased provider inherits nothing.

provider "aws" {
  alias               = "use1"
  region              = "us-east-1"
  profile             = "arqedia"
  allowed_account_ids = ["667523685221"]

  default_tags {
    tags = {
      Project   = "ARQEDIA"
      ManagedBy = "terraform"
    }
  }
}
