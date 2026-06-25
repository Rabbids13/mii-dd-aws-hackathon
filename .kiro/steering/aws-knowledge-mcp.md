---
inclusion: manual
---

# AWS Knowledge MCP — Design Decisions

## MCP Configuration
The AWS Documentation MCP Server is configured in `.kiro/settings/mcp.json`.
It provides access to AWS documentation for informed design decisions.

## Question That Shaped Design

**Q: "Which Amazon Bedrock models are available in the Jakarta (ap-southeast-3) region?"**

**Answer from AWS Documentation MCP:**
> Amazon Nova Micro (amazon.nova-micro-v1:0) is available in ap-southeast-3 (Jakarta).
> It supports the Converse API with streaming, tool use, and system prompts.
> Pricing: $0.035/1M input tokens, $0.14/1M output tokens.
> Max tokens: 128K context, 5K output.

**Impact on Design:**
- Chose `amazon.nova-micro-v1:0` as the primary model
- Set default region to `ap-southeast-3` (Jakarta) for in-region compliance
- Used Converse API (not InvokeModel) as recommended for Nova models
- Added cost estimation based on Nova Micro pricing ($0.035/$0.14 per 1M tokens)
- Configured maxTokens to stay within 5K output limit

## Additional Knowledge Used
- Bedrock Guardrails API supports `ApplyGuardrail` for input/output content filtering
- Bedrock Knowledge Base uses `RetrieveAndGenerate` or `Retrieve` API
- ddtrace auto-instruments boto3 calls to Bedrock when `DD_LLMOBS_ENABLED=1`
