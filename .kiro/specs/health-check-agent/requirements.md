# Requirements — AI Health Check Agent

## Overview
Build an AI-powered health check dashboard that integrates Amazon Bedrock (Nova Micro) with Datadog MCP Server for real-time infrastructure monitoring and automated analysis.

## Functional Requirements

### FR-1: Datadog MCP Integration
- Connect to Datadog MCP Server via JSON-RPC over HTTP
- Pull monitors, logs, services, and metrics data
- Each MCP tool call must be traced as a tool span in Datadog LLM Observability

### FR-2: Bedrock LLM Analysis
- Use Amazon Nova Micro (amazon.nova-micro-v1:0) in Jakarta region (ap-southeast-3)
- Analyze monitor/log/service data and produce a health score (0-100)
- Track token usage and estimated cost per invocation

### FR-3: Multi-Step ReAct Agent
- Implement Reason→Act pattern with 2+ sequential steps per request
- Agent should be able to: analyze_monitors, analyze_logs, analyze_services, check_knowledge_base, provide_answer
- Full trace visible in Datadog LLM Observability Explorer

### FR-4: Knowledge Base Grounding
- Integrate Amazon Bedrock Knowledge Base for RAG retrieval
- Agent can retrieve proprietary/internal data to ground its responses
- Retrieval calls visible as tool spans

### FR-5: Bedrock Guardrails
- Apply Bedrock Guardrails to filter harmful/blocked prompts
- Blocked prompts show clear feedback to user
- Guardrail checks visible as tool spans in trace

### FR-6: Error Handling & Alerting
- Graceful error handling with user-friendly messages
- Errors logged to Datadog as events with appropriate tags
- Error accumulation monitor configured to alert on-call team

### FR-7: Ops Readiness
- Datadog Monitor with runbook for health score alerts
- SLO defined (99.5% availability over 7 days)
- Alert escalation policy to on-call team via Slack/PagerDuty

## Non-Functional Requirements

### NFR-1: Observability
- Complete end-to-end traces with decorators: @workflow, @tool, @task, @llm
- Token/cost metrics on every LLM span
- Custom dashboard with ≥3 widgets in Datadog

### NFR-2: Region Compliance
- All Bedrock calls must use Jakarta region (ap-southeast-3)
- Model must be available in Jakarta: amazon.nova-micro-v1:0

### NFR-3: Security
- API keys stored in environment variables, never hardcoded
- Guardrails block prompt injection and harmful content
