# Applied by the harness to every model request, on input and output.

locals {
  harmful_content = ["HATE", "INSULTS", "SEXUAL", "VIOLENCE", "MISCONDUCT"]

  # Customers should never paste card details into a support chat, and the
  # agent has no use for them.
  card_details = ["CREDIT_DEBIT_CARD_NUMBER", "CREDIT_DEBIT_CARD_CVV", "CREDIT_DEBIT_CARD_EXPIRY"]
}

resource "aws_bedrock_guardrail" "this" {
  name                      = var.name
  description               = "Order support agent: harmful content, prompt attacks, card details, unauthorised discounts"
  blocked_input_messaging   = "Sorry, I can't help with that. I can help with orders, stock, returns and store policies."
  blocked_outputs_messaging = "Sorry, I can't share that. Is there anything else about your order I can help with?"

  content_policy_config {
    dynamic "filters_config" {
      for_each = toset(local.harmful_content)

      content {
        type            = filters_config.value
        input_strength  = "HIGH"
        output_strength = "HIGH"
      }
    }

    # Prompt attacks only make sense on input, so the output strength is NONE.
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }

  sensitive_information_policy_config {
    dynamic "pii_entities_config" {
      for_each = toset(local.card_details)

      content {
        type   = pii_entities_config.value
        action = "BLOCK"
      }
    }
  }

  # The agent can open a return; it has no authority to bargain. Denying the
  # topic stops it being talked into promises the business never made.
  topic_policy_config {
    topics_config {
      name       = "Discounts and compensation"
      type       = "DENY"
      definition = "Requests for discounts, coupons, price matching, vouchers or goodwill compensation beyond the refund described in the store's published policies."
      examples = [
        "Can you give me 20% off for the trouble?",
        "Will you match the price I found on another site?",
        "My parcel was late, can I get a voucher?",
      ]
    }
  }
}

# The harness pins a numbered version, so editing the guardrail above has no
# effect until a new version is cut. Replacing this resource on every change
# cuts one.
resource "aws_bedrock_guardrail_version" "this" {
  guardrail_arn = aws_bedrock_guardrail.this.guardrail_arn
  description   = "Published by Terraform"

  lifecycle {
    replace_triggered_by = [aws_bedrock_guardrail.this]
  }
}
