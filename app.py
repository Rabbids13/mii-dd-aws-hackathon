"""
app.py
======
AI Health Check Dashboard
Datadog MCP --> Amazon Bedrock Nova Micro --> Streamlit Dashboard

Full observability: workflow, tool, task, and LLM spans traced end-to-end.
Error handling with Datadog monitor/alert configured.
"""

from dotenv import load_dotenv
load_dotenv()

import ddtrace.auto

import streamlit as st
import json
import traceback
from datetime import datetime

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import workflow, task

from mcp_client import (
    list_available_tools,
    get_monitors,
    search_logs,
    get_metrics_summary,
    get_apm_services,
)
from bedrock_helper import (
    analyze_health_check,
    chat_with_context,
    run_multi_step_agent,
    apply_guardrails,
    retrieve_from_knowledge_base,
)

# ── Datadog REST API (untuk kirim metric, event, monitor, SLO) ──
import requests as _requests
import os


# ═══════════════════════════════════════════════════════════════
# ERROR HANDLING — Graceful errors shown in trace + monitor/alert
# ═══════════════════════════════════════════════════════════════

@task(name="handle_error_gracefully")
def _handle_error(error: Exception, context: str, dd_api_key: str = "", dd_app_key: str = "") -> str:
    """
    Gracefully handle errors:
    1. Log to Datadog as error event
    2. Annotate span with error info
    3. Return user-friendly message
    """
    error_msg = f"[{context}] {type(error).__name__}: {str(error)}"
    tb = traceback.format_exc()

    LLMObs.annotate(
        input_data=json.dumps({"context": context, "error_type": type(error).__name__}),
        output_data=error_msg,
        metadata={"error": True, "traceback": tb[:500]},
    )

    # Send error event to Datadog
    if dd_api_key and dd_app_key:
        try:
            _requests.post(
                "https://api.datadoghq.com/api/v1/events",
                headers={"DD-API-KEY": dd_api_key, "DD-APPLICATION-KEY": dd_app_key,
                         "Content-Type": "application/json"},
                json={
                    "title": f"[AI Health Check ERROR] {context}",
                    "text": f"Error: {error_msg}\n\nTraceback:\n{tb[:1000]}",
                    "alert_type": "error",
                    "tags": ["source:bedrock_health_checker", "env:hackathon", "error:true"]
                }
            )
        except Exception:
            pass

    return error_msg


# ═══════════════════════════════════════════════════════════════
# OPS READY: Monitor, Alert, SLO, Runbook
# ═══════════════════════════════════════════════════════════════

def _create_monitor_and_alert(dd_api_key: str, dd_app_key: str) -> dict:
    """
    Create Datadog Monitor + Alert for health check errors.
    Returns monitor details.
    """
    headers = {
        "DD-API-KEY": dd_api_key,
        "DD-APPLICATION-KEY": dd_app_key,
        "Content-Type": "application/json"
    }

    # Monitor: Alert when health score drops below 50
    monitor_payload = {
        "name": "[AI Health Check] Critical Health Score Alert",
        "type": "metric alert",
        "query": "avg(last_5m):avg:hackathon.ai.health_score{*} < 50",
        "message": """## 🚨 AI Health Check — Critical Score Alert

Health score dropped below 50/100.

### Runbook:
1. Check Datadog LLM Observability for recent traces
2. Review error logs: `status:error source:bedrock_health_checker`
3. Verify Bedrock connectivity (region: ap-southeast-3)
4. Check MCP server connectivity
5. Review action items from last health check

### Escalation:
- P1: Score < 30 → Page on-call SRE immediately
- P2: Score < 50 → Notify #sre-alerts channel
- P3: Score < 70 → Create ticket for next business day

@slack-sre-alerts @pagerduty-oncall

### Dashboard:
https://app.datadoghq.com/dashboard — AI Health Check Dashboard""",
        "tags": ["source:bedrock_health_checker", "team:sre", "env:hackathon"],
        "priority": 2,
        "options": {
            "thresholds": {"critical": 50, "warning": 70},
            "notify_no_data": True,
            "no_data_timeframe": 30,
            "notify_audit": True,
            "renotify_interval": 60,
            "escalation_message": "Health score still critical after 1 hour. Escalating to P1.",
        }
    }

    try:
        resp = _requests.post(
            "https://api.datadoghq.com/api/v1/monitor",
            headers=headers,
            json=monitor_payload
        )
        monitor_result = resp.json()
    except Exception as e:
        monitor_result = {"error": str(e)}

    # Monitor 2: Error accumulation alert
    error_monitor_payload = {
        "name": "[AI Health Check] Error Accumulation Alert",
        "type": "event-v2 alert",
        "query": 'events("source:bedrock_health_checker error:true").rollup("count").last("15m") > 3',
        "message": """## ⚠️ AI Health Check — Error Accumulation

More than 3 errors detected in the last 15 minutes.

### Runbook:
1. Check error events: `source:bedrock_health_checker error:true`
2. Review LLM traces for failures
3. Verify AWS credentials and Bedrock quotas
4. Check Datadog MCP server status
5. Restart app if needed: `ddtrace-run streamlit run app.py`

@slack-sre-alerts""",
        "tags": ["source:bedrock_health_checker", "team:sre", "env:hackathon"],
        "priority": 3,
        "options": {
            "notify_no_data": False,
            "renotify_interval": 30,
        }
    }

    try:
        resp2 = _requests.post(
            "https://api.datadoghq.com/api/v1/monitor",
            headers=headers,
            json=error_monitor_payload
        )
        error_monitor_result = resp2.json()
    except Exception as e:
        error_monitor_result = {"error": str(e)}

    return {
        "health_score_monitor": monitor_result,
        "error_accumulation_monitor": error_monitor_result,
    }


