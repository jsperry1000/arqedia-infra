terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region              = "us-east-2"
  profile             = "arqedia"
  allowed_account_ids = ["667523685221"]
}
