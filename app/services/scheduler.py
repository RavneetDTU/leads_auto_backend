from app.database import AsyncSessionLocal
from app.services.meta import meta_service
from app.services.wati import wati_service
from app.sql_models import Lead, Campaign, LeadDetail
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timezone
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_and_process_leads():
    """
    Background task to:
    1. Fetch Active campaigns from Meta. (And update their status in DB)
    2. Sync them to 'campaigns' table.
    3. For ACTIVE campaigns:
        a. Fetch new leads.
        b. Insert into 'leads' table (ignoring duplicates).
        c. Send WATI template message if new.
    
    All blocking Meta API calls are run in a thread pool via asyncio.to_thread()
    so they don't block the event loop and the API stays responsive.
    """
    logger.info(f"Starting lead fetch job at {datetime.now()}")
    
    async with AsyncSessionLocal() as session:
        try:
            # 1. Sync Campaigns
            # Assuming single ad account for now
            ad_accounts = await asyncio.to_thread(meta_service.get_ad_accounts)
            if not ad_accounts:
                logger.warning("No ad accounts found.")
                return
                
            ad_account_id = ad_accounts[0]["id"]
            meta_campaigns = await asyncio.to_thread(meta_service.get_campaigns, ad_account_id)
            
            active_campaign_ids = []
            
            for mc in meta_campaigns:
                camp_id = mc["id"]
                status = mc.get("status", "UNKNOWN")
                
                # Prepare Campaign Data
                campaign_data = {
                    "id": camp_id,
                    "name": mc["name"],
                    "status": status,
                    "updated_at": datetime.utcnow()
                }
                
                # Check if campaign exists to preserve template_name
                stmt = select(Campaign).where(Campaign.id == camp_id)
                result = await session.execute(stmt)
                existing_campaign = result.scalar_one_or_none()
                
                if existing_campaign:
                    # Update status and name
                    existing_campaign.name = mc["name"]
                    existing_campaign.status = status
                    existing_campaign.updated_at = datetime.utcnow()
                else:
                    # Insert new
                    new_campaign = Campaign(**campaign_data)
                    session.add(new_campaign)
                
                if status == "ACTIVE":
                    active_campaign_ids.append(camp_id)
            
            await session.commit()
            logger.info(f"Synced {len(meta_campaigns)} campaigns. {len(active_campaign_ids)} are ACTIVE.")

            # 2. Process Leads for ACTIVE Campaigns
            for camp_id in active_campaign_ids:
                # Get campaign to have template_name handy
                stmt = select(Campaign).where(Campaign.id == camp_id)
                result = await session.execute(stmt)
                campaign = result.scalar_one()
                
                template_name = campaign.template_name
                
                # Fetch Ads (in thread pool to avoid blocking event loop)
                ads = await asyncio.to_thread(meta_service.get_ads, camp_id)
                
                for ad in ads:
                    ad_id = ad.get("id")
                    if not ad_id:
                        continue

                    # Fetch leads from Ad (in thread pool)
                    leads_data = await asyncio.to_thread(meta_service.get_leads_from_ad, ad_id)
                    
                    for lead_raw in leads_data:
                        meta_lead_id = lead_raw.get("id")
                        
                        # Check existance
                        stmt = select(Lead).where(Lead.meta_lead_id == meta_lead_id)
                        result = await session.execute(stmt)
                        if result.scalar_one_or_none():
                            continue # Skip if already exists
                        
                        # Parse Info
                        field_data = lead_raw.get("field_data", [])
                        parsed_fields = meta_service.parse_lead_field_data(field_data)
                        name = parsed_fields.get("name", "Unknown")
                        phone = parsed_fields.get("phone", "")
                        email = parsed_fields.get("email")
                        
                        if not phone:
                            logger.info(f"Skipping lead {meta_lead_id} due to missing phone.")
                            continue

                        # Use Meta's actual created_time (UTC) for accuracy
                        # Falls back to utcnow() if not provided
                        meta_created_str = lead_raw.get("created_time", "")
                        try:
                            # Meta returns ISO format: "2026-02-20T08:15:37+0000"
                            created_at_utc = datetime.fromisoformat(
                                meta_created_str.replace("+0000", "+00:00")
                            ).replace(tzinfo=None)  # Store as naive UTC in DB
                        except Exception:
                            created_at_utc = datetime.utcnow()

                        # Create Lead Object
                        new_lead = Lead(
                            lead_id = meta_lead_id,
                            meta_lead_id = meta_lead_id,
                            name = name,
                            phone = phone,
                            email = email,
                            campaign_id = camp_id,
                            campaign_name = campaign.name,
                            status = "new",
                            created_at = created_at_utc,
                            created_date = created_at_utc.date(),
                            ad_id = lead_raw.get("ad_id"),
                            ad_name = lead_raw.get("ad_name"),
                            adset_id = lead_raw.get("adset_id"),
                            adset_name = lead_raw.get("adset_name"),
                            # Branch / Practice fields
                            province = parsed_fields.get("province"),
                            preferred_practice = parsed_fields.get("preferred_practice"),
                            practice_to_visit = parsed_fields.get("practice_to_visit"),
                            practice_location = parsed_fields.get("practice_location"),
                            practice_to_attend = parsed_fields.get("practice_to_attend"),
                        )
                        
                        session.add(new_lead)

                        # Auto-populate LeadDetail from Meta fields
                        branch_name = (
                            parsed_fields.get("preferred_practice") or
                            parsed_fields.get("practice_to_attend") or
                            parsed_fields.get("practice_to_visit") or
                            parsed_fields.get("practice_location")
                        )
                        detail = LeadDetail(
                            lead_id=meta_lead_id,
                            name=name,
                            email=email,
                            phone_number=phone,
                            branch_name=branch_name,
                            updated_at=datetime.utcnow(),
                        )
                        session.add(detail)

                        logger.info(f"Saved new lead: {name} ({meta_lead_id}) [branch: {branch_name}]")
                        
                        # Optional: Send WATI message if template is configured
                        # if template_name:
                        #     wati_service.send_template_message(...)

                # Update timestamp for campaign
                campaign.last_fetch_time = datetime.utcnow()
                
            await session.commit()
            logger.info("Lead fetch job completed.")

        except Exception as e:
            logger.error(f"Error in fetch_and_process_leads: {e}")
            await session.rollback()

