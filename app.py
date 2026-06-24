"""
app.py
======
AI Health Check Dashboard
Datadog MCP --> Amazon Bedrock Nova Micro --> Streamlit Dashboard
"""

import streamlit as st
import json
from datetime import datetime

from mcp_client import (
    list_available_tools,
    get_monitors,
    search_logs,
    get_metrics_summary,
    get_apm_services,
)
from bedrock_helper import analyze_health_check, chat_with_context

# ── Datadog REST API (hanya untuk kirim metric & event balik) ──
import requests as _requests

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
            "tags": [f"ai_status:{status.lower()}", "source:bedrock_health_checker"]
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
            "tags": ["source:bedrock_health_checker", "env:hackathon"]
        }
    )

# ────────────────────────────────────────────────
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
        index=1 # Defaultnya ke 'past 1 hour'
    )
    
    # PERUBAHAN UI 1: Sembunyikan Query yang teknis ke dalam expander
    with st.expander("⚙️ Advanced Settings (Query)"):
        log_query  = st.text_input("Log Query", value="status:error OR status:warn")
        metric_q   = st.text_input("Metric Query (opsional)",
                                    value="avg:system.cpu.user{*}",
                                    help="Query metric Datadog, kosongkan kalau skip")

    st.markdown("---")

    # ── Tombol: cek koneksi MCP dulu ──
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
                    st.error(f"Gagal konek MCP: {e}")

    st.markdown("---")

    # ── Tombol: jalankan health check ──
    if st.button("🩺 Jalankan Health Check", use_container_width=True, type="primary"):
        if not dd_api_key or not dd_app_key:
            st.error("Isi API Key & App Key dulu!")
        else:
            progress = st.progress(0, text="Memulai...")

            progress.progress(15, text="MCP → get_monitors...")
            try:
                monitors_raw = get_monitors(dd_api_key, dd_app_key)
            except Exception as e:
                monitors_raw = f"Error get_monitors: {e}"

            progress.progress(35, text=f"MCP → search_logs ({timeframe})...")
            try:
                logs_raw = search_logs(dd_api_key, dd_app_key, log_query, timeframe)
            except Exception as e:
                logs_raw = f"Error search_logs: {e}"

            progress.progress(50, text="MCP → get_services...")
            try:
                services_raw = get_apm_services(dd_api_key, dd_app_key)
            except Exception as e:
                services_raw = f"Error get_services: {e}"

            if metric_q.strip():
                # progress.progress(70, text=f"MCP → get_usage_metrics ({timeframe})...")
                # try:
                #     # Nembak metrik bawaan Datadog untuk billing APM & Logs
                #     usage_q = "avg:datadog.estimated_usage.hosts{*} OR avg:datadog.estimated_usage.logs.ingested_bytes{*}"
                #     usage_raw = get_metrics_summary(dd_api_key, dd_app_key, usage_q, timeframe)
                # except Exception as e:
                #     usage_raw = f"Error get_usage: {e}"
                progress.progress(70, text="MCP → get_usage_metrics...")
                try:
                    # Ganti avg jadi max, dan paksa timeframe jadi "past 30 days"
                    usage_q = "max:datadog.estimated_usage.hosts{*}, max:datadog.estimated_usage.apm.hosts{*}, sum:datadog.estimated_usage.synthetics.api_test_runs{*}"
                    usage_raw = get_metrics_summary(dd_api_key, dd_app_key, usage_q, "past 30 days")
                except Exception as e:
                    usage_raw = f"Error get_usage: {e}"
            

            st.session_state.monitors_raw  = monitors_raw
            st.session_state.logs_raw      = logs_raw
            st.session_state.services_raw  = services_raw

            progress.progress(75, text="Bedrock Nova Micro sedang analisis...")
            try:
                health = analyze_health_check(monitors_raw, logs_raw, services_raw, timeframe)
                st.session_state.health_data = health
                st.session_state.last_check  = datetime.now().strftime("%d %b %Y, %H:%M:%S")
            except Exception as e:
                st.error(f"Bedrock error: {e}")
                progress.empty()
                st.stop()

            progress.progress(90, text="Mengirim metric & event ke Datadog...")
            score  = health.get("overall_health_score", 0)
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
            st.success(f"✅ Health check selesai! Metric `hackathon.ai.health_score` sudah masuk ke Datadog.")

    st.markdown("---")
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ── Main: Dashboard ───────────────────────────────
st.title("AI Health Check")

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
    st.stop()

