# Tasks — AI Health Check Agent

## Task 1: Setup Bedrock Integration (Jakarta Region)
- [x] Configure boto3 client for ap-southeast-3 (Jakarta)
- [x] Implement Converse API call with Nova Micro
- [x] Add token tracking and cost estimation
- [x] Add @llm decorator for LLM Observability tracing
- [x] Verify model availability in Jakarta region

## Task 2: Implement Datadog MCP Client
- [x] Implement JSON-RPC session management with session ID
- [x] Add @tool decorator on all MCP tool calls
- [x] Implement wrapper functions: get_monitors, search_logs, get_apm_services, get_metrics_summary
- [x] Handle MCP errors gracefully

## Task 3: Build Health Check Workflow
- [x] Create main `_run_health_check` with @workflow decorator
- [x] Orchestrate MCP data pull → Bedrock analysis → metric send
- [x] Implement batching for service analysis
- [x] Add LLMObs annotations with input/output data

## Task 4: Implement Multi-Step ReAct Agent
- [x] Create `_agent_reason` with @task decorator
- [x] Create `_agent_act` with @task decorator
- [x] Implement `run_multi_step_agent` with @workflow decorator
- [x] Support 2+ sequential reason→act steps per request
- [x] Parse THOUGHT/ACTION/ACTION_INPUT from LLM output

## Task 5: Add Knowledge Base Integration
- [x] Implement `retrieve_from_knowledge_base` with @tool decorator
- [x] Integrate KB retrieval into agent act step
- [x] Integrate KB retrieval into chat_with_context
- [x] Handle missing KB configuration gracefully

## Task 6: Add Bedrock Guardrails
- [x] Implement `apply_guardrails` with @tool decorator
- [x] Apply guardrails check before chat responses
- [x] Show blocked message to user when content is filtered
- [x] Handle missing guardrail configuration gracefully

## Task 7: Error Handling & Alerting
- [x] Create `_handle_error` with @task decorator
- [x] Log errors as Datadog events with proper tags
- [x] Create health score monitor with runbook
- [x] Create error accumulation monitor with alert
- [x] Add escalation policy in monitor message

## Task 8: Ops Readiness (Monitor + SLO)
- [x] Create monitor: health score < 50 → critical alert
- [x] Create monitor: error accumulation > 3 in 15m
- [x] Add runbook in monitor message
- [x] Create SLO: 99.5% availability over 7 days
- [x] Configure alert routing to Slack + PagerDuty

## Task 9: Streamlit Dashboard
- [x] Health score card + status indicator
- [x] Per-service health cards
- [x] Action items list
- [x] Raw MCP data viewer
- [x] AI Copilot chat with guardrails
- [x] Multi-step agent trigger button
- [x] Ops setup button (monitor + SLO creation)

## Task 10: Terminal Demo Scripts
- [x] `demo_bedrock_online()` — Shows successful Bedrock response
- [x] `demo_multi_step_agent()` — Shows 2+ reason→act steps
- [x] `demo_guardrails()` — Shows blocked prompt filtering
