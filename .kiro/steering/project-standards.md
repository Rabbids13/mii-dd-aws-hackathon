# Project Standards — AI Health Check (Bedrock × Datadog MCP)

## Architecture

This is a Streamlit-based AI Health Check dashboard that:
1. Connects to Datadog MCP Server (remote, official) for monitors/logs/services data
2. Uses Amazon Bedrock Nova Micro (ap-southeast-3 Jakarta) for AI analysis
3. Sends health metrics back to Datadog for observability
4. Full LLM Observability tracing with ddtrace decorators

## Technology Stack
- **Frontend**: Streamlit
- **LLM**: Amazon Bedrock Nova Micro (amazon.nova-micro-v1:0)
- **Region**: ap-southeast-3 (Jakarta)
- **Observability**: Datadog LLM Observability (ddtrace)
- **MCP**: Datadog MCP Server (remote JSON-RPC over HTTP)
- **Guardrails**: Amazon Bedrock Guardrails
- **Knowledge Base**: Amazon Bedrock Knowledge Base (RAG)

## Coding Standards
- All LLM calls must be decorated with `@llm` from ddtrace
- All tool calls must be decorated with `@tool` from ddtrace
- All workflows must be decorated with `@workflow` from ddtrace
- All sub-tasks must be decorated with `@task` from ddtrace
- Errors must be handled gracefully and logged to Datadog
- Token usage and cost must be tracked in every LLM call

## File Structure
- `app.py` — Main Streamlit dashboard + workflow orchestration
- `bedrock_helper.py` — All Bedrock interactions (LLM, Guardrails, KB, Agent)
- `mcp_client.py` — Datadog MCP Server client (JSON-RPC)
- `debug_mcp.py` — Debug utility for MCP connection testing

## Observability Requirements
- Every user action must produce a complete trace in Datadog
- Traces must include: workflow → tool → task → LLM spans
- Token/cost metrics must be annotated on every LLM span
- Errors must trigger alerts via configured monitors
