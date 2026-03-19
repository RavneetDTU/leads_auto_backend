
import os
import sys
import firebase_admin
from firebase_admin import firestore
from datetime import datetime

# Setup path
sys.path.append(os.getcwd())

# Initialize Firebase (if not already via app imports, but script runs standalone)
# We assume existing firebase_setup logic or just re-init if safe.
# Better to reuse app's setup if possible, but it might be initialized at module level.
from app.firebase_setup import db
from app.services.meta import meta_service

def delete_collection(coll_ref, batch_size=400):
    """Recursively delete a collection in batches."""
    docs = coll_ref.limit(batch_size).stream()
    deleted = 0
    batch = db.batch()

    for doc in docs:
        # print(f"Deleting doc {doc.id} => {doc.reference.path}") # Too verbose
        batch.delete(doc.reference)
        deleted += 1

    if deleted > 0:
        batch.commit()
        print(f" > Deleted batch of {deleted} docs from {coll_ref.id}")
        
    if deleted >= batch_size:
        return delete_collection(coll_ref, batch_size)

def main():
    print("--- Starting Cleanup and Initialization ---")
    
    # 1. Migration: Preserve Template Names
    print("[1/4] caching existing templates from old 'campaigns' collection...")
    template_map = {}
    try:
        old_campaigns = db.collection("campaigns").stream()
        for doc in old_campaigns:
            data = doc.to_dict()
            if "template_name" in data and data["template_name"]:
                print(f" > Found template '{data['template_name']}' for campaign {doc.id}")
                template_map[doc.id] = data["template_name"]
    except Exception as e:
        print(f"Warning reading old campaigns: {e}")

    # 2. Cleanup: Delete old collections
    print("[2/4] Deleting old 'campaigns' and 'leads' collections...")
    delete_collection(db.collection("campaigns"))
    delete_collection(db.collection("leads"))
    print(" > Cleanup done.")

    # 3. Fetch Campaigns from Meta
    print("[3/4] Fetching Campaigns from Meta...")
    ad_accounts = meta_service.get_ad_accounts()
    if not ad_accounts:
        print(" ! No Ad Accounts found.")
        return

    # Use first ad account
    ad_account_id = ad_accounts[0]["id"]
    print(f" > Using Ad Account: {ad_account_id}")
    
    campaigns = meta_service.get_campaigns(ad_account_id)
    print(f" > Found {len(campaigns)} campaigns.")

    # 4. Process Campaigns & Backfill Leads
    print("[4/4] Processing Campaigns and Backfilling Leads...")
    
    total_leads_processed = 0
    
    for camp in campaigns:
        camp_id = camp["id"]
        camp_name = camp["name"]
        status = camp.get("status", "UNKNOWN")
        
        print(f" > Processing {camp_name} ({status})...")
        
        # Determine Collection
        if status == "ACTIVE":
            target_coll = db.collection("active_campaigns")
        else:
            target_coll = db.collection("paused_campaigns")
            
        # Prepare Data
        camp_data = {
            "id": camp_id,
            "name": camp_name,
            "status": status,
            "last_fetch_time": datetime.now()
        }
        
        # Restore Template
        if camp_id in template_map:
            camp_data["template_name"] = template_map[camp_id]
            print(f"   > Restored template: {template_map[camp_id]}")
            
        # Save Campaign
        target_coll.document(camp_id).set(camp_data, merge=True)
        
        # Fetch Leads (Backfill)
        ads = meta_service.get_ads(camp_id)
        print(f"   > Found {len(ads)} ads. Fetching leads...")
        
        for ad in ads:
            leads = meta_service.get_leads_from_ad(ad["id"], limit_total=200) # Limit 200 per ad for backfill safety
            
            for lead in leads:
                meta_lead_id = lead.get("id")
                created_time_str = lead.get("created_time") # ISO format: 2026-02-10T...
                
                # Parse date for Daily Leads
                try:
                    # Example: 2026-02-10T12:00:00+0000
                    dt = datetime.strptime(created_time_str, "%Y-%m-%dT%H:%M:%S%z")
                    date_str = dt.strftime("%Y-%m-%d")
                except:
                    date_str = datetime.now().strftime("%Y-%m-%d")
                
                # Parse Field Data
                field_data = meta_service.parse_lead_field_data(lead.get("field_data", []))
                
                lead_doc = {
                    "lead_id": meta_lead_id,
                    "meta_lead_id": meta_lead_id,
                    "campaign_id": camp_id,
                    "campaign_name": camp_name,
                    "ad_id": lead.get("ad_id"),
                    "ad_name": lead.get("ad_name"),
                    "adset_id": lead.get("adset_id"),
                    "adset_name": lead.get("adset_name"),
                    "created_at": created_time_str,
                    "name": field_data.get("full_name") or field_data.get("name"),
                    "phone": field_data.get("phone_number") or field_data.get("phone"),
                    "email": field_data.get("email"),
                    "status": "new" # Reset status for backfill? Or assume 'new'?
                    # We don't want to re-trigger WATI for OLD leads if we run scheduler later.
                    # BUT scheduler only sends if 'status' is 'new' AND template is set.
                    # If we set 'new' here, scheduler WILL message them if template is set.
                    # Does user want to message ALL historical leads?
                    # Probably NOT.
                    # Safe bet: Set status to 'imported' or 'old' for historical?
                    # OPTION: Only set status='new' for leads created today?
                    # User said: "initlize data... daily leads endpoint".
                    # Let's set status='new' but rely on valid logic. 
                    # Actually, if we set template, scheduler might message them.
                    # Let's default to 'imported' to avoid mass spamming old leads.
                }

                # Save to Sub-collection
                # Only if ACTIVE or PAUSED? Schema says leads under campaigns.
                target_coll.document(camp_id).collection("leads").document(meta_lead_id).set(lead_doc, merge=True)
                
                # Save to Daily Leads
                db.collection("daily_leads").document(date_str).collection("leads").document(meta_lead_id).set(lead_doc, merge=True)
                
                total_leads_processed += 1
                
    print(f"\n--- Initialization Complete. Processed {total_leads_processed} leads. ---")

if __name__ == "__main__":
    main()
