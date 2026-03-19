"""
 WATI Webhook Listener - Standalone Script
 Run this directly in terminal to see all incoming WATI webhook messages.

 Usage:
   python scripts/webhook_listener.py

 This runs a simple FastAPI server on port 3000 (or any port you choose).
 Point WATI webhook to: https://your-domain/webhook
"""

from fastapi import FastAPI, Request
from datetime import datetime
import uvicorn
import json

app = FastAPI()

@app.post("/webhook")
@app.post("/webhook/")
async def webhook_receiver(request: Request):
    data = await request.json()

    print("\n" + "═" * 60)
    print("  📩 WATI WEBHOOK RECEIVED")
    print(f"  🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 60)

    # Extract key fields
    sender_name = data.get("senderName", "N/A")
    wa_id = data.get("waId", "N/A")
    text = data.get("text", "")
    msg_type = data.get("type", "text")
    event_type = data.get("eventType", "N/A")

    print(f"  📱 Phone (waId) : {wa_id}")
    print(f"  👤 Sender Name  : {sender_name}")
    print(f"  💬 Message Text : {text}")
    print(f"  📦 Message Type : {msg_type}")
    print(f"  🔔 Event Type   : {event_type}")
    print("─" * 60)
    print("  📋 FULL RAW PAYLOAD:")
    print("─" * 60)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("═" * 60 + "\n")

    return {"status": "ok"}


# Also catch anything sent to root, just in case
@app.post("/")
async def root_webhook(request: Request):
    data = await request.json()
    print("\n⚠️  Webhook received on ROOT / instead of /webhook")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return {"status": "ok"}


if __name__ == "__main__":
    PORT = 5012
    print("\n" + "═" * 60)
    print("  🚀 WATI Webhook Listener Started!")
    print(f"  📡 Listening on port: {PORT}")
    print(f"  🔗 Webhook URL: http://localhost:{PORT}/webhook")
    print("  👀 Waiting for incoming messages...")
    print("═" * 60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
