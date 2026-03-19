
import os
import sys
import firebase_admin
from firebase_admin import firestore

sys.path.append(os.getcwd())
from app.firebase_setup import db

def count_leads():
    print("--- Verifying Data Backfill ---")
    
    # 1. Active Campaigns
    active_camps = list(db.collection("active_campaigns").stream())
    print(f"Active Campaigns: {len(active_camps)}")
    
    total_leads = 0
    for camp in active_camps:
        leads = list(camp.reference.collection("leads").stream())
        count = len(leads)
        if count > 0:
            print(f" - {camp.to_dict().get('name', camp.id)}: {count} leads")
        total_leads += count
        
    print(f"Total Leads in Active Campaigns: {total_leads}")
    
    # 2. Daily Leads (Sample check for today)
    # This might be huge, just checking if collection exists/has entries
    # daily_leads = list(db.collection("daily_leads").limit(5).stream())
    # print(f"Daily Lead Dates: {[d.id for d in daily_leads]}")

if __name__ == "__main__":
    count_leads()
