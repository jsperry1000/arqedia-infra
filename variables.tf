variable "aws_region" {
  type        = string
  default     = "us-east-2"
  description = "Region this stack is deployed into."
}

variable "environment" {
  type        = string
  default     = "dev"
  description = "dev or prod."
}

variable "scope" {
  type        = string
  default     = "shared"
  description = "shared for multi-tenant, dedicated for a regulated single-tenant stack."
}
