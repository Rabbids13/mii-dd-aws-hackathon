# Design — AI Health Check Agent

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI (app.py)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │Health Card│  │Service   │  │Action    │  │AI Copilot Chat│  │
│  │Dashboard │  │Status    │  │Items     │  │               │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────────┐
│ mcp_client  │  │bedrock_helper│  │ Datadog REST API│
│ (JSON-RPC)  │  │ (Converse)  │  │ (metrics/events)│
└──────┬──────┘  └──────┬──────┘  └────────┬────────┘
       │                 │                   │
       ▼                 ▼                   ▼
┌─────────────┐  ┌─────────────────┐  ┌──────────┐
│ Datadog MCP │  │ Amazon Bedrock  │  │ Datadog  │
│ Server      │  │ Nova Micro      │  │ Platform │
│ (Remote)    │  │ (ap-southeast-3)│  │          │
└─────────────┘  │ + Guardrails    │  └──────────┘
                 │ + Knowledge Base│
                 └─────────────────┘
```

## Trace Structure (End-to-End)

```
workflow: run_health_check
├── tool: get_monitors (MCP)
├── tool: search_logs (MCP)
├── tool: get_apm_services (MCP)
├── tool: get_metrics_summary (MCP)
├── workflow: analyze_health_check
│   ├── llm: invoke_nova_micro (main analysis)
│   └── llm: invoke_nova_micro (service batching)
└── task: handle_error_gracefully (if error)

workflow: multi_step_agent
├── task: agent_reason_step (Step 1)
│   └── llm: invoke_nova_micro
├── task: agent_act_step (Step 1)
│   └── tool: retrieve_from_knowledge_base (optional)
├── task: agent_reason_step (Step 2)
│   └── llm: invoke_nova_micro
├── task: agent_act_step (Step 2)
└── llm: invoke_nova_micro (final synthesis)

workflow: chat_with_context
├── tool: apply_guardrails
├── tool: retrieve_from_knowledge_base (optional)
└── llm: invoke_nova_micro
```

## Component Design

### bedrock_helper.py
- `get_bedrock_client()` — Boto3 client for ap-southeast-3
- `_invoke_nova()` — Core LLM call with @llm decorator, token tracking, cost estimation
- `apply_guardrails()` — Bedrock Guardrails content filtering
- `retrieve_from_knowledge_base()` — RAG retrieval from Bedrock KB
- `run_multi_step_agent()` — ReAct agent with reason→act loop
- `analyze_health_check()` — Health score analysis workflow
- `chat_with_context()` — Chat with guardrails + KB grounding

### mcp_client.py
- `_call_mcp()` — JSON-RPC session management
- `call_mcp_tool()` — Generic tool invocation with LLMObs tool span
- Wrapper functions: get_monitors, search_logs, get_apm_services, get_metrics_summary

### app.py
- `_run_health_check()` — Main orchestration workflow
- `_handle_error()` — Graceful error handling with Datadog event
- `_create_monitor_and_alert()` — Ops setup: monitors + runbook
- `_create_slo()` — SLO definition
- Streamlit UI: sidebar config, dashboard, chat

## Data Flow
1. User clicks "Health Check" → `_run_health_check` workflow starts
2. MCP tools pull data (4 tool spans)
3. Bedrock analyzes data (2+ LLM spans)
4. Results displayed in UI + sent to Datadog (metric + event)
5. Complete trace visible in LLM Observability Explorer
