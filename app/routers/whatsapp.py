from fastapi import APIRouter, HTTPException, Depends, Query
from app.models import (
    SendTemplateRequest, SendSessionMessageRequest,
    ChatContactResponse, ChatMessageResponse
)
from app.sql_models import Lead, Campaign, Message
from app.services.wati import wati_service
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, case
from typing import List, Optional
from datetime import datetime
import uuid

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


# ═══════════════════════════════════════════════════════
# 1. SEND TEMPLATE MESSAGE
# ═══════════════════════════════════════════════════════
@router.post("/send-template")
async def send_template_message(
    request: SendTemplateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Sends a pre-approved WhatsApp template message.
    Looks up the template_name from the campaign.
    If no template saved → returns error.
    Saves outgoing message to DB and marks lead.
    """
    # 1. Look up campaign
    stmt = select(Campaign).where(Campaign.id == request.campaign_id)
    result = await db.execute(stmt)
    campaign = result.scalar_one_or_none()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    if not campaign.template_name:
        return {
            "result": False,
            "error": "No Template Message saved for this Campaign",
            "campaign_id": request.campaign_id
        }
    
    # 2. Find lead by phone for parameter substitution
    clean_phone = request.phone.replace("+", "").strip()
    stmt = select(Lead).where(Lead.phone == clean_phone).limit(1)
    result = await db.execute(stmt)
    lead = result.scalar_one_or_none()
    
    lead_name = lead.name if lead else "Customer"
    lead_id = lead.lead_id if lead else None
    
    # 3. Build parameters (customize based on your template)
    parameters = [{"name": "name", "value": lead_name}]
    
    # 4. Call WATI
    wati_response = wati_service.send_template_message(
        phone=clean_phone,
        template_name=campaign.template_name,
        parameters=parameters
    )
    
    # 5. Save outgoing message to DB
    message_id = str(uuid.uuid4())
    new_message = Message(
        message_id=message_id,
        lead_id=lead_id,
        phone=clean_phone,
        direction="OUT",
        message_type="template",
        template_name=campaign.template_name,
        message_text=f"[Template: {campaign.template_name}]",
        wati_message_id=wati_response.get("messageId"),
        wati_raw_data=wati_response,
        status="sent" if wati_response.get("result") else "failed",
        timestamp=datetime.utcnow()
    )
    db.add(new_message)
    
    # 6. Mark lead as template sent
    if lead:
        lead.template_message_sent = True
        lead.status = "contacted"
    
    await db.commit()
    
    print(f"  📤 Template '{campaign.template_name}' sent to {clean_phone} → {wati_response.get('result')}")
    
    return {
        "result": wati_response.get("result", False),
        "message_id": message_id,
        "phone": clean_phone,
        "template_name": campaign.template_name,
        "wati_response": wati_response
    }


# ═══════════════════════════════════════════════════════
# 2. CONTACTS COUNT (for frontend to know total)
# ═══════════════════════════════════════════════════════
@router.get("/contacts/count")
async def get_contacts_count(
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Returns total number of contacts with messages. Used by frontend for pagination."""
    from sqlalchemy import func as sqlfunc

    stmt = (
        select(func.count(func.distinct(Message.phone)))
        .select_from(Message)
        .outerjoin(Lead, Lead.phone == Message.phone)
    )
    if search:
        stmt = stmt.where(
            (Lead.name.ilike(f"%{search}%")) | (Message.phone.ilike(f"%{search}%"))
        )
    result = await db.execute(stmt)
    total = result.scalar() or 0
    return {"total": total}


# ═══════════════════════════════════════════════════════
# 3. CONTACTS LIST (Left Panel)
# ═══════════════════════════════════════════════════════
@router.get("/contacts", response_model=List[ChatContactResponse])
async def get_chat_contacts(
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),  # Default 20, max 1000
    db: AsyncSession = Depends(get_db)
):
    """
    Returns contacts with messages, ordered by most recent message.
    Frontend uses this for the left-panel WhatsApp view.
    
    Pagination:
     - page=1&page_size=100  → first 100 contacts (default)
     - page=2&page_size=100  → next 100 contacts (for infinite scroll)
     - page_size=1000        → effectively all contacts at once
    
    Re-fetching this endpoint after a webhook updates the order automatically.
    """
    # ── Step 1: Latest message per phone (DISTINCT ON for correctness) ──────
    # Using raw SQL via SQLAlchemy text() because DISTINCT ON is PostgreSQL-specific
    # and much cleaner than a complex correlated subquery here.
    from sqlalchemy import text as sa_text

    latest_msg_subq = (
        select(
            Message.phone.label("phone"),
            Message.message_text.label("last_message_text"),
            Message.direction.label("last_message_direction"),
            Message.timestamp.label("last_message_time"),
        )
        .distinct(Message.phone)               # DISTINCT ON (phone)
        .order_by(Message.phone, Message.timestamp.desc())  # latest first per phone
        .subquery("latest_msg")
    )

    # ── Step 2: Unread count per phone ───────────────────────────────────────
    unread_subq = (
        select(
            Message.phone.label("phone"),
            func.count(Message.message_id).label("unread_count"),
        )
        .where(and_(Message.direction == "IN", Message.status == "received"))
        .group_by(Message.phone)
        .subquery("unread_counts")
    )

    # ── Step 3: Join everything together ─────────────────────────────────────
    stmt = (
        select(
            latest_msg_subq.c.phone,
            latest_msg_subq.c.last_message_text,
            latest_msg_subq.c.last_message_direction,
            latest_msg_subq.c.last_message_time,
            func.coalesce(unread_subq.c.unread_count, 0).label("unread_count"),
            Lead.lead_id,
            Lead.name,
        )
        .outerjoin(Lead, Lead.phone == latest_msg_subq.c.phone)
        .outerjoin(unread_subq, unread_subq.c.phone == latest_msg_subq.c.phone)
        .order_by(latest_msg_subq.c.last_message_time.desc())
    )

    # Apply search filter
    if search:
        stmt = stmt.where(
            (Lead.name.ilike(f"%{search}%")) | (latest_msg_subq.c.phone.ilike(f"%{search}%"))
        )

    # Pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await db.execute(stmt)
    rows = result.all()

    contacts = []
    for row in rows:
        contacts.append(ChatContactResponse(
            lead_id=row.lead_id,
            name=row.name or row.phone,
            phone=row.phone,
            last_message_text=row.last_message_text,
            last_message_time=row.last_message_time,
            last_message_direction=row.last_message_direction,
            unread_count=row.unread_count or 0
        ))

    return contacts


