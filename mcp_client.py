"""
mcp_client.py
=============
Koneksi ke Datadog MCP Server menggunakan REST HTTP JSON-RPC dengan session ID.
"""

import httpx
import json

DATADOG_MCP_URL = "https://mcp.datadoghq.com/v1/mcp"


def _build_headers(dd_api_key: str, dd_app_key: str) -> dict[str, str]:
    return {
        "DD-API-KEY": dd_api_key,
        "DD-APPLICATION-KEY": dd_app_key,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }


def _call_mcp(dd_api_key: str, dd_app_key: str, method: str, params: dict | None = None) -> dict:
    headers = _build_headers(dd_api_key, dd_app_key)
    with httpx.Client() as client:
        # Step 1: Initialize session and capture session ID from response header
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "streamlit-app", "version": "1.0"},
            },
            "id": 1,
        }
        response = client.post(DATADOG_MCP_URL, headers=headers, json=init_payload)
        response.raise_for_status()
        session_id = response.headers.get("MCP-Session-Id")

        if not session_id:
            raise RuntimeError("MCP server did not return a session ID")

        headers["MCP-Session-Id"] = session_id

        # Step 2: Send initialized notification
        initialized_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        response = client.post(DATADOG_MCP_URL, headers=headers, json=initialized_payload)
        response.raise_for_status()

        # Step 3: Send actual request
        actual_payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": 2,
        }
        if params is not None:
            actual_payload["params"] = params

        response = client.post(DATADOG_MCP_URL, headers=headers, json=actual_payload)
        response.raise_for_status()
        return response.json()


def list_available_tools(dd_api_key: str, dd_app_key: str) -> list[str]:
    """List semua tools yang tersedia di Datadog MCP Server."""
    data = _call_mcp(dd_api_key, dd_app_key, method="tools/list")
    if "error" in data:
        raise RuntimeError(f"MCP error: {json.dumps(data['error'])}")

    result = data.get("result") or {}
    tools = result.get("tools") or []
    return [t.get("name") for t in tools if isinstance(t, dict) and t.get("name")]


def call_mcp_tool(dd_api_key: str, dd_app_key: str, tool_name: str, tool_args: dict) -> str:
    """Memanggil tool spesifik di Datadog MCP Server."""
    result = _call_mcp(
        dd_api_key,
        dd_app_key,
        method="tools/call",
        params={"name": tool_name, "arguments": tool_args},
    )

    if "error" in result:
        return f"Error dari Datadog MCP: {json.dumps(result['error'])}"

    result_body = result.get("result") or {}
    content = result_body.get("content")
    if isinstance(content, list):
        texts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
        return "\n".join(texts)

    return "Tidak ada respons teks dari MCP server."


# ─────────────────────────────────────────────
# Mapping fungsi pembungkus tool (Tetap sama agar app.py tidak rusak)
# ─────────────────────────────────────────────

def get_monitors(dd_api_key: str, dd_app_key: str) -> str:
    """MCP Tool: search_datadog_monitors"""
    return call_mcp_tool(
        dd_api_key, dd_app_key,
        tool_name="search_datadog_monitors",
        tool_args={
            "query": "status:alert OR status:warn",
        }
    )


def search_logs(dd_api_key: str, dd_app_key: str, query: str = "status:error", timeframe: str = "past 1 hour") -> str:
    """MCP Tool: search_datadog_logs dengan timeframe"""
    return call_mcp_tool(
        dd_api_key, dd_app_key,
        tool_name="search_datadog_logs",
        tool_args={
            "query": query,
            "timeframe": timeframe
        }
    )

def get_metrics_summary(dd_api_key: str, dd_app_key: str, metric_query: str, timeframe: str = "past 1 hour") -> str:
    """MCP Tool: search_datadog_metrics dengan timeframe"""
    return call_mcp_tool(
        dd_api_key, dd_app_key,
        tool_name="search_datadog_metrics",
        tool_args={
            "query": metric_query,
            "timeframe": timeframe
        }
    )


def get_apm_services(dd_api_key: str, dd_app_key: str) -> str:
    """MCP Tool: search_datadog_services"""
    return call_mcp_tool(
        dd_api_key, dd_app_key,
        tool_name="search_datadog_services",
        tool_args={}
    )