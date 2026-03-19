from fastapi import APIRouter, Request, HTTPException, Depends
from app.database import get_db
from app.sql_models import Lead, Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime
import uuid
import json
import logging
import os
from logging.handlers import TimedRotatingFileHandler

# ═══════════════════════════════════════════════════════════════
# DEDICATED WATI WEBHOOK LOGGER
# Writes to logs/wati_webhook.log — rotates daily, keeps 30 days
# ═══════════════════════════════════════════════════════════════
_LOG_DIR = os.path.join(os.path.dirname(__file__), "../../logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, "wati_webhook.log")

wati_logger = logging.getLogger("wati_webhook")
wati_logger.setLevel(logging.DEBUG)

if not wati_logger.handlers:
    _handler = TimedRotatingFileHandler(
        _LOG_FILE,
        when="midnight",      # Rotate at midnight
        interval=1,           # Every day
        backupCount=30,       # Keep 30 days
        encoding="utf-8",
    )
    _handler.setFormatter(logging.Formatter("%(message)s"))
    wati_logger.addHandler(_handler)


def _wlog(msg: str):
    """Write to both terminal (print) and the dedicated wati log file."""
    print(msg)
    wati_logger.info(msg)


router = APIRouter(prefix="/webhook", tags=["Webhook"])


@router.post("")
@router.post("/")
async def wati_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        data = await request.json()
        
        # ═══════════════════════════════════════════════════
        # RICH TERMINAL LOGGING
        # ═══════════════════════════════════════════════════
        _wlog("\n" + "═" * 60)
        _wlog("  📩 WATI WEBHOOK RECEIVED")
        _wlog(f"  🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        _wlog("═" * 60)
        
        # Extract key fields for quick view
        sender_name = data.get("senderName", "N/A")
        raw_wa_id = data.get("waId", "N/A")
        wa_id = raw_wa_id.replace("+", "").replace(" ", "").replace("-", "").strip() if raw_wa_id != "N/A" else "N/A"
        text = data.get("text", "")
        msg_type = data.get("type", "text")
        event_type = data.get("eventType", "N/A")
        wati_msg_id = data.get("whatsappMessageId", "") or data.get("id", "")
        
        _wlog(f"  📱 Phone (waId) : {wa_id}")
        _wlog(f"  👤 Sender Name  : {sender_name}")
        _wlog(f"  💬 Message Text : {text}")
        _wlog(f"  📦 Message Type : {msg_type}")
        _wlog(f"  🔔 Event Type   : {event_type}")
        _wlog(f"  🆔 WATI Msg ID  : {wati_msg_id}")
        _wlog("─" * 60)
        _wlog("  📋 FULL RAW PAYLOAD:")
        _wlog("─" * 60)
        _wlog(json.dumps(data, indent=2, ensure_ascii=False))
        _wlog("═" * 60 + "\n")
        
        # ═══════════════════════════════════════════════════
        # HANDLE STATUS UPDATES (Delivered, Read, Replied)
        # ═══════════════════════════════════════════════════
        status_events = {
            "sentMessageDELIVERED_v2": "delivered",
            "sentMessageREAD_v2": "read",
            "sentMessageREPLIED_v2": "replied",
        }
        
        if event_type in status_events and wati_msg_id:
            new_status = status_events[event_type]
            stmt = (
                update(Message)
                .where(Message.wati_message_id == wati_msg_id)
                .values(status=new_status)
            )
            result = await db.execute(stmt)
            await db.commit()
            
            if result.rowcount > 0:
                _wlog(f"  ✅ Updated message {wati_msg_id} status → {new_status}")
            else:
                _wlog(f"  ⚠️  No message found with wati_message_id: {wati_msg_id}")
            
            return {"status": "success", "action": f"status_updated_to_{new_status}"}
        
        # ═══════════════════════════════════════════════════
        # PROCESS MESSAGE & STORE IN DB
        # ═══════════════════════════════════════════════════
        if not wa_id or wa_id == "N/A":
            _wlog("  ⚠️  Ignored: No waId found in payload")
            return {"status": "ignored", "detail": "No waId found"}

        # Determine direction using owner field (same logic as sync_old_chats):
        #   owner=True  → our team/system sent this → OUT
        #   owner=False → customer sent this        → IN
        owner = data.get("owner", None)
        if owner is True:
            direction = "OUT"
        elif owner is False:
            direction = "IN"
        else:
            # owner absent — fall back to event type
            if event_type in ("sessionMessageSent_v2", "templateMessageSent_v2",
                              "sessionMessageSent", "templateMessageSent"):
                direction = "OUT"
            else:
                direction = "IN"

        # Deduplicate: check if this WATI message already exists
        if wati_msg_id:
            stmt = select(Message).where(Message.wati_message_id == wati_msg_id).limit(1)
            result = await db.execute(stmt)
            if result.scalar_one_or_none():
                _wlog(f"  ⚠️  Duplicate: message {wati_msg_id} already in DB")
                return {"status": "duplicate"}

        # Find Lead by Phone
        stmt = select(Lead).where(Lead.phone == wa_id).limit(1)
        result = await db.execute(stmt)
        lead = result.scalar_one_or_none()
        
        lead_id = lead.lead_id if lead else None
            
        if not lead_id:
            _wlog(f"  ⚠️  No lead found in DB for phone: {wa_id}")
        else:
            _wlog(f"  ✅ Matched Lead: {lead_id} ({lead.name})")

        message_id = str(uuid.uuid4())
        
        new_message = Message(
            message_id = message_id,
            lead_id = lead_id,
            phone = wa_id,
            direction = direction,           # ← now uses owner field
            message_type = msg_type,
            message_text = text,
            wati_message_id = wati_msg_id if wati_msg_id else None,
            wati_raw_data = data,
            status = "received" if direction == "IN" else "sent",
            timestamp = datetime.utcnow()
        )
        
        db.add(new_message)
        await db.commit()
        
        _wlog(f"  💾 Message saved ({direction}): {message_id}")
        return {"status": "success"}

    except Exception as e:
        _wlog(f"\n❌ WEBHOOK ERROR: {e}\n")
        return {"status": "error", "detail": str(e)}
