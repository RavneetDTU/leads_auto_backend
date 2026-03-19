import asyncio
from app.services.meta import meta_service
import logging
import sys
import json
import requests

logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

def debug_meta_leads():
    # Hardcoded ID from previous run for testing: NORWOOD/NORTHGATE – Copy (120236734983810281)
    camp_id = "120236734983810281" 
    logger.info(f"Debugging campaign: {camp_id}")
    
    try:
        ads = meta_service.get_ads(camp_id)
        logger.info(f"Found {len(ads)} ads")
        
        if not ads:
            logger.error("No ads found!")
            return

        ad_id = ads[0]["id"]
        logger.info(f"Testing Ad ID: {ad_id}")
        
        # Manually verify lead count via separate request to see if wrapper is hiding something
        url = f"{meta_service.base_url}/{ad_id}/leads"
        params = {
            "access_token": meta_service.access_token,
            "summary": "true",
            "limit": 1
        }
        resp = requests.get(url, params=params)
        logger.info(f"Raw API Status: {resp.status_code}")
        logger.info(f"Raw API Response: {resp.text}")

        # wrapper test
        leads = meta_service.get_leads_from_ad(ad_id, limit_total=5)
        logger.info(f"Wrapper returned {len(leads)} leads (default)")
        
    except Exception as e:
        logger.exception("Debug script failed")

if __name__ == "__main__":
    debug_meta_leads()
