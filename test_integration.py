
import os
import sys
import uuid
import time
from unittest.mock import MagicMock, patch

# Ensure app module can be found
sys.path.append(os.getcwd())

from fastapi.testclient import TestClient
from app.main import app
from app.services.meta import meta_service
from app.services.wati import wati_service
from app.firebase_setup import db
from datetime import datetime

client = TestClient(app)

def run_integration_test():
    """
    Simulates the full flow for Schema V2:
    1. Sync Campaigns (Verify Active/Paused sorting)
    2. Add Lead to Active Campaign (Verify sub-collection & daily collection & WATI auto-send)
    3. Move Campaign to Paused (Verify move logic)
    """
    print("--- Starting Integration Test (Schema Refactor) ---")
    
    # Mock Data
    mock_ad_accounts = [{"id": "act_123", "name": "Test Ad Account"}]
    
    # 1. Active & Paused Campaigns
    mock_campaigns_mixed = [
        {"id": "camp_active_001", "name": "Active Campaign", "status": "ACTIVE"},
        {"id": "camp_paused_001", "name": "Paused Campaign", "status": "PAUSED"}
    ]
    
    # Mock Leads for Active Campaign
    mock_ads = [{"id": "ad_123", "name": "Ad 1"}]
    mock_leads_list = [
        {
            "id": "lead_active_100", 
            "ad_id": "ad_123",
            "field_data": [
                {"name": "full_name", "values": ["Active Lead"]},
                {"name": "phone_number", "values": ["+919999999999"]}
            ]
        }
    ]

    # Patch Everything for Step 1 & 2
    with patch("app.services.meta.MetaService.get_ad_accounts", return_value=mock_ad_accounts), \
         patch("app.services.meta.MetaService.get_campaigns", return_value=mock_campaigns_mixed), \
         patch("app.services.meta.MetaService.get_ads", return_value=mock_ads), \
         patch("app.services.meta.MetaService.get_leads_from_ad", return_value=mock_leads_list), \
         patch("app.services.wati.WatiService.send_template_message", return_value={"result": True}) as mock_send_wati:
         
         print("\n[Step 1] Triggering Sync (Initial Campaign Sync)...")
         # We force sync via the manual trigger endpoint to run the full scheduler logic
         resp = client.post("/trigger-sync")
         assert resp.status_code == 200
         
         # Verify Collections
         active_doc = db.collection("active_campaigns").document("camp_active_001").get()
         paused_doc = db.collection("paused_campaigns").document("camp_paused_001").get()
         
         if active_doc.exists and paused_doc.exists:
             print("SUCCESS: Campaigns sorted into Active/Paused collections.")
         else:
             print("FAILURE: Campaigns NOT sorted correctly.")
             
         # --- Pre-requisite: Set Template for Active Campaign ---
         # The router now checks active/paused collections
         print("\n[Step 2] Setting Template...")
         client.post("/campaigns/camp_active_001/template?template_name=welcome_template")
         print(" > Template set for active campaign.")
         
         print("\n[Step 3] Triggering Sync (Lead Fetch)...")
         # Now that template is set, next sync should process leads and send WATI
         client.post("/trigger-sync")
         
         # Verify Lead in Sub-collection
         lead_sub_ref = db.collection("active_campaigns").document("camp_active_001").collection("leads").document("lead_active_100")
         if lead_sub_ref.get().exists:
              print("SUCCESS: Lead saved to active_campaigns sub-collection.")
         else:
              print("FAILURE: Lead NOT found in sub-collection.")
              
         # Verify Daily Leads
         today = datetime.now().strftime("%Y-%m-%d")
         daily_ref = db.collection("daily_leads").document(today).collection("leads").document("lead_active_100")
         if daily_ref.get().exists:
              print("SUCCESS: Lead saved to daily_leads.")
         else:
              print("FAILURE: Lead NOT found in daily_leads.")
         
         # Check WATI auto-send (Step 2 of sync)
         if mock_send_wati.called:
              print("SUCCESS: WATI message sent.")
         else:
              print("FAILURE: WATI message NOT sent.")

    # --- Step 4: Move Campaign ---
    print("\n[Step 4] Testing Campaign Move (Active -> Paused)...")
    
    mock_campaigns_moved = [
        {"id": "camp_active_001", "name": "Active Campaign", "status": "PAUSED"},
        {"id": "camp_paused_001", "name": "Paused Campaign", "status": "PAUSED"}
    ]
    
    with patch("app.services.meta.MetaService.get_ad_accounts", return_value=mock_ad_accounts), \
         patch("app.services.meta.MetaService.get_campaigns", return_value=mock_campaigns_moved):
         
         client.post("/trigger-sync")
         
         # Check if moved
         old_active_ref = db.collection("active_campaigns").document("camp_active_001")
         new_paused_ref = db.collection("paused_campaigns").document("camp_active_001")
         
         # It should be gone from active and present in paused
         if not old_active_ref.get().exists and new_paused_ref.get().exists:
             print("SUCCESS: Campaign moved from Active to Paused.")
             
             # Check if template name preserved
             # Note: The move logic in scheduler *should* preserve it if we implemented it right
             tmpl_name = new_paused_ref.get().to_dict().get("template_name")
             if tmpl_name == "welcome_template":
                  print("SUCCESS: Template name preserved.")
             else:
                  print(f"FAILURE: Template name LOST. Found: {tmpl_name}")
         else:
             print("FAILURE: Campaign move failed.")

    print("\n--- Integration Test Finished ---")

if __name__ == "__main__":
    run_integration_test()
