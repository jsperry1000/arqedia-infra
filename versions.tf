terraform {
  required_version = ">= 1.10"

  backend "s3" {
    bucket       = "arqedia-tfstate-667523685221"
    key          = "arqedia/us-east-2/terraform.tfstate"
    region       = "us-east-2"
    profile      = "arqedia"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

provider "aws" {
  region              = var.aws_region
  profile             = "arqedia"
  allowed_account_ids = ["667523685221"]

  default_tags {
    tags = {
      Project   = "ARQEDIA"
      ManagedBy = "terraform"
    }
  }
}
