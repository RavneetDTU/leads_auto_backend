from fastapi import APIRouter, HTTPException, Depends, Query
from app.models import (
    Lead as LeadSchema,
    LeadWithStatus,
    LeadStats, LeadsWithStats,
    LeadDetailUpdate, LeadDetailResponse,
    LeadNoteCreate, LeadNoteUpdate, LeadNoteResponse,
    LeadAnswersUpdate, LeadAnswersResponse,
)
from app.sql_models import Lead, Campaign, LeadDetail, LeadNote, LeadAnswers, Message
from app.database import get_db
from app.timezone_utils import SAST
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, case, func
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import uuid

router = APIRouter(prefix="/leads", tags=["Leads"])

MAX_NOTES = 10


# ═══════════════════════════════════════════════════════
# ACTIVE CAMPAIGNS (for demo lead form dropdown)
# ═══════════════════════════════════════════════════════
@router.get("/active-campaigns")
async def get_active_campaigns(db: AsyncSession = Depends(get_db)):
    """
    Returns all ACTIVE campaigns.
    Use this to populate the campaign dropdown when creating a demo lead.
    """
    stmt = select(Campaign).where(Campaign.status == "ACTIVE").order_by(Campaign.name)
    result = await db.execute(stmt)
    campaigns = result.scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "template_name": c.template_name
        }
        for c in campaigns
    ]


# ═══════════════════════════════════════════════════════
# DEMO LEAD (for end-to-end testing)
# ═══════════════════════════════════════════════════════
class DemoLeadRequest(BaseModel):
    # Required
    campaign_id: str
    name: str
    phone: str

    # Optional — same fields as a real Meta lead
    email: Optional[str] = None
    province: Optional[str] = None
    preferred_practice: Optional[str] = None
    practice_to_visit: Optional[str] = None
    practice_location: Optional[str] = None
    practice_to_attend: Optional[str] = None


