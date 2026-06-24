# AI Health Check — Bedrock x Datadog MCP

## Arsitektur

```
Streamlit UI
    │
    ├── mcp_client.py  ──→  Datadog MCP Server (remote, official)
    │                           tools: get_monitors, search_logs,
    │                                  get_services, query_metrics
    │
    ├── bedrock_helper.py ──→  Amazon Bedrock (Nova Micro)
    │                           analisis data MCP → health score JSON
    │
    └── app.py  ──→  Dashboard Streamlit
                     + kirim metric balik ke Datadog
                       (hackathon.ai.health_score)
```

---

## Step 1 — Install dependencies

```bash
pip install -r requirements.txt
```

---

## Step 2 — Setup AWS credentials

```bash
aws configure
# AWS Access Key ID: <isi dari IAM>
# AWS Secret Access Key: <isi dari IAM>
# Default region: us-east-1
# Output format: json
```

Pastikan IAM user kamu punya policy `AmazonBedrockFullAccess` dan Nova Micro sudah di-enable di Bedrock console.

---

## Step 3 — Enable Datadog MCP Server

Datadog MCP Server adalah **remote server** yang disediakan Datadog (bukan yang kamu jalankan sendiri).

1. Buka https://docs.datadoghq.com/bits_ai/mcp_server/
2. Login ke Datadog account kamu
3. Pastikan akun kamu punya akses ke Bits AI / MCP Server (tersedia di semua plan)
4. Siapkan:
   - **API Key**: Datadog → Organization Settings → API Keys → New Key
   - **App Key**: Datadog → Organization Settings → Application Keys → New Key
   - App Key harus punya scope: `monitors_read`, `logs_read`, `metrics_read`

---

## Step 4 — Jalankan app

```bash
streamlit run app.py
```

Buka browser ke http://localhost:8501

---

## Step 5 — Di dalam app

1. Isi **Datadog API Key** dan **App Key** di sidebar
2. Klik **Tes Koneksi MCP** — kalau berhasil akan tampil list tools yang tersedia
3. Klik **Jalankan Health Check** — app akan:
   - Panggil `get_monitors` via MCP
   - Panggil `search_logs` via MCP
   - Panggil `get_services` via MCP
   - Kirim semua data ke Bedrock Nova Micro untuk dianalisis
   - Tampilkan hasilnya di dashboard
   - Kirim metric `hackathon.ai.health_score` balik ke Datadog

---

## Step 6 — Buat Custom Dashboard di Datadog

Setelah health check jalan minimal sekali, metric `hackathon.ai.health_score` sudah masuk.

1. Datadog → **Dashboards** → **New Dashboard**
2. Tambahkan widget:

| Widget Type | Query | Keterangan |
|---|---|---|
| Query Value | `avg:hackathon.ai.health_score{*}` | Overall score sekarang |
| Timeseries | `avg:hackathon.ai.health_score{*} by {service}` | Trend per service |
| Top List | `avg:hackathon.ai.health_score{*} by {service}` sort ASC | Service paling sakit |
| Event Stream | filter `source:bedrock_health_checker` | Event dari AI health check |

---

## Step 7 — LLM Observability (opsional tapi penting untuk hackathon)

Supaya semua call ke Nova Micro ke-track di Datadog LLM Observability:

```bash
# Set env vars sebelum jalankan app
export DD_API_KEY="your_datadog_api_key"
export DD_LLMOBS_ENABLED=1
export DD_LLMOBS_ML_APP="hackathon-health-checker"
export DD_LLMOBS_AGENTLESS_ENABLED=1

# Jalankan dengan ddtrace
ddtrace-run streamlit run app.py
```

Setelah ini, buka Datadog → **LLM Observability** → kamu bisa lihat:
- Setiap prompt yang dikirim ke Nova Micro
- Token usage
- Latency per call
- Response dari model

---

## Troubleshooting

**Error: `mcp.client.streamable_http` not found**
```bash
pip install --upgrade mcp
```

**Error: MCP connection timeout**
- Cek API Key dan App Key sudah benar
- Pastikan App Key punya scope yang cukup
- Coba dari browser: buka https://mcp.datadoghq.com/mcp/v1

**Error: Bedrock access denied**
- Pastikan `aws configure` sudah diisi
- Cek Nova Micro sudah di-enable di region us-east-1
- Cek IAM policy ada `AmazonBedrockFullAccess`

**Nova Micro tidak tersedia**
- Ganti `modelId` di `bedrock_helper.py` ke `amazon.nova-lite-v1:0`# mii-dd-aws-hackathon
