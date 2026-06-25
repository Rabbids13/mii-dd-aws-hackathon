"""
bedrock_helper.py
=================
Semua interaksi dengan Amazon Bedrock Nova Micro.
Traced ke Datadog LLM Observability lewat ddtrace decorators + auto-instrumentation.
"""

import boto3
import json
import os
import re
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import llm, workflow


def get_bedrock_client():
    return boto3.client(
        service_name="bedrock-runtime",
        region_name=os.environ.get("AWS_REGION", "us-east-1")
    )


@llm(model_name="amazon.nova-micro-v1:0", model_provider="amazon_bedrock", name="invoke_nova_micro")
def _invoke_nova(prompt: str, max_tokens: int = 4000, temperature: float = 0.8) -> str:
    """
    Panggil Amazon Nova Micro via Bedrock.
    Nova Micro pakai format Converse API (bukan invoke_model langsung).
    """
    client = get_bedrock_client()

    LLMObs.annotate(
        input_data=[{"role": "user", "content": prompt}],
        metadata={"max_tokens": max_tokens, "temperature": temperature},
    )

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

    output_text = response["output"]["message"]["content"][0]["text"]

    # Extract token usage if available
    usage = response.get("usage", {})
    metrics = {}
    if usage.get("inputTokens"):
        metrics["input_tokens"] = usage["inputTokens"]
    if usage.get("outputTokens"):
        metrics["output_tokens"] = usage["outputTokens"]
    if usage.get("totalTokens"):
        metrics["total_tokens"] = usage["totalTokens"]
    elif metrics.get("input_tokens") and metrics.get("output_tokens"):
        metrics["total_tokens"] = metrics["input_tokens"] + metrics["output_tokens"]

    LLMObs.annotate(
        output_data=[{"role": "assistant", "content": output_text}],
        metrics=metrics if metrics else None,
    )

    return output_text


@workflow(name="analyze_health_check")
def analyze_health_check(
    monitors_raw: str,
    logs_raw: str,
    services_raw: str,
    timeframe: str
) -> dict:
    """
    Kirim data MCP Datadog ke Nova Micro dengan teknik BATCHING (Operasi Berulang).
    Memisahkan pencarian Health Score utama dengan ekstraksi daftar Service.
    """

    # --- TAHAP 1: PROMPT UTAMA (Health Score & Action Items) ---
    prompt_main = f"""
Kamu adalah AI SRE Copilot. Analisis data Datadog berikut untuk periode {timeframe}.

=== MONITORS ===
{monitors_raw[:3000]}

=== ERROR LOGS ===
{logs_raw[:3000]}

Berikan response dalam format JSON STRICT ini (TANPA memasukkan list service):
{{
  "overall_health_score": <angka 0-100>,
  "overall_status": "<HEALTHY|WARNING|CRITICAL>",
  "summary": "<ringkasan situasi teknis>",
  "top_risk": "<risiko terbesar>",
  "action_items": ["<langkah 1>", "<langkah 2>"]
}}
"""
    raw_main = _invoke_nova(prompt_main, max_tokens=1500, temperature=0.0)

    try:
        match = re.search(r"\{.*\}", raw_main, re.DOTALL)
        main_data = json.loads(match.group()) if match else json.loads(raw_main)
    except Exception as e:
        main_data = {
            "overall_health_score": 0, "overall_status": "UNKNOWN",
            "summary": f"Gagal parse main data: {e}", "top_risk": "none",
            "action_items": ["Cek log Bedrock"]
        }

    # --- TAHAP 2: BATCHING UNTUK SERVICES ---
    all_services = []
    chunk_size = 3500

    chunks = [services_raw[i:i+chunk_size] for i in range(0, len(services_raw), chunk_size)]

    for chunk in chunks[:4]:
        prompt_svc = f"""
Ekstrak daftar service dari potongan data APM Datadog ini, dan nilai kesehatannya (health_score) dengan mencocokkannya melawan data Error Logs dan Monitors.

=== ACTIVE MONITORS & ERROR LOGS (Gunakan ini sebagai acuan error) ===
{monitors_raw[:1500]}
{logs_raw[:1500]}

=== DATA APM SERVICES ===
{chunk}

ATURAN PENILAIAN WAJIB:
1. Cross-check nama service dari APM dengan data Monitors/Logs di atas.
2. Jika nama service tercantum di dalam Logs/Monitors yang sedang ERROR atau FAIL, turunkan skornya (contoh: 40-80), set status jadi "WARNING" atau "CRITICAL", dan tulis issue-nya.
3. Jika service aman (tidak ada di log error), berikan skor 95-100 dan status "HEALTHY".

Berikan HANYA format JSON Array (List). Jangan ada markdown atau teks tambahan.
[
  {{
    "name": "<nama_service>",
    "health_score": <0-100>,
    "status": "<HEALTHY|WARNING|CRITICAL>",
    "issue": "<issue dari monitor/log atau none>",
    "action": "<mitigasi atau none>"
  }}
]
"""
        raw_svc = _invoke_nova(prompt_svc, max_tokens=2000, temperature=0.0)

        try:
            match_svc = re.search(r"\[.*\]", raw_svc, re.DOTALL)
            if match_svc:
                svc_list = json.loads(match_svc.group())
                if isinstance(svc_list, list):
                    all_services.extend(svc_list)
        except Exception:
            pass

    # --- TAHAP 3: GABUNGKAN HASIL ---
    main_data["services"] = all_services

    return main_data


@workflow(name="chat_with_context")
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

    return _invoke_nova(prompt, max_tokens=4000, temperature=0.8)