@router.post("/demo", response_model=LeadSchema)
async def create_demo_lead(
    request: DemoLeadRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Inserts a demo lead that behaves exactly like a real Meta lead.
    Use this for end-to-end testing of the full platform:
    - Lead appears in the leads list
    - Template messages can be sent to it
    - WhatsApp replies will be linked to it
    - All campaign stats include it

    The demo lead is given a unique ID prefixed with 'DEMO-' so it can
    be identified and removed later if needed.
    """

    # 1. Validate campaign exists and is active
    stmt = select(Campaign).where(Campaign.id == request.campaign_id)
    result = await db.execute(stmt)
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != "ACTIVE":
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is not ACTIVE (current status: {campaign.status}). Demo leads should go into active campaigns."
        )

    # 2. Clean phone number (strip spaces, dashes, leading +)
    clean_phone = request.phone.replace("+", "").replace(" ", "").replace("-", "").strip()

    # 3. Check for duplicate phone in this campaign
    stmt = select(Lead).where(Lead.phone == clean_phone, Lead.campaign_id == request.campaign_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"A lead with phone {clean_phone} already exists in this campaign."
        )

    # 4. Create the demo lead — same structure as a real Meta lead
    demo_id = f"DEMO-{uuid.uuid4().hex[:12].upper()}"
    now = datetime.utcnow()

    new_lead = Lead(
        lead_id=demo_id,
        meta_lead_id=demo_id,          # Matches real lead structure
        name=request.name,
        phone=clean_phone,
        email=request.email,
        campaign_id=request.campaign_id,
        campaign_name=campaign.name,
        status="new",
        ad_id=None,
        ad_name="[Demo Lead]",
        adset_id=None,
        adset_name="[Demo Lead]",
        platform="facebook",
        province=request.province,
        preferred_practice=request.preferred_practice,
        practice_to_visit=request.practice_to_visit,
        practice_location=request.practice_location,
        practice_to_attend=request.practice_to_attend,
        template_message_sent=False,
        created_at=now,
        created_date=now.date(),
    )

    db.add(new_lead)
    await db.commit()
    await db.refresh(new_lead)

    # Auto-populate LeadDetail for demo lead
    branch_name = (
        request.preferred_practice or
        request.practice_to_attend or
        request.practice_to_visit or
        request.practice_location
    )
    detail = LeadDetail(
        lead_id=demo_id,
        name=request.name,
        email=request.email,
        phone_number=clean_phone,
        branch_name=branch_name,
        updated_at=datetime.utcnow(),
    )
    db.add(detail)
    await db.commit()

    print(f"  🧪 Demo lead created: {new_lead.name} ({new_lead.lead_id}) → campaign: {campaign.name}")

    return new_lead


# ═══════════════════════════════════════════════════════
# EXISTING ENDPOINT: BY CAMPAIGN
# ═══════════════════════════════════════════════════════
@router.get("/campaign/{campaign_id}", response_model=List[LeadSchema])
async def get_leads_by_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get leads for a specific campaign.
    """
    stmt = select(Lead).where(Lead.campaign_id == campaign_id)
    result = await db.execute(stmt)
    return result.scalars().all()


# ═══════════════════════════════════════════════════════
# EXISTING ENDPOINT: BY DATE
# ═══════════════════════════════════════════════════════
def _derive_whatsapp_status(
    template_message_sent: bool,
    latest_in_ts,   # datetime | None
    latest_out_ts,  # datetime | None
) -> str:
    """
    Derive the live WhatsApp status badge for a lead.

    The WATI webhook is shared with another team, so OUT messages may not
    always originate from our platform. We distinguish using the
    `template_message_sent` flag, which is set ONLY when our platform sends
    a template via the scheduler.

    Priority order:
      responded              – any OUT is newer than (or equal to) latest IN;
                               also fires when another team's OUT exists with no
                               customer reply (template_message_sent=False, OUT exists)
      unread                 – customer replied (IN exists), no OUT after it
      initial_template_sent  – our platform sent the template (flag=True), no reply yet
      new                    – no messages at all, we haven't sent anything
    """
    if latest_in_ts is not None:
        if latest_out_ts is not None and latest_out_ts >= latest_in_ts:
            return "responded"
        return "unread"
    # No customer reply yet
    if template_message_sent:
        return "initial_template_sent"   # Our platform sent the template
    if latest_out_ts is not None:
        return "responded"               # Other team sent a message
    return "new"


async def _leads_with_status_query(db, where_clause, order_by_clause) -> LeadsWithStats:
    """
    Shared helper: runs the LEFT JOIN query and returns LeadsWithStats.
    One SQL round-trip. ~0.7 ms for daily leads, <50 ms for 2000 leads.
    """
    latest_in_ts = func.max(
        case((Message.direction == "IN", Message.timestamp), else_=None)
    ).label("latest_in_ts")
    latest_out_ts = func.max(
        case((Message.direction == "OUT", Message.timestamp), else_=None)
    ).label("latest_out_ts")
    last_activity_ts = func.max(Message.timestamp).label("last_activity_ts")

    stmt = (
        select(
            Lead,
            latest_in_ts,
            latest_out_ts,
            last_activity_ts,
        )
        .outerjoin(Message, Message.lead_id == Lead.lead_id)
        .where(where_clause)
        .group_by(Lead.lead_id)
        .order_by(order_by_clause)
    )

    result = await db.execute(stmt)
    rows = result.all()

    leads = []
    counts = {"new": 0, "initial_template_sent": 0, "unread": 0, "responded": 0}

    for row in rows:
        lead_orm = row[0]
        lin  = row[1]  # latest_in_ts
        lout = row[2]  # latest_out_ts
        lact = row[3]  # last_activity_ts

        wa_status = _derive_whatsapp_status(
            lead_orm.template_message_sent or False, lin, lout
        )
        counts[wa_status] = counts.get(wa_status, 0) + 1

        leads.append(LeadWithStatus(
            lead_id=lead_orm.lead_id,
            meta_lead_id=lead_orm.meta_lead_id,
            name=lead_orm.name,
            phone=lead_orm.phone,
            email=lead_orm.email,
            campaign_id=lead_orm.campaign_id,
            campaign_name=lead_orm.campaign_name,
            status=lead_orm.status,
            ad_id=lead_orm.ad_id,
            ad_name=lead_orm.ad_name,
            adset_id=lead_orm.adset_id,
            adset_name=lead_orm.adset_name,
            platform=lead_orm.platform,
            province=lead_orm.province,
            preferred_practice=lead_orm.preferred_practice,
            practice_to_visit=lead_orm.practice_to_visit,
            practice_location=lead_orm.practice_location,
            practice_to_attend=lead_orm.practice_to_attend,
            template_message_sent=lead_orm.template_message_sent,
            created_at=lead_orm.created_at,
            whatsapp_status=wa_status,
            last_message_time=lact,
        ))

    stats = LeadStats(
        total=len(leads),
        new=counts["new"],
        initial_template_sent=counts["initial_template_sent"],
        unread=counts["unread"],
        responded=counts["responded"],
    )
    return LeadsWithStats(leads=leads, stats=stats)


@router.get("/date/{date_str}", response_model=LeadsWithStats)
async def get_leads_by_date(date_str: str, db: AsyncSession = Depends(get_db)):
    """
    Get leads for a specific date (YYYY-MM-DD), enriched with live WhatsApp status and stats.
    Ordered by most recent WhatsApp activity first (same as the WhatsApp contacts panel).
    Dates/times returned in GMT+2.

    whatsapp_status values:
      "new"                   – no template sent yet
      "initial_template_sent" – template sent, no reply yet
      "unread"                – customer replied, we haven't replied since
      "responded"             – we replied after their last message
    """
    try:
        query_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    return await _leads_with_status_query(
        db,
        where_clause=Lead.created_date == query_date,
        order_by_clause=Lead.created_at.desc(),
    )


# ═══════════════════════════════════════════════════════
# FEATURE 1: LAST 30 DAYS LEADS
# ═══════════════════════════════════════════════════════
@router.get("/last-30-days", response_model=LeadsWithStats)
async def get_leads_last_30_days(db: AsyncSession = Depends(get_db)):
    """
    Get all leads from the last 30 days, enriched with live WhatsApp status and stats.
    Ordered by most recent WhatsApp activity first.
    Dates/times are returned in GMT+2.
    """
    today_gmt2 = datetime.now(tz=SAST).date()
    cutoff_date = today_gmt2 - timedelta(days=30)

    return await _leads_with_status_query(
        db,
        where_clause=Lead.created_date >= cutoff_date,
        order_by_clause=Lead.created_at.desc(),
    )


# ═══════════════════════════════════════════════════════
# FEATURE 3.1: LEAD DETAIL (Branch Info — editable)
# ═══════════════════════════════════════════════════════
@router.get("/{lead_id}/detail", response_model=LeadDetailResponse)
async def get_lead_detail(lead_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the editable detail record for a lead.
    Fields: branch_name, status, name, email, phone_number, city.
    Returns null values for all fields if no detail has been saved yet.
    """
    lead_result = await db.execute(select(Lead).where(Lead.lead_id == lead_id))
    if not lead_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")

    result = await db.execute(select(LeadDetail).where(LeadDetail.lead_id == lead_id))
    detail = result.scalar_one_or_none()

    if not detail:
        return LeadDetailResponse(lead_id=lead_id)

    return detail


@router.put("/{lead_id}/detail", response_model=LeadDetailResponse)
async def upsert_lead_detail(
    lead_id: str,
    payload: LeadDetailUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create or update the editable detail record for a lead (upsert).
    Fields: branch_name, status, name, email, phone_number, city.
    Note: name/email/phone_number here are editable copies — the original
    Meta-sourced values on the Lead record remain untouched.
    """
    lead_result = await db.execute(select(Lead).where(Lead.lead_id == lead_id))
    if not lead_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")

    result = await db.execute(select(LeadDetail).where(LeadDetail.lead_id == lead_id))
    detail = result.scalar_one_or_none()

    now = datetime.utcnow()
    if detail:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(detail, field, value)
        detail.updated_at = now
    else:
        detail = LeadDetail(
            lead_id=lead_id,
            updated_at=now,
            **payload.model_dump(exclude_unset=True)
        )
        db.add(detail)

    await db.commit()
    await db.refresh(detail)
    return detail


# ═══════════════════════════════════════════════════════
# FEATURE 3.2: LEAD NOTES (max 10, editable)
# ═══════════════════════════════════════════════════════
@router.get("/{lead_id}/notes", response_model=List[LeadNoteResponse])
async def get_lead_notes(lead_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get all notes for a lead, ordered by note_number (1 → 10).
    """
    lead_result = await db.execute(select(Lead).where(Lead.lead_id == lead_id))
    if not lead_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")

    result = await db.execute(
        select(LeadNote)
        .where(LeadNote.lead_id == lead_id)
        .order_by(LeadNote.note_number)
    )
    return result.scalars().all()


@router.post("/{lead_id}/notes", response_model=LeadNoteResponse, status_code=201)
async def add_lead_note(
    lead_id: str,
    payload: LeadNoteCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Add a new note to a lead. Auto-assigns the next note_number (1–10).
    Returns 400 if the lead already has 10 notes (max limit).
    """
    lead_result = await db.execute(select(Lead).where(Lead.lead_id == lead_id))
    if not lead_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")

    notes_result = await db.execute(
        select(LeadNote)
        .where(LeadNote.lead_id == lead_id)
        .order_by(LeadNote.note_number)
    )
    existing_notes = notes_result.scalars().all()

    if len(existing_notes) >= MAX_NOTES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_NOTES} notes reached for this lead. Edit an existing note instead."
        )

    next_note_number = len(existing_notes) + 1
    new_note = LeadNote(
        lead_id=lead_id,
        note_number=next_note_number,
        content=payload.content,
        updated_at=datetime.utcnow(),
    )
    db.add(new_note)
    await db.commit()
    await db.refresh(new_note)
    return new_note


@router.put("/{lead_id}/notes/{note_number}", response_model=LeadNoteResponse)
async def update_lead_note(
    lead_id: str,
    note_number: int,
    payload: LeadNoteUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Edit the content of an existing note by its note_number.
    Returns 404 if the note does not exist.
    """
    if not (1 <= note_number <= MAX_NOTES):
        raise HTTPException(status_code=400, detail=f"note_number must be between 1 and {MAX_NOTES}")

    result = await db.execute(
        select(LeadNote).where(
            LeadNote.lead_id == lead_id,
            LeadNote.note_number == note_number,
        )
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=404,
            detail=f"Note {note_number} not found for lead '{lead_id}'"
        )

    note.content = payload.content
    note.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(note)
    return note


# ═══════════════════════════════════════════════════════
# FEATURE 3.3: LEAD Y/N ANSWERS
# ═══════════════════════════════════════════════════════
@router.get("/{lead_id}/answers", response_model=LeadAnswersResponse)
async def get_lead_answers(lead_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the yes/no question answers for a lead.
    Questions:
    - difficulty_crowded: Do you have difficulty in crowded or noisy situations?
    - mumble_or_muffled:  Do you think that other people mumble or sound muffled?
    - watch_face:         Do you intently watch people's face when they speak to you?
    Returns null values if answers have not been saved yet.
    """
    lead_result = await db.execute(select(Lead).where(Lead.lead_id == lead_id))
    if not lead_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")

    result = await db.execute(select(LeadAnswers).where(LeadAnswers.lead_id == lead_id))
    answers = result.scalar_one_or_none()

    if not answers:
        return LeadAnswersResponse(lead_id=lead_id)

    return answers


@router.put("/{lead_id}/answers", response_model=LeadAnswersResponse)
async def upsert_lead_answers(
    lead_id: str,
    payload: LeadAnswersUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Set or update the yes/no question answers for a lead (upsert).
    Pass true/false for each question. Omit a field to leave it unchanged.
    """
    lead_result = await db.execute(select(Lead).where(Lead.lead_id == lead_id))
    if not lead_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")

    result = await db.execute(select(LeadAnswers).where(LeadAnswers.lead_id == lead_id))
    answers = result.scalar_one_or_none()

    now = datetime.utcnow()
    if answers:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(answers, field, value)
        answers.updated_at = now
    else:
        answers = LeadAnswers(
            lead_id=lead_id,
            updated_at=now,
            **payload.model_dump(exclude_unset=True)
        )
        db.add(answers)

    await db.commit()
    await db.refresh(answers)
    return answers