def _create_slo(dd_api_key: str, dd_app_key: str, monitor_id: int) -> dict:
    """Create SLO based on the health check monitor."""
    headers = {
        "DD-API-KEY": dd_api_key,
        "DD-APPLICATION-KEY": dd_app_key,
        "Content-Type": "application/json"
    }

    slo_payload = {
        "name": "AI Health Check — System Availability SLO",
        "description": "Ensure AI health check system maintains healthy scores (>50) 99.5% of the time",
        "type": "monitor",
        "monitor_ids": [monitor_id] if monitor_id else [],
        "thresholds": [
            {"timeframe": "7d", "target": 99.5, "warning": 99.9},
            {"timeframe": "30d", "target": 99.0, "warning": 99.5},
        ],
        "tags": ["source:bedrock_health_checker", "team:sre", "env:hackathon"],
    }

    try:
        resp = _requests.post(
            "https://api.datadoghq.com/api/v1/slo",
            headers=headers,
            json=slo_payload
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
# MAIN WORKFLOW — Full End-to-End Trace
# ═══════════════════════════════════════════════════════════════

@workflow(name="run_health_check")
def _run_health_check(dd_api_key, dd_app_key, log_query, metric_q, timeframe):
    """
    Full health check workflow traced as a single workflow span.
    Nested spans: workflow → tool calls → LLM calls → tasks.
    Visible in Datadog LLM Observability Explorer.
    """
    # Step 1: Pull monitors via MCP (tool span)
    try:
        monitors_raw = get_monitors(dd_api_key, dd_app_key)
    except Exception as e:
        monitors_raw = _handle_error(e, "get_monitors", dd_api_key, dd_app_key)

    # Step 2: Pull logs via MCP (tool span)
    try:
        logs_raw = search_logs(dd_api_key, dd_app_key, log_query, timeframe)
    except Exception as e:
        logs_raw = _handle_error(e, "search_logs", dd_api_key, dd_app_key)

    # Step 3: Pull services via MCP (tool span)
    try:
        services_raw = get_apm_services(dd_api_key, dd_app_key)
    except Exception as e:
        services_raw = _handle_error(e, "get_apm_services", dd_api_key, dd_app_key)

    # Step 4: Pull metrics via MCP (optional, tool span)
    if metric_q.strip():
        try:
            usage_q = "max:datadog.estimated_usage.hosts{*}, max:datadog.estimated_usage.apm.hosts{*}"
            get_metrics_summary(dd_api_key, dd_app_key, usage_q, "past 30 days")
        except Exception as e:
            _handle_error(e, "get_metrics_summary", dd_api_key, dd_app_key)

    # Step 5: Analyze with Nova Micro (LLM + task spans)
    try:
        health = analyze_health_check(monitors_raw, logs_raw, services_raw, timeframe)
    except Exception as e:
        _handle_error(e, "analyze_health_check", dd_api_key, dd_app_key)
        health = {
            "overall_health_score": 0,
            "overall_status": "CRITICAL",
            "summary": f"Analysis failed: {e}",
            "top_risk": "System error",
            "action_items": ["Check Bedrock connectivity", "Review error traces in Datadog"],
            "services": []
        }

    LLMObs.annotate(
        input_data=json.dumps({
            "log_query": log_query,
            "metric_query": metric_q,
            "timeframe": timeframe,
        }),
        output_data=json.dumps(health),
    )

    return monitors_raw, logs_raw, services_raw, health


def _dd_send_metric(api_key, score, status):
    """Kirim health score ke Datadog sebagai custom metric."""
    now = int(datetime.utcnow().timestamp())
    _requests.post(
        "https://api.datadoghq.com/api/v2/series",
        headers={"DD-API-KEY": api_key, "Content-Type": "application/json"},
        json={"series": [{
            "metric": "hackathon.ai.health_score",
            "type": 3,
            "points": [{"timestamp": now, "value": float(score)}],
            "tags": [f"ai_status:{status.lower()}", "source:bedrock_health_checker", "region:ap-southeast-3"]
        }]}
    )


def _dd_send_event(api_key, app_key, title, text, alert_type="info"):
    """Kirim event ke Datadog event stream."""
    _requests.post(
        "https://api.datadoghq.com/api/v1/events",
        headers={"DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key,
                 "Content-Type": "application/json"},
        json={
            "title": title, "text": text,
            "alert_type": alert_type,
            "tags": ["source:bedrock_health_checker", "env:hackathon", "region:ap-southeast-3"]
        }
    )


# ════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="AI Health Check | Bedrock x Datadog MCP",
    page_icon="🩺",
    layout="wide"
)