# ═══════════════════════════════════════════════════════
# 3. SYNC OLD CHATS (Load Old Chats Button)
# ═══════════════════════════════════════════════════════
@router.post("/sync-chats/{phone}")
async def sync_old_chats(
    phone: str,
    page_size: int = Query(100, ge=1, le=500),
    page_number: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetches old chats from WATI and syncs them into our DB.
    Frontend calls this when user clicks "Load Old Chats" button.
    Returns the synced messages.
    """
    clean_phone = phone.replace("+", "").strip()
    
    # 1. Fetch from WATI
    wati_data = wati_service.get_messages(clean_phone, page_size, page_number)
    
    if wati_data.get("result") == "error":
        raise HTTPException(status_code=502, detail=f"WATI error: {wati_data.get('error')}")
    
    # 2. Extract messages
    messages_data = wati_data.get("messages", {})
    items = messages_data.get("items", [])
    
    if not items:
        return {"synced": 0, "message": "No messages found on WATI for this contact"}
    
    # 3. Find lead by phone
    stmt = select(Lead).where(Lead.phone == clean_phone).limit(1)
    result = await db.execute(stmt)
    lead = result.scalar_one_or_none()
    lead_id = lead.lead_id if lead else None
    
    synced_count = 0
    
    for item in items:
        # Determine direction using the `owner` field:
        # WATI sets owner=True when the message was sent by your agent (OUT)
        # WATI sets owner=False when sent by the customer (IN)
        # NOTE: eventType="message" is used for BOTH directions, so it cannot be trusted.
        owner = item.get("owner", False)
        direction = "OUT" if owner else "IN"

        wati_msg_id = item.get("id") or item.get("whatsappMessageId", "")
        
        # Message text
        msg_text = item.get("text") or item.get("finalText") or item.get("data", "")
        
        # Timestamp — strip timezone info (DB uses naive timestamps)
        created_str = item.get("created", "")
        try:
            msg_timestamp = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            msg_timestamp = msg_timestamp.replace(tzinfo=None)  # Strip tz for naive TIMESTAMP column
        except:
            msg_timestamp = datetime.utcnow()
        
        # PRIMARY dedup check: by wati_message_id
        if wati_msg_id:
            stmt = select(Message).where(Message.wati_message_id == wati_msg_id).limit(1)
            result = await db.execute(stmt)
            if result.scalar_one_or_none():
                continue  # Already exists
        
        # SECONDARY dedup check: same phone + same text + timestamp within 5 seconds
        # Catches cases where webhook and sync both store the same message under different IDs
        if msg_text:
            from datetime import timedelta
            ts_lower = msg_timestamp - timedelta(seconds=5)
            ts_upper = msg_timestamp + timedelta(seconds=5)
            stmt = select(Message).where(
                Message.phone == clean_phone,
                Message.message_text == msg_text,
                Message.timestamp >= ts_lower,
                Message.timestamp <= ts_upper,
            ).limit(1)
            result = await db.execute(stmt)
            if result.scalar_one_or_none():
                continue  # Near-duplicate (same message, different ID format), skip
        
        # Insert new message
        message_id = str(uuid.uuid4())
        raw_type = item.get("type", "text")
        msg_type_str = str(raw_type) if raw_type is not None else "text"
        status_str = str(item.get("statusString", "synced")).lower()
        
        new_message = Message(
            message_id=message_id,
            lead_id=lead_id,
            phone=clean_phone,
            direction=direction,
            message_type=msg_type_str,
            message_text=msg_text or "",
            wati_message_id=wati_msg_id if wati_msg_id else None,
            wati_raw_data=item,
            status=status_str,
            timestamp=msg_timestamp
        )
        db.add(new_message)
        synced_count += 1
    
    await db.commit()
    
    print(f"  📥 Synced {synced_count} old messages for {clean_phone}")
    
    return {
        "synced": synced_count,
        "total_from_wati": len(items),
        "phone": clean_phone
    }


# ═══════════════════════════════════════════════════════
# 4. SEND SESSION MESSAGE (Free Text Reply)
# ═══════════════════════════════════════════════════════
@router.post("/send-message")
async def send_session_message(
    request: SendSessionMessageRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Sends a free-text message within the 24-hour WhatsApp session window.
    Saves copy to our DB.
    """
    clean_phone = request.phone.replace("+", "").strip()
    
    # 1. Call WATI
    wati_response = wati_service.send_session_message(clean_phone, request.message_text)
    
    # 2. Find lead
    stmt = select(Lead).where(Lead.phone == clean_phone).limit(1)
    result = await db.execute(stmt)
    lead = result.scalar_one_or_none()
    lead_id = lead.lead_id if lead else None
    
    # 3. Save to DB
    message_id = str(uuid.uuid4())
    new_message = Message(
        message_id=message_id,
        lead_id=lead_id,
        phone=clean_phone,
        direction="OUT",
        message_type="session",
        message_text=request.message_text,
        wati_message_id=wati_response.get("messageId"),
        wati_raw_data=wati_response,
        status="sent" if wati_response.get("result") else "failed",
        timestamp=datetime.utcnow()
    )
    db.add(new_message)

    # Mark lead as contacted (so status moves from 'new' → 'initial_template_sent')
    if lead:
        lead.template_message_sent = True

    await db.commit()
    
    print(f"  📤 Session msg to {clean_phone}: '{request.message_text[:50]}...' → {wati_response.get('result')}")
    
    return {
        "result": wati_response.get("result", False),
        "message_id": message_id,
        "phone": clean_phone,
        "wati_response": wati_response
    }


# ═══════════════════════════════════════════════════════
# 5. GET MESSAGES (Right Panel Chat View)
# ═══════════════════════════════════════════════════════
@router.get("/messages/{phone}")
async def get_messages(
    phone: str,
    page_size: int = Query(50, ge=1, le=200),
    before_timestamp: Optional[str] = Query(None, description="ISO timestamp; load messages strictly before this point (for infinite scroll upward)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the most recent `page_size` messages for a contact by default.
    Messages are always in ASC order (oldest first) for correct chat display.

    Response shape:
        { "has_more": bool, "messages": [ ...ChatMessageResponse... ] }

    For infinite scroll upward, pass `before_timestamp` equal to the ISO
    timestamp of the oldest message currently displayed.
    """
    clean_phone = phone.replace("+", "").strip()

    base_where = Message.phone == clean_phone

    if before_timestamp:
        try:
            before_dt = datetime.fromisoformat(before_timestamp.replace("Z", "+00:00"))
            before_dt = before_dt.replace(tzinfo=None)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid before_timestamp format. Use ISO 8601.")

        count_stmt = select(func.count(Message.message_id)).where(
            and_(base_where, Message.timestamp < before_dt)
        )
        total_before = (await db.execute(count_stmt)).scalar() or 0
        offset = max(0, total_before - page_size)

        stmt = (
            select(Message)
            .where(and_(base_where, Message.timestamp < before_dt))
            .order_by(Message.timestamp.asc())
            .offset(offset)
            .limit(page_size)
        )
        has_more = offset > 0

    else:
        # Default: load the LAST page — most recent `page_size` messages.
        count_stmt = select(func.count(Message.message_id)).where(base_where)
        total_count = (await db.execute(count_stmt)).scalar() or 0
        offset = max(0, total_count - page_size)
        has_more = offset > 0

        stmt = (
            select(Message)
            .where(base_where)
            .order_by(Message.timestamp.asc())
            .offset(offset)
            .limit(page_size)
        )

    result = await db.execute(stmt)
    messages = result.scalars().all()

    return {
        "has_more": has_more,
        "messages": [
            ChatMessageResponse(
                message_id=m.message_id,
                phone=m.phone,
                direction=m.direction,
                message_type=m.message_type,
                template_name=m.template_name,
                message_text=m.message_text,
                status=m.status,
                timestamp=m.timestamp
            )
            for m in messages
        ]
    }
