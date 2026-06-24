# debug_mcp.py
import asyncio
import traceback
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "https://mcp.datadoghq.com/v1/mcp"

# Pastikan Key ini aktif dan sesuai dengan Region akun Datadog-mu
DD_API_KEY = "1821f25bd235c0830dc0b365d2bf6365"
DD_APP_KEY = "ddapp_VETS3Xeibxmp78wF2cGufxPEPFyG0DJDmq"

async def main():
    headers = {
        "DD-API-KEY": DD_API_KEY,
        "DD-APPLICATION-KEY": DD_APP_KEY,
        "Content-Type": "application/json"
    }
    
    print(f"🔄 Membuka koneksi resmi ke: {URL}\n")
    try:
        async with streamablehttp_client(URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                print("⏳ Mengirim 'initialize' handshake...")
                await session.initialize()
                print("✅ Handshake Sukses!\n")
                
                print("⏳ Meminta daftar tools asli (tools/list)...")
                result = await session.list_tools()
                print(f"🎉 Berhasil! Ditemukan {len(result.tools)} tools aktif.")
                        
    except Exception as e:
        print("\n❌ Terjadi kesalahan! Berikut detail sub-exception yang terjadi:\n")
        # traceback.print_exc() otomatis membongkar seluruh isi TaskGroup / ExceptionGroup ke terminal
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())