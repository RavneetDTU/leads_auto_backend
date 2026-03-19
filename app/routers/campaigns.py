from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from app.models import Campaign as CampaignSchema
from app.sql_models import Campaign
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Optional

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

@router.get("/active", response_model=List[CampaignSchema])
async def get_active_campaigns(db: AsyncSession = Depends(get_db)):
    """
    Get all ACTIVE campaigns.
    """
    stmt = select(Campaign).where(Campaign.status == "ACTIVE")
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/paused", response_model=List[CampaignSchema])
async def get_paused_campaigns(db: AsyncSession = Depends(get_db)):
    """
    Get all PAUSED campaigns.
    """
    stmt = select(Campaign).where(Campaign.status != "ACTIVE") # Assuming anything not ACTIVE is PAUSED/ARCHIVED
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/", response_model=List[CampaignSchema])
async def get_all_campaigns(sync: bool = False, db: AsyncSession = Depends(get_db)):
    """
    Get ALL campaigns.
    """
    if sync:
         from app.services.scheduler import fetch_and_process_leads
         try:
             await fetch_and_process_leads()
         except Exception as e:
             print(f"Error during manual sync: {e}")

    stmt = select(Campaign)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/{campaign_id}/template")
async def set_campaign_template(
    campaign_id: str, 
    template_name: str = Query(..., description="WATI Template Name"),
    db: AsyncSession = Depends(get_db)
):
    """
    Assign a WATI template to a campaign.
    """
    stmt = select(Campaign).where(Campaign.id == campaign_id)
    result = await db.execute(stmt)
    campaign = result.scalar_one_or_none()
        
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    campaign.template_name = template_name
    await db.commit()
    
    return {"message": "Template updated successfully", "campaign_id": campaign_id, "template_name": template_name}
