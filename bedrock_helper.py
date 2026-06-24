"""
bedrock_helper.py
=================
Semua interaksi dengan Amazon Bedrock Nova Micro.
Otomatis ter-trace ke Datadog LLM Observability lewat ddtrace.
"""

import boto3
import json
import os
import re


def get_bedrock_client():
    return boto3.client(
        service_name="bedrock-runtime",
        region_name="us-east-1"
    )


def _invoke_nova(prompt: str, max_tokens: int = 1200, temperature: float = 0.8) -> str:
    """
    Panggil Amazon Nova Micro via Bedrock.
    Nova Micro pakai format Converse API (bukan invoke_model langsung).
    """
    client = get_bedrock_client()

    response = client.converse(
        modelId="amazon.nova-micro-v1:0",
        messages=[
            {"role": "user", "content": [{"text": prompt}]}
        ],
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature
        }
    )

    return response["output"]["message"]["content"][0]["text"]


def analyze_health_check(
    monitors_raw: str,
    logs_raw: str,
    services_raw: str,
    timeframe: str,
) -> dict:

    prompt = f"""
Kamu adalah AI SRE Copilot. Analisis data Datadog berikut untuk periode {timeframe}.
PENTING: Jangan berikan opini atau peringatan terkait limit, license, atau biaya. Cukup ekstrak angka penggunaannya saja.

=== MONITORS ===
{monitors_raw[:3000]}

=== ERROR LOGS ===
{logs_raw[:3000]}

=== SERVICES ===
{services_raw[:5000]}

Berikan response dalam format JSON STRICT ini:
{{
  "overall_health_score": <angka 0-100>,
  "overall_status": "<HEALTHY|WARNING|CRITICAL>",
  "summary": "<ringkasan situasi teknis tanpa bahas license>",
  "usage_stats": {{
    "infra_hosts": "<angka atau N/A>",
    "apm_hosts": "<angka atau N/A>",
    "synthetics": "<angka atau N/A>"
  }},
  "top_risk": "<risiko terbesar>",
  "services": [
    {{
      "name": "<nama>", "health_score": <0-100>, "status": "<status>", "issue": "<issue>", "action": "<mitigasi>"
    }}
  ],
  "action_items": ["<langkah 1>", "<langkah 2>"]
}}
"""
    raw = _invoke_nova(prompt, max_tokens=2000, temperature=0.0)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Nova Micro kadang masih nambah teks di luar JSON, strip dulu
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        # Fallback kalau parse gagal total
        return {
            "overall_health_score": 0,
            "overall_status": "UNKNOWN",
            "summary": f"Gagal parse response AI: {raw[:300]}",
            "top_risk": "Parse error",
            "services": [],
            "action_items": ["Cek koneksi Bedrock", "Coba jalankan ulang health check"]
        }


def chat_with_context(user_prompt: str, health_data: dict, monitors_raw: str, logs_raw: str) -> str:
    """
    Mode chat freestyle.
    Gunakan data health check terakhir sebagai konteks untuk jawab pertanyaan user.
    """

    prompt = f"""
Kamu adalah L0 SRE AI Assistant yang membantu tim engineering.
Jawab pertanyaan user berdasarkan data health check dan log Datadog berikut.
Format jawaban dengan Markdown. Jangan mengarang — kalau data tidak ada, bilang terus terang.

=== DATA HEALTH CHECK TERAKHIR ===
{json.dumps(health_data, indent=2)[:2000]}

=== RAW MONITORS & LOGS ===
{monitors_raw[:1000]}
{logs_raw[:1000]}

=== PERTANYAAN USER ===
{user_prompt}
"""

    return _invoke_nova(prompt, max_tokens=800, temperature=0.1)