h      = st.session_state.health_data
score  = h.get("overall_health_score", 0)
status = h.get("overall_status", "UNKNOWN")
emoji  = {"HEALTHY": "🟢", "WARNING": "🟡", "CRITICAL": "🔴"}.get(status, "⚪")

# ── Row 1: Metric cards (Full Width) ───────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overall Health Score", f"{score}/100")
c2.metric("Status", f"{emoji} {status}")
c3.metric("Last Check", st.session_state.last_check or "-")
c4.metric("MCP Tools Connected", len(st.session_state.mcp_tools) or "–")

st.info(f"**Summary:** {h.get('summary', '-')}")

# if h.get("finops_insight") and h.get("finops_insight") != "none":
#     st.success(f"💰 **FinOps Insight:** {h.get('finops_insight')}")

if h.get("top_risk") and h["top_risk"] != "none":
    st.warning(f"⚠️ **Top Risk:** {h['top_risk']}")

st.markdown("---")

# ── Row 1.5: Usage Summary ──────────────────────────────
usage = h.get("usage_stats", {})

# ── Status Per-service (Full Width) ──────────────────────
services = h.get("services", [])
if services:
    st.subheader(f"Status per Service ({len(services)} service)")
    cols = st.columns(min(len(services), 4)) # Bisa nampung sampai 4 card sebaris
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

# ── Action items (Full Width) ───────────────────────────
action_items = h.get("action_items", [])
if action_items:
    st.subheader("🛠️ Action Items")
    for i, item in enumerate(action_items, 1):
        st.markdown(f"**{i}.** {item}")
    st.markdown("---")

# ── Raw Data MCP (Full Width) ───────────────────────────
with st.expander("📡 Lihat Raw Data dari Datadog MCP (JSON)"):
    tab1, tab2, tab3, tab4 = st.tabs(["Monitors", "Logs", "Services & Metrics", "Usage"])

    with tab1:
        st.caption("Hasil MCP tool: `get_monitors`")
        st.code(st.session_state.monitors_raw[:3000] or "Tidak ada data", language="json")

    with tab2:
        st.caption("Hasil MCP tool: `search_logs`")
        st.code(st.session_state.logs_raw[:3000] or "Tidak ada data", language="json")

    with tab3:
        st.caption("Hasil MCP tool: `get_services` + `query_metrics`")
        st.code(st.session_state.services_raw[:2000] or "Tidak ada data", language="json")

    # with tab4:
    #     st.caption("Hasil MCP metrik billing (past 30 days)")
    #     st.code(st.session_state.get("usage_raw", "Tidak ada data")[:3000], language="json")

# ── Chat AI (Sticky di bawah) ───────────────────────────
# Menggunakan st.container khusus untuk memisahkan chat dari konten utama
# Agar lebih rapi, kita taruh chat history di dalam expander 
# dan input text di luar agar selalu terlihat.

st.markdown("<br><br><br>", unsafe_allow_html=True) # Memberi ruang agar konten utama tidak tertutup chat

chat_history_container = st.container()

# Menggunakan fitur st.chat_input yang secara default selalu melayang (sticky) di bagian paling bawah layar
if prompt := st.chat_input("Tanya AI tentang optimasi biaya atau analisis log..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Render user prompt
    with chat_history_container:
         with st.expander("💬 Lihat History Chat dengan AI Copilot", expanded=True):
             with st.chat_message("user"):
                 st.markdown(prompt)
             
             # Render assistant response
             with st.chat_message("assistant"):
                 with st.spinner("Nova Micro lagi mikir..."):
                     reply = chat_with_context(
                         prompt,
                         h,
                         st.session_state.monitors_raw,
                         st.session_state.logs_raw
                     )
                     st.markdown(reply)
                     
    st.session_state.messages.append({"role": "assistant", "content": reply})