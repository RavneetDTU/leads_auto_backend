#!/usr/bin/env python3
"""
Meta Lead Ads API Experiment Script

This script:
1. Authenticates with Meta Graph API using access token
2. Fetches all ad accounts linked to the user
3. Gets campaigns (filtering for OUTCOME_LEADS objective)
4. Retrieves leads from each campaign's ads
5. Polls periodically for new leads

Usage:
    export PYTHONPATH=$PYTHONPATH:$(pwd)
    python experiments/meta_leads_experiment.py
"""

import os
import sys
import time
import json
from datetime import datetime
from typing import Dict, List, Set, Optional
import requests
from dotenv import load_dotenv

# Load environment variables from project root
load_dotenv()

# Configuration
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
POLL_INTERVAL_MINUTES = int(os.getenv("META_POLL_INTERVAL_MINUTES", "5"))
GRAPH_API_VERSION = "v24.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Track seen leads to avoid duplicates
seen_lead_ids: Set[str] = set()


def make_api_request(endpoint: str, params: Optional[Dict] = None) -> Dict:
    """Make a GET request to Meta Graph API."""
    if params is None:
        params = {}
    params["access_token"] = META_ACCESS_TOKEN
    
    url = f"{BASE_URL}/{endpoint}"
    response = requests.get(url, params=params)
    
    if response.status_code != 200:
        print(f"❌ API Error: {response.status_code}")
        print(f"   Response: {response.text}")
        return {"error": response.text}
    
    return response.json()