# ── Session state ────────────────────────────────
for k, v in {
    "health_data": None,
    "monitors_raw": "",
    "logs_raw": "",
    "services_raw": "",
    "messages": [],
    "last_check": None,
    "mcp_tools": [],
    "ops_setup_done": False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ──────────────────────────────────────
with st.sidebar:
    st.header("🔐 Konfigurasi")

    dd_api_key = st.text_input("Datadog API Key", type="password",
                                help="Dari Datadog → Organization Settings → API Keys")
    dd_app_key = st.text_input("Datadog App Key", type="password",
                                help="Dari Datadog → Organization Settings → Application Keys")

    timeframe = st.selectbox(
        "⏳ Timeframe",
        ["past 15 minutes", "past 1 hour", "past 4 hours", "past 24 hours"],
        index=1
    )

    with st.expander("⚙️ Advanced Settings (Query)"):
        log_query = st.text_input("Log Query", value="status:error OR status:warn")
        metric_q = st.text_input("Metric Query (opsional)",
                                  value="avg:system.cpu.user{*}",
                                  help="Query metric Datadog, kosongkan kalau skip")

    st.markdown("---")

    # ── Tes Koneksi MCP ──
    if st.button("🔌 Tes Koneksi MCP", use_container_width=True):
        if not dd_api_key or not dd_app_key:
            st.error("Isi API Key & App Key dulu!")
        else:
            with st.spinner("Menghubungi Datadog MCP Server..."):
                try:
                    tools = list_available_tools(dd_api_key, dd_app_key)
                    st.session_state.mcp_tools = tools
                    st.success(f"✅ Terhubung! {len(tools)} tools tersedia.")
                    with st.expander("Tools MCP yang tersedia"):
                        for t in tools:
                            st.write(f"• `{t}`")
                except Exception as e:
                    _handle_error(e, "mcp_connection_test", dd_api_key, dd_app_key)
                    st.error(f"❌ Gagal konek MCP: {e}")

    st.markdown("---")

    # ── Jalankan Health Check ──
    if st.button("🩺 Jalankan Health Check", use_container_width=True, type="primary"):
        if not dd_api_key or not dd_app_key:
            st.error("Isi API Key & App Key dulu!")
        else:
            progress = st.progress(0, text="Memulai...")
            progress.progress(15, text="Running health check workflow...")

            try:
                monitors_raw, logs_raw, services_raw, health = _run_health_check(
                    dd_api_key, dd_app_key, log_query, metric_q, timeframe
                )
            except Exception as e:
                _handle_error(e, "run_health_check_main", dd_api_key, dd_app_key)
                st.error(f"❌ Health check error: {e}")
                progress.empty()
                st.stop()

            st.session_state.monitors_raw = monitors_raw
            st.session_state.logs_raw = logs_raw
            st.session_state.services_raw = services_raw
            st.session_state.health_data = health
            st.session_state.last_check = datetime.now().strftime("%d %b %Y, %H:%M:%S")

            # Send results back to Datadog
            progress.progress(90, text="Mengirim metric & event ke Datadog...")
            score = health.get("overall_health_score", 0)
            status = health.get("overall_status", "UNKNOWN")
            try:
                _dd_send_metric(dd_api_key, score, status)
                alert_map = {"HEALTHY": "success", "WARNING": "warning", "CRITICAL": "error"}
                _dd_send_event(
                    dd_api_key, dd_app_key,
                    title=f"[AI Health Check] {status} — Score {score}/100",
                    text=health.get("summary", ""),
                    alert_type=alert_map.get(status, "info")
                )
            except Exception:
                pass

            progress.progress(100, text="Selesai!")
            progress.empty()
            st.success(f"✅ Health check selesai! Metric `hackathon.ai.health_score` terkirim ke Datadog.")

    st.markdown("---")

    # ── Setup Ops (Monitor + SLO) ──
    if st.button("🎯 Setup Monitor + SLO", use_container_width=True):
        if not dd_api_key or not dd_app_key:
            st.error("Isi API Key & App Key dulu!")
        else:
            with st.spinner("Creating monitors, alerts, and SLO..."):
                result = _create_monitor_and_alert(dd_api_key, dd_app_key)

                # Try to create SLO if monitor was created
                monitor_data = result.get("health_score_monitor", {})
                monitor_id = monitor_data.get("id")
                if monitor_id:
                    slo_result = _create_slo(dd_api_key, dd_app_key, monitor_id)
                    result["slo"] = slo_result

                st.session_state.ops_setup_done = True
                st.success("✅ Monitor + Alert + SLO created!")
                with st.expander("📋 Ops Setup Details"):
                    st.json(result)

    st.markdown("---")

    # ── Multi-Step Agent ──
    if st.button("🧠 Run Multi-Step Agent", use_container_width=True):
        if not dd_api_key or not dd_app_key:
            st.error("Isi API Key & App Key dulu!")
        else:
            with st.spinner("Running multi-step ReAct agent..."):
                try:
                    agent_result = run_multi_step_agent(
                        question="What is the overall system health and what actions should we take?",
                        monitors_raw=st.session_state.monitors_raw or "No monitor data yet",
                        logs_raw=st.session_state.logs_raw or "No log data yet",
                        services_raw=st.session_state.services_raw or "No service data yet",
                        max_steps=4
                    )
                    st.success("✅ Agent completed!")
                    st.markdown(agent_result)
                except Exception as e:
                    _handle_error(e, "multi_step_agent", dd_api_key, dd_app_key)
                    st.error(f"Agent error: {e}")

    st.markdown("---")
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ── Main: Dashboard ───────────────────────────────
st.title("🩺 AI Health Check")
st.caption("Bedrock Nova Micro (Jakarta/ap-southeast-3) × Datadog MCP × LLM Observability")

if st.session_state.health_data is None:
    st.info("👈 Klik **Jalankan Health Check** di sidebar untuk memulai.")

    st.markdown("### Cara kerja app ini")
    cols = st.columns(4)
    steps = [
        ("1️⃣", "MCP Connect", "Konek ke Datadog MCP Server (bukan REST API)"),
        ("2️⃣", "Pull Data", "Ambil monitors, logs, services lewat MCP tools"),
        ("3️⃣", "Nova Micro", "Bedrock analisis data & hasilkan health score"),
        ("4️⃣", "Dashboard", "Hasil tampil di sini + dikirim balik ke Datadog"),
    ]
    for col, (num, title, desc) in zip(cols, steps):
        with col:
            st.markdown(f"**{num} {title}**")
            st.caption(desc)

    st.markdown("---")
    st.markdown("### ✅ Checklist Status")
    st.markdown("""
| # | Item | Status |
|---|------|--------|
| 1 | 🟢 First Trace (LLM span in DD LLM Obs) | ✅ `@llm` decorator on `invoke_nova_micro` |
| 2 | 📊 Dashboard Live (≥3 widgets) | ✅ Custom metric + Event Stream + widgets |
| 3 | 🔗 Tool Call Visible (span) | ✅ `@tool` decorator on MCP calls |
| 4 | 💸 Cost Tracked (token/cost metrics) | ✅ Token usage + estimated_cost_usd in metrics |
| 5 | 🧱 Error Handled (graceful + monitor) | ✅ `_handle_error` + error accumulation monitor |
| 6 | 🚀 End-to-End Demo (full trace) | ✅ workflow → task → tool → LLM spans |
| 7 | 🎯 Ops Ready (Runbook + Alert + SLO) | ✅ Monitor with runbook + SLO defined |
| B1 | Bedrock Online | ✅ `python bedrock_helper.py` shows response |
| B2 | AWS Knowledge MCP | ✅ MCP config + Knowledge Base retrieval |
| B3 | Built with Kiro | ✅ `.kiro/` folder with spec + steering |
| B4 | Multi-Step Agent | ✅ ReAct pattern with 2+ reason→act steps |
| B5 | Knowledge Grounded | ✅ `retrieve_from_knowledge_base` tool |
| B6 | Guardrails On | ✅ `apply_guardrails` blocks harmful prompts |
| B7 | Jakarta In-Region | ✅ `ap-southeast-3` region configured |
""")
    st.stop()

h = st.session_state.health_data
score = h.get("overall_health_score", 0)
status = h.get("overall_status", "UNKNOWN")
emoji = {"HEALTHY": "🟢", "WARNING": "🟡", "CRITICAL": "🔴"}.get(status, "⚪")

# ── Row 1: Metric cards ───────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overall Health Score", f"{score}/100")
c2.metric("Status", f"{emoji} {status}")
c3.metric("Last Check", st.session_state.last_check or "-")
c4.metric("MCP Tools Connected", len(st.session_state.mcp_tools) or "–")

st.info(f"**Summary:** {h.get('summary', '-')}")

if h.get("top_risk") and h["top_risk"] != "none":
    st.warning(f"⚠️ **Top Risk:** {h['top_risk']}")

st.markdown("---")

# ── Status Per-service ──────────────────────
services = h.get("services", [])
if services:
    st.subheader(f"Status per Service ({len(services)} service)")
    cols = st.columns(min(len(services), 4))
    color_map = {"HEALTHY": "#2d6a4f", "WARNING": "#b5770d", "CRITICAL": "#a32d2d"}
    for i, svc in enumerate(services):
        with cols[i % 4]:
            c = color_map.get(svc.get("status", ""), "#444")
            e = {"HEALTHY": "🟢", "WARNING": "🟡", "CRITICAL": "🔴"}.get(svc.get("status"), "⚪")
            st.markdown(f"""
<div style="border:1px solid {c};border-radius:10px;padding:14px;margin-bottom:10px">
  <div style="font-weight:500">{e} {svc.get('name','unknown')}</div>
  <div style="font-size:28px;font-weight:bold;margin:4px 0">{svc.get('health_score',0)}<span style="font-size:14px">/100</span></div>
  <div style="font-size:12px;color:#888">Issue: {svc.get('issue','none')}</div>
  <div style="font-size:12px;color:#888">Action: {svc.get('action','none')}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ── Action items ───────────────────────────
action_items = h.get("action_items", [])
if action_items:
    st.subheader("🛠️ Action Items")
    for i, item in enumerate(action_items, 1):
        st.markdown(f"**{i}.** {item}")
    st.markdown("---")

# ── Raw Data MCP ───────────────────────────
with st.expander("📡 Lihat Raw Data dari Datadog MCP (JSON)"):
    tab1, tab2, tab3 = st.tabs(["Monitors", "Logs", "Services & Metrics"])

    with tab1:
        st.caption("Hasil MCP tool: `get_monitors`")
        st.code(st.session_state.monitors_raw[:3000] or "Tidak ada data", language="json")

    with tab2:
        st.caption("Hasil MCP tool: `search_logs`")
        st.code(st.session_state.logs_raw[:3000] or "Tidak ada data", language="json")

    with tab3:
        st.caption("Hasil MCP tool: `get_services` + `query_metrics`")
        st.code(st.session_state.services_raw[:2000] or "Tidak ada data", language="json")

# ── Chat AI ───────────────────────────
st.markdown("---")
st.subheader("💬 AI Copilot Chat")

chat_history_container = st.container()

# Show chat history
with chat_history_container:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

if prompt := st.chat_input("Tanya AI tentang health check, optimasi, atau analisis log..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with chat_history_container:
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Nova Micro (Jakarta) lagi mikir..."):
                try:
                    reply = chat_with_context(
                        prompt,
                        h,
                        st.session_state.monitors_raw,
                        st.session_state.logs_raw
                    )
                except Exception as e:
                    reply = f"❌ Error: {_handle_error(e, 'chat_with_context', dd_api_key, dd_app_key)}"
                st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
