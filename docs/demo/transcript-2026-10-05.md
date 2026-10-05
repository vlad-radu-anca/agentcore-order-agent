# Demo transcript, 5 October 2026

A single `make chat` session against the deployed stack, using the sample data from `make seed`.

- Region: `us-west-2`
- Model: Claude Opus 4.6 (`us.anthropic.claude-opus-4-6-v1`). The repository default is Opus 5.5, which was not yet enabled on the account used for this run.
- `[tool]` lines are printed by `scripts/chat.py` when the agent calls a gateway tool; `[guardrail intervened]` when the Bedrock Guardrail blocks a turn.

The agent's replies are reproduced exactly as returned; only blank lines between turns were normalised.

```text
you> Hi, where is my order ORD-1001? My email is alex@example.com
agent> Let me look that up for you right away.
  [tool] order-tools___get_order
Your order ORD-1001 has been **delivered** — it arrived on 30 September 2026.

Here's a quick summary of what was in it:
- 1 × Aluminium 75% mechanical keyboard — €149.00
- 2 × Braided USB-C cable, 2 m — €12.50 each
- Order total: €174.00

Is there anything else I can help you with?

you> I'd like to return it, the keyboard is too loud for my office
agent> Just to confirm: you'd like to return the full order ORD-1001 because the keyboard is too loud for your office. A return request covers the whole order, and the refund (€174.00) would be issued once the items are received back — no money moves until then.

Shall I go ahead and open the return?

you> Can I also return ORD-1002?
agent> Sure, I can look into that. Could you give me the email address you used when placing ORD-1002? Is it the same alex@example.com, or a different one?

you> How long will my refund take?
agent> Let me check the store's refund policy for you.
  [tool] order-tools___search_policies
Refunds are issued to your original payment method within **5 business days** of the returned parcel arriving at our warehouse. Your bank may then take an additional 3–5 business days to show the credit on your account.

Now, back to your two open items:

1. **ORD-1001** — shall I go ahead and open the return for the keyboard being too loud?
2. **ORD-1002** — what email address was that order placed with so I can look it up?

you> Is the wireless mouse MS-WL-02 back in stock?
agent> Let me check that for you, and I still have your two return questions open — I'll come back to those right after.
  [tool] order-tools___check_inventory
The Wireless ergonomic mouse (MS-WL-02) is currently out of stock. It's expected to be restocked on 17 October 2026.

Back to your returns:

1. **ORD-1001** — I'm ready to open the return (reason: keyboard too loud for office) whenever you give the go-ahead.
2. **ORD-1002** — I still need the email address that order was placed with. Is it alex@example.com or a different one?

you> Can you give me 20% off for the trouble?
agent> Sorry, I can't help with that. I can help with orders, stock, returns and store policies.
  [guardrail intervened]

you> Yes, please open the return
agent>   [tool] order-tools___request_return
The return is open. Here are the details:

- **Return ID:** RET-FA5115A7FB
- **Refund amount:** €174.00 (to your original payment method, within 5 business days of the items reaching our warehouse)

You'll receive a prepaid shipping label by email within one business day. Pack everything up with all accessories and original packaging, attach the label, and drop it off at any carrier point within 14 days.

Still need help with ORD-1002? Just let me know the email address it was placed with and I'll look it up.
```

## What each turn shows

| Turn | Behaviour | Where it comes from |
| --- | --- | --- |
| 1 | Looks the order up only once it has both the order number and the email | `get_order` and the system prompt |
| 2 | Restates the order, the reason and the refund, and asks before acting | The confirm-first rule in `prompts/system.md` |
| 3 | Asks for the email rather than assuming it | The system prompt: an order lookup needs both details |
| 4 | Answers refund timing from the policy document, not general knowledge | `search_policies` over the Bedrock Knowledge Base |
| 5 | Reports stock and the restock date | `check_inventory` |
| 6 | Refuses a discount with the guardrail's message | The denied topic in `infra/guardrail.tf` |
| 7 | Opens the return only after the customer confirms, and reports the return ID and refund amount from DynamoDB. The shipping label and 14 day drop-off come from the returns policy it retrieved earlier | `request_return` and the knowledge base |

Across turns 3 to 7 the agent keeps track of both unfinished requests, which is the harness's conversation memory. The guardrail blocking turn 6 did not end the conversation: turn 7 picks up the pending return.

Not shown in this session: the closed return window for ORD-1002, since the customer never supplied its email. That path is covered by the unit tests in `tests/test_tools.py`.
