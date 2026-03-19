import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update, func
from app.database import AsyncSessionLocal
from app.sql_models import Lead, LeadDetail, Message

def clean_phone(phone: str) -> str:
    if not phone: return phone
    return phone.replace("+", "").replace(" ", "").replace("-", "").strip()

async def backfill():
    async with AsyncSessionLocal() as db:
        print("1. Cleaning Lead.phone")
        leads_fixed = 0
        result = await db.execute(select(Lead))
        leads = result.scalars().all()
        for lead in leads:
            cleaned = clean_phone(lead.phone)
            if cleaned != lead.phone:
                lead.phone = cleaned
                leads_fixed += 1
                
        print("2. Cleaning LeadDetail.phone_number")
        details_fixed = 0
        result_det = await db.execute(select(LeadDetail))
        details = result_det.scalars().all()
        for det in details:
            cleaned = clean_phone(det.phone_number)
            if cleaned != det.phone_number:
                det.phone_number = cleaned
                details_fixed += 1
                
        print("3. Linking orphaned messages")
        msgs_linked = 0
        # Get orphaned messages
        stmt = select(Message).where(Message.lead_id.is_(None))
        orphans = (await db.execute(stmt)).scalars().all()
        
        # Build lead dict for fast lookup (cleaned phone -> lead_id)
        # Note: some leads might have duplicate phones, taking the first we see
        lead_dict = {lead.phone: lead.lead_id for lead in leads if lead.phone}
        
        for msg in orphans:
            cleaned_wa_id = clean_phone(msg.phone)
            # WATI messages might have been stored with their raw data 'waId' in phone column
            if cleaned_wa_id in lead_dict:
                msg.lead_id = lead_dict[cleaned_wa_id]
                msgs_linked += 1

        print("Committing to DB...")
        await db.commit()
        
        print("\n--- RESULTS ---")
        print(f"Leads cleaned: {leads_fixed}")
        print(f"LeadDetails cleaned: {details_fixed}")
        print(f"Orphaned messages linked: {msgs_linked}")
        print("----------------")

if __name__ == "__main__":
    asyncio.run(backfill())
