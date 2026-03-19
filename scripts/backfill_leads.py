#!/usr/bin/env python3
"""
One-time backfill script: Fetches ALL leads from Meta for active campaigns
and stores them in Firestore (campaign subcollections + daily_leads).

Usage:
    cd /home/rpsoftwarelab/Documents/2026_Projects/leads_auto
    source venv/bin/activate
    python scripts/backfill_leads.py

Rate limiting: 2s pause between API calls, 5s between campaigns.
"""

import os
import sys
import time
import logging
from datetime import datetime

# Setup path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.firebase_setup import db
from app.services.meta import meta_service

# --- Logging Setup ---
LOG_FILE = os.path.join(os.path.dirname(__file__), "backfill.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("backfill")

# --- Rate Limit Config ---
PAUSE_BETWEEN_API_CALLS = 2    # seconds between each Meta API call
PAUSE_BETWEEN_CAMPAIGNS = 5    # seconds between each campaign
PAUSE_BETWEEN_LEADS_PAGES = 2  # seconds between pagination pages


def backfill_active_campaigns():
    log.info("=" * 60)
    log.info("STARTING ACTIVE CAMPAIGN LEAD BACKFILL")
    log.info("=" * 60)

    if not db:
        log.error("Firebase not initialized. Exiting.")
        return

    if not meta_service.access_token:
        log.error("META_ACCESS_TOKEN not set. Exiting.")
        return

    # Step 1: Get Ad Account
    log.info("Fetching ad accounts from Meta...")
    accounts = meta_service.get_ad_accounts()
    if not accounts:
        log.error("No ad accounts found. Exiting.")
        return

    ad_account_id = accounts[0]["id"]
    log.info(f"Using ad account: {ad_account_id}")

    time.sleep(PAUSE_BETWEEN_API_CALLS)

    # Step 2: Get ALL campaigns, filter active
    log.info("Fetching campaigns...")
    all_campaigns = meta_service.get_campaigns(ad_account_id)
    active_campaigns = [c for c in all_campaigns if c.get("status") == "ACTIVE"]

    log.info(f"Total campaigns: {len(all_campaigns)}")
    log.info(f"Active campaigns: {len(active_campaigns)}")

    time.sleep(PAUSE_BETWEEN_API_CALLS)

    total_new = 0
    total_skipped = 0
    total_no_phone = 0

    # Step 3: Process each active campaign
    for idx, camp in enumerate(active_campaigns, 1):
        camp_id = camp["id"]
        camp_name = camp["name"]
        log.info("")
        log.info(f"--- [{idx}/{len(active_campaigns)}] Campaign: {camp_name} ({camp_id}) ---")

        camp_ref = db.collection("active_campaigns").document(camp_id)

        # Fetch ads for this campaign
        time.sleep(PAUSE_BETWEEN_API_CALLS)
        ads = meta_service.get_ads(camp_id)
        log.info(f"  Found {len(ads)} ad(s)")

        camp_new = 0
        camp_skipped = 0

        for ad_idx, ad in enumerate(ads, 1):
            ad_id = ad.get("id")
            ad_name = ad.get("name", "Unknown")
            if not ad_id:
                continue

            log.info(f"  Ad [{ad_idx}/{len(ads)}]: {ad_name} ({ad_id})")

            # Fetch leads from this ad (with pagination, up to 500)
            time.sleep(PAUSE_BETWEEN_API_CALLS)
            leads_data = meta_service.get_leads_from_ad(ad_id, limit_total=500)
            log.info(f"    Fetched {len(leads_data)} lead(s) from Meta")

            for lead_raw in leads_data:
                meta_lead_id = lead_raw.get("id")
                if not meta_lead_id:
                    continue

                # Check duplicate in campaign subcollection
                lead_ref = camp_ref.collection("leads").document(meta_lead_id)
                if lead_ref.get().exists:
                    camp_skipped += 1
                    continue

                # Parse lead fields
                field_data = lead_raw.get("field_data", [])
                parsed = meta_service.parse_lead_field_data(field_data)
                name = parsed.get("name", "Unknown")
                phone = parsed.get("phone", "")
                email = parsed.get("email")

                if not phone:
                    total_no_phone += 1
                    continue

                # Parse created_time from Meta
                created_time_str = lead_raw.get("created_time", "")
                try:
                    created_at = datetime.fromisoformat(
                        created_time_str.replace("+0000", "+00:00")
                    ) if created_time_str else datetime.now()
                except Exception:
                    created_at = datetime.now()

                new_lead = {
                    "lead_id": meta_lead_id,
                    "meta_lead_id": meta_lead_id,
                    "name": name,
                    "phone": phone,
                    "email": email,
                    "campaign_id": camp_id,
                    "campaign_name": camp_name,
                    "status": "new",
                    "created_at": created_at,
                    "ad_id": lead_raw.get("ad_id"),
                    "ad_name": lead_raw.get("ad_name"),
                    "adset_id": lead_raw.get("adset_id"),
                    "adset_name": lead_raw.get("adset_name"),
                    # Branch / Practice fields
                    "province": parsed.get("province"),
                    "preferred_practice": parsed.get("preferred_practice"),
                    "practice_to_visit": parsed.get("practice_to_visit"),
                    "practice_location": parsed.get("practice_location"),
                    "practice_to_attend": parsed.get("practice_to_attend"),
                }

                # A. Save to campaign subcollection
                lead_ref.set(new_lead)

                # B. Save to daily_leads
                date_str = created_at.strftime("%Y-%m-%d")
                daily_ref = (
                    db.collection("daily_leads")
                    .document(date_str)
                    .collection("leads")
                    .document(meta_lead_id)
                )
                daily_ref.set(new_lead)

                camp_new += 1

            # Small pause after processing each ad's leads
            time.sleep(PAUSE_BETWEEN_API_CALLS)

        log.info(f"  ✅ Campaign done: {camp_new} new, {camp_skipped} skipped (already existed)")
        total_new += camp_new
        total_skipped += camp_skipped

        # Pause between campaigns to respect rate limits
        if idx < len(active_campaigns):
            log.info(f"  Pausing {PAUSE_BETWEEN_CAMPAIGNS}s before next campaign...")
            time.sleep(PAUSE_BETWEEN_CAMPAIGNS)

    # Summary
    log.info("")
    log.info("=" * 60)
    log.info("BACKFILL COMPLETE")
    log.info(f"  Total new leads saved:     {total_new}")
    log.info(f"  Total duplicates skipped:  {total_skipped}")
    log.info(f"  Total skipped (no phone):  {total_no_phone}")
    log.info("=" * 60)


if __name__ == "__main__":
    try:
        backfill_active_campaigns()
    except KeyboardInterrupt:
        log.info("\nBackfill interrupted by user. Progress so far is saved.")
    except Exception as e:
        log.error(f"Backfill failed with error: {e}", exc_info=True)
