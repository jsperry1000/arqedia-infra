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

variable "extraction_model_id" {
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
  description = "Bedrock inference profile for extraction. Bounded structured task, runs per document, so cost-sensitive."
}

variable "composition_model_id" {
  type        = string
  default     = "us.anthropic.claude-sonnet-4-6"
  description = "Bedrock inference profile for composition. Narrative quality matters, runs once per memo."
}
