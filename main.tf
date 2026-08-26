locals {
  name_prefix = "arqedia-${var.environment}"
}

output "region" {
  value = var.aws_region
}

output "name_prefix" {
  value = local.name_prefix
}
