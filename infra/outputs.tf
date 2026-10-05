output "harness_arn" {
  description = "Pass to scripts/chat.py, or to InvokeHarness."
  value       = aws_bedrockagentcore_harness.this.arn
}

output "gateway_url" {
  description = "MCP endpoint of the tool gateway. Requires SigV4."
  value       = aws_bedrockagentcore_gateway.this.gateway_url
}

output "orders_table" {
  description = "DynamoDB table holding orders and return requests."
  value       = aws_dynamodb_table.orders.name
}

output "inventory_table" {
  description = "DynamoDB table holding stock levels."
  value       = aws_dynamodb_table.inventory.name
}

output "knowledge_base_id" {
  description = "Policy knowledge base, for StartIngestionJob."
  value       = aws_bedrockagent_knowledge_base.policies.id
}

output "data_source_id" {
  description = "S3 data source of the policy knowledge base, for StartIngestionJob."
  value       = aws_bedrockagent_data_source.policies.data_source_id
}
