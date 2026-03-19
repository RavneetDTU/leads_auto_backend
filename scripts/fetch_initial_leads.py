import asyncio
from app.database import AsyncSessionLocal
from app.services.meta import meta_service
from app.sql_models import Lead, Campaign
from sqlalchemy import select
from datetime import datetime
import logging
import sys

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def fetch_initial_leads():
    logger.info("Starting initial lead fetch for ACTIVE campaigns...")
    
    async with AsyncSessionLocal() as session:
        try:
            # 1. Sync Campaigns
            ad_accounts = meta_service.get_ad_accounts()
            if not ad_accounts:
                logger.warning("No ad accounts found.")
                return
                
            ad_account_id = ad_accounts[0]["id"]
            logger.info(f"Using Ad Account: {ad_account_id}")
            
            meta_campaigns = meta_service.get_campaigns(ad_account_id)
            active_campaign_ids = []
            
            # Sync all campaigns first
            for mc in meta_campaigns:
                camp_id = mc["id"]
                status = mc.get("status", "UNKNOWN")
                
                campaign_data = {
                    "id": camp_id,
                    "name": mc["name"],
                    "status": status,
                    "updated_at": datetime.utcnow()
                }
                
                stmt = select(Campaign).where(Campaign.id == camp_id)
                result = await session.execute(stmt)
                existing_campaign = result.scalar_one_or_none()
                
                if existing_campaign:
                    existing_campaign.name = mc["name"]
                    existing_campaign.status = status
                    existing_campaign.updated_at = datetime.utcnow()
                else:
                    new_campaign = Campaign(**campaign_data)
                    session.add(new_campaign)
                
                if status == "ACTIVE":
                    active_campaign_ids.append(camp_id)
            
            await session.commit()
            logger.info(f"Synced {len(meta_campaigns)} campaigns. {len(active_campaign_ids)} are ACTIVE.")

            # 2. Process Leads for ACTIVE Campaigns
            total_leads_fetched = 0
            
            for camp_id in active_campaign_ids:
                stmt = select(Campaign).where(Campaign.id == camp_id)
                result = await session.execute(stmt)
                campaign = result.scalar_one()
                
                logger.info(f"Processing Campaign: {campaign.name} ({camp_id})")
                
                ads = meta_service.get_ads(camp_id)
                logger.info(f"  Found {len(ads)} ads.")
                
                campaign_leads_count = 0
                
                for ad in ads:
                    ad_id = ad.get("id")
                    if not ad_id:
                        continue

                    # Fetch ALL leads from Ad (pagination handled in meta_service)
                    # Use a large limit to get everything initially
                    # Start from Jan 1, 2023 to capture historical leads
                    # 1672531200 = 2023-01-01
                    leads_data = meta_service.get_leads_from_ad(ad_id, since_timestamp=1672531200, limit_total=5000)
                    
                    for lead_raw in leads_data:
                        meta_lead_id = lead_raw.get("id")
                        
                        stmt = select(Lead).where(Lead.meta_lead_id == meta_lead_id)
                        result = await session.execute(stmt)
                        if result.scalar_one_or_none():
                            continue 
                        
                        field_data = lead_raw.get("field_data", [])
                        parsed_fields = meta_service.parse_lead_field_data(field_data)
                        name = parsed_fields.get("name", "Unknown")
                        phone = parsed_fields.get("phone", "")
                        email = parsed_fields.get("email")
                        
                        if not phone:
                            continue

                        now = datetime.utcnow()
                        # Try to parse created_time from Meta if available, else use now
                        created_time_str = lead_raw.get("created_time")
                        if created_time_str:
                            try:
                                # Example: 2023-10-27T10:00:00+0000
                                created_at = datetime.strptime(created_time_str, "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)
                            except ValueError as e:
                                logger.warning(f"Date parse error for {created_time_str}: {e}")
                                created_at = now
                        else:
                            logger.warning(f"No created_time for lead {meta_lead_id}, using now.")
                            created_at = now

                        # logger.info(f"Lead {meta_lead_id} date: {created_at}") # Debug log

                        new_lead = Lead(
                            lead_id = meta_lead_id, 
                            meta_lead_id = meta_lead_id,
                            name = name,
                            phone = phone,
                            email = email,
                            campaign_id = camp_id,
                            campaign_name = campaign.name,
                            status = "new",
                            created_at = created_at,
                            created_date = created_at.date(), 
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
                        campaign_leads_count += 1
                        total_leads_fetched += 1
                        
                        # Commit every 50 leads to avoid huge transaction
                        if campaign_leads_count % 50 == 0:
                            await session.commit()
                            print(f"    Synced {campaign_leads_count} leads...", end="\r")

                # Update timestamp for campaign
                campaign.last_fetch_time = datetime.utcnow()
                await session.commit()
                logger.info(f"  Finished Campaign: {campaign.name}. Total leads synced: {campaign_leads_count}")
            
            logger.info(f"Initial fetch completed. Total leads added: {total_leads_fetched}")

        except Exception as e:
            logger.error(f"Error in fetch_initial_leads: {e}")
            await session.rollback()

if __name__ == "__main__":
    asyncio.run(fetch_initial_leads())