def get_all_pages(endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
    """Fetch all pages of data from a paginated endpoint."""
    all_data = []
    
    result = make_api_request(endpoint, params)
    if "error" in result:
        return all_data
    
    all_data.extend(result.get("data", []))
    
    # Handle pagination
    while "paging" in result and "next" in result["paging"]:
        next_url = result["paging"]["next"]
        response = requests.get(next_url)
        if response.status_code == 200:
            result = response.json()
            all_data.extend(result.get("data", []))
        else:
            break
    
    return all_data


def get_system_user_profile() -> Optional[Dict]:
    """Verify access token and get system user profile."""
    print("\n📋 Step 1: Verifying Access Token...")
    result = make_api_request("me")
    
    if "error" in result:
        print("❌ Failed to verify access token")
        return None
    
    print(f"✅ Authenticated as: {result.get('name')} (ID: {result.get('id')})")
    return result


def get_ad_accounts(user_id: str) -> List[Dict]:
    """Get all ad accounts linked to the user."""
    print("\n📋 Step 2: Fetching Ad Accounts...")
    accounts = get_all_pages(f"{user_id}/adaccounts")
    
    print(f"✅ Found {len(accounts)} ad account(s)")
    for acc in accounts:
        print(f"   - {acc.get('id')} (Account ID: {acc.get('account_id')})")
    
    return accounts


def get_lead_campaigns(ad_account_id: str) -> List[Dict]:
    """Get lead generation campaigns from an ad account."""
    print(f"\n📋 Step 3: Fetching Lead Campaigns from {ad_account_id}...")
    
    params = {
        "fields": "id,name,status,objective,start_time,stop_time"
    }
    
    campaigns = get_all_pages(f"{ad_account_id}/campaigns", params)
    
    # Filter for lead generation campaigns
    lead_campaigns = [c for c in campaigns if c.get("objective") == "OUTCOME_LEADS"]
    
    print(f"✅ Found {len(lead_campaigns)} lead campaign(s) out of {len(campaigns)} total")
    for camp in lead_campaigns:
        status_emoji = "🟢" if camp.get("status") == "ACTIVE" else "⚪"
        print(f"   {status_emoji} {camp.get('name')} (ID: {camp.get('id')}) - {camp.get('status')}")
    
    return lead_campaigns


def get_ads_for_campaign(campaign_id: str) -> List[Dict]:
    """Get all ads for a campaign."""
    print(f"\n📋 Step 4: Fetching Ads for Campaign {campaign_id}...")
    
    ads = get_all_pages(f"{campaign_id}/ads")
    
    print(f"✅ Found {len(ads)} ad(s)")
    for ad in ads:
        print(f"   - Ad ID: {ad.get('id')}")
    
    return ads


def get_leads_for_ad(ad_id: str) -> List[Dict]:
    """Get leads from an ad."""
    params = {
        "fields": "id,created_time,field_data"
    }
    
    leads = get_all_pages(f"{ad_id}/leads", params)
    return leads


def process_lead(lead: Dict) -> None:
    """Process and display a single lead."""
    lead_id = lead.get("id")
    
    if lead_id in seen_lead_ids:
        return  # Skip already seen leads
    
    seen_lead_ids.add(lead_id)
    
    created_time = lead.get("created_time", "Unknown")
    field_data = lead.get("field_data", [])
    
    print(f"\n   🆕 NEW LEAD (ID: {lead_id})")
    print(f"      Created: {created_time}")
    print("      Fields:")
    
    for field in field_data:
        name = field.get("name", "unknown")
        values = field.get("values", [])
        value = values[0] if values else "N/A"
        print(f"         - {name}: {value}")


def fetch_all_leads() -> int:
    """Fetch all leads from all campaigns. Returns count of new leads."""
    new_leads_count = 0
    
    # Step 1: Get user profile
    user = get_system_user_profile()
    if not user:
        return 0
    
    user_id = user.get("id")
    
    # Step 2: Get ad accounts
    accounts = get_ad_accounts(user_id)
    if not accounts:
        print("⚠️  No ad accounts found")
        return 0
    
    # Step 3 & 4 & 5: For each account, get campaigns, ads, and leads
    for account in accounts:
        ad_account_id = account.get("id")
        
        campaigns = get_lead_campaigns(ad_account_id)
        
        for campaign in campaigns:
            campaign_id = campaign.get("id")
            campaign_name = campaign.get("name")
            
            print(f"\n📋 Step 5: Fetching Leads for Campaign: {campaign_name}...")
            
            ads = get_ads_for_campaign(campaign_id)
            
            for ad in ads:
                ad_id = ad.get("id")
                leads = get_leads_for_ad(ad_id)
                
                if leads:
                    print(f"   Found {len(leads)} lead(s) from Ad {ad_id}")
                    for lead in leads:
                        if lead.get("id") not in seen_lead_ids:
                            new_leads_count += 1
                        process_lead(lead)
                else:
                    print(f"   No leads from Ad {ad_id}")
    
    return new_leads_count


def run_polling_loop():
    """Run the continuous polling loop."""
    print("\n" + "=" * 60)
    print("🔄 META LEAD ADS POLLING STARTED")
    print(f"   Polling every {POLL_INTERVAL_MINUTES} minute(s)")
    print("   Press Ctrl+C to stop")
    print("=" * 60)
    
    poll_count = 0
    
    while True:
        poll_count += 1
        print(f"\n{'=' * 60}")
        print(f"📊 POLL #{poll_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        try:
            new_leads = fetch_all_leads()
            print(f"\n✅ Poll complete. New leads found: {new_leads}")
            print(f"   Total leads tracked: {len(seen_lead_ids)}")
        except Exception as e:
            print(f"\n❌ Error during poll: {e}")
        
        # Wait for next poll
        print(f"\n⏳ Next poll in {POLL_INTERVAL_MINUTES} minute(s)...")
        time.sleep(POLL_INTERVAL_MINUTES * 60)


def main():
    """Main entry point."""
    print("=" * 60)
    print("🚀 META LEAD ADS API EXPERIMENT")
    print("=" * 60)
    
    # Validate configuration
    if not META_ACCESS_TOKEN:
        print("\n❌ ERROR: META_ACCESS_TOKEN not set in environment")
        print("   Please add it to your .env file:")
        print("   META_ACCESS_TOKEN=your_access_token_here")
        sys.exit(1)
    
    print(f"\n✅ Configuration loaded:")
    print(f"   - Access Token: {META_ACCESS_TOKEN[:20]}...")
    print(f"   - Poll Interval: {POLL_INTERVAL_MINUTES} minutes")
    print(f"   - API Version: {GRAPH_API_VERSION}")
    
    # Ask user for mode
    print("\n📌 Select Mode:")
    print("   1. One-time fetch (fetch leads once and exit)")
    print("   2. Continuous polling (fetch leads every X minutes)")
    
    mode = input("\nEnter choice (1 or 2): ").strip()
    
    if mode == "2":
        run_polling_loop()
    else:
        new_leads = fetch_all_leads()
        print(f"\n✅ Fetch complete. Total leads found: {new_leads}")


if __name__ == "__main__":
    main()
