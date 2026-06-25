# AI Health Check — Bedrock × Datadog MCP

## Arsitektur

```
Streamlit UI (app.py)
    │
    ├── mcp_client.py  ──→  Datadog MCP Server (remote, official)
    │                         tools: get_monitors, search_logs,
    │                                get_services, query_metrics
    │                         [Each call = @tool span in DD LLM Obs]
    │
    ├── bedrock_helper.py ──→  Amazon Bedrock (Nova Micro)
    │                           Region: ap-southeast-3 (Jakarta) 🌏
    │                           + Guardrails (content filtering)
    │                           + Knowledge Base (RAG grounding)
    │                           + Multi-Step ReAct Agent
    │                           [Each call = @llm/@workflow/@task span]
    │
    └── app.py  ──→  Dashboard + Ops Setup
                     + Custom metrics → Datadog
                     + Monitor + Alert + SLO creation
                     + Error handling with DD events
```

---

## ✅ Hackathon Checklist Coverage

| # | Item | Implementation |
|---|------|----------------|
| 1 | 🟢 First Trace | `@llm` decorator on `_invoke_nova` → LLM span in DD |
| 2 | 📊 Dashboard Live | Custom metric `hackathon.ai.health_score` + event stream + 3+ widgets |
| 3 | 🔗 Tool Call Visible | `@tool` decorator on MCP calls → tool spans in DD |
| 4 | 💸 Cost Tracked | `input_tokens`, `output_tokens`, `estimated_cost_usd` in metrics |
| 5 | 🧱 Error Handled | `_handle_error` task + error event to DD + error accumulation monitor |
| 6 | 🚀 End-to-End Demo | workflow → tool → task → LLM spans (see Design doc) |
| 7 | 🎯 Ops Ready | Monitor (runbook) + Alert (escalation) + SLO (99.5% / 7d) |
| B1 | Bedrock Online | `python bedrock_helper.py` shows response in terminal |
| B2 | AWS Knowledge MCP | `.kiro/settings/mcp.json` + design doc in steering |
| B3 | Built with Kiro | `.kiro/specs/` + `.kiro/steering/` present |
| B4 | Multi-Step Agent | ReAct pattern with 2+ reason→act steps |
| B5 | Knowledge Grounded | `retrieve_from_knowledge_base()` tool call |
| B6 | Guardrails On | `apply_guardrails()` blocks harmful prompts |
| B7 | Jakarta In-Region | `AWS_REGION=ap-southeast-3` + model in Jakarta |

---

## Quick Start

### Step 1 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 2 — Configure .env

```bash
cp .env.example .env
# Fill in your keys:
# - DD_API_KEY, DD_APP_KEY
# - AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
# - AWS_REGION=ap-southeast-3
# - BEDROCK_GUARDRAIL_ID (optional)
# - BEDROCK_KNOWLEDGE_BASE_ID (optional)
```

### Step 3 — Verify Bedrock Online (Terminal Demo)

```bash
python bedrock_helper.py
```

This runs:
1. ✅ Bedrock Online check (shows model response)
2. 🧠 Multi-Step Agent demo (shows 2+ reason→act steps)
3. 🛡️ Guardrails demo (shows blocked prompt)

### Step 4 — Run the App

```bash
ddtrace-run streamlit run app.py
```

Or with explicit env vars:
```bash
export DD_LLMOBS_ENABLED=1
export DD_LLMOBS_ML_APP=hackathon-health-checker
export DD_LLMOBS_AGENTLESS_ENABLED=1
ddtrace-run streamlit run app.py
```

### Step 5 — In the App

1. Enter **Datadog API Key** and **App Key** in sidebar
2. Click **🔌 Tes Koneksi MCP** to verify MCP connection
3. Click **🩺 Jalankan Health Check** to run full workflow
4. Click **🎯 Setup Monitor + SLO** to create ops infrastructure
5. Click **🧠 Run Multi-Step Agent** to see ReAct pattern
6. Use **Chat** to ask questions (guardrails applied)

---

## Observability — What You See in Datadog

### LLM Observability Explorer
Complete traces with nested spans:
```
workflow: run_health_check
├── tool: search_datadog_monitors
├── tool: search_datadog_logs
├── tool: search_datadog_services
├── workflow: analyze_health_check
│   ├── llm: invoke_nova_micro (main)
│   └── llm: invoke_nova_micro (services)
└── [error handling if needed]
```

### Custom Dashboard Widgets
1. **Query Value**: `avg:hackathon.ai.health_score{*}` — Current score
2. **Timeseries**: `avg:hackathon.ai.health_score{*}` — Score over time
3. **Event Stream**: `source:bedrock_health_checker` — Events from app
4. **Monitor Status**: Health score + error accumulation monitors

### Monitors & Alerts
- **Health Score Alert**: Triggers when score < 50 (critical) or < 70 (warning)
- **Error Accumulation**: Triggers on 3+ errors in 15 minutes
- **Runbook**: Embedded in monitor message with escalation policy

### SLO
- Target: 99.5% availability over 7 days
- Warning: 99.9%
- Based on health score monitor

---

## File Structure

```
health_check_mcp/
├── app.py                  # Main Streamlit app + workflow
├── bedrock_helper.py       # Bedrock: LLM, Agent, Guardrails, KB
├── mcp_client.py           # Datadog MCP Server client
├── debug_mcp.py            # MCP debug utility
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (not in git)
├── .env.example            # Template for .env
├── .gitignore
├── README.md
└── .kiro/
    ├── settings/
    │   └── mcp.json        # AWS Knowledge MCP config
    ├── steering/
    │   ├── project-standards.md    # Coding standards
    │   └── aws-knowledge-mcp.md   # Design decisions from MCP
    └── specs/
        └── health-check-agent/
            ├── requirements.md     # Functional requirements
            ├── design.md           # Architecture & trace design
            └── tasks.md            # Implementation tasks
```

---

## Troubleshooting

**Error: Bedrock access denied in ap-southeast-3**
- Ensure Nova Micro is enabled in Jakarta region via Bedrock console
- Check IAM policy includes `AmazonBedrockFullAccess`

**Error: MCP connection timeout**
- Verify API Key and App Key are correct
- Ensure App Key has scopes: `monitors_read`, `logs_read`, `metrics_read`

**Guardrails not working**
- Set `BEDROCK_GUARDRAIL_ID` in .env
- Create a guardrail in Bedrock console (Jakarta region)
- Use DRAFT version for testing

**Knowledge Base not responding**
- Set `BEDROCK_KNOWLEDGE_BASE_ID` in .env
- Create a Knowledge Base in Bedrock console with data source
- Ensure the KB is synced and active
