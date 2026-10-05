variable "name" {
  description = "Prefix for every resource name."
  type        = string
  default     = "order-support"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,20}$", var.name))
    error_message = "Use 3 to 21 lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "region" {
  description = "AWS region. Must support the AgentCore harness, gateway and memory."
  type        = string
  default     = "eu-central-1"
}

variable "model_id" {
  description = "Bedrock inference profile the agent runs on. The eu. profile keeps inference inside EU regions; global. routes worldwide."
  type        = string
  default     = "eu.anthropic.claude-opus-5-5"
}

variable "embedding_model_id" {
  description = "Bedrock embedding model for the policy knowledge base. Its output size must match the vector index dimension."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "embedding_dimensions" {
  description = "Vector size produced by the embedding model."
  type        = number
  default     = 1024
}

variable "return_window_days" {
  description = "Days after delivery during which an order can be returned. Keep in step with knowledge/policies/returns-and-refunds.md."
  type        = number
  default     = 30
}

variable "memory_expiry_days" {
  description = "Days AgentCore Memory keeps conversation events."
  type        = number
  default     = 30
}

variable "log_retention_days" {
  description = "Retention for the tool Lambda's log group."
  type        = number
  default     = 30
}
