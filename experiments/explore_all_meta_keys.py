"""
Explore ALL keys returned by Meta Graph API at each level:
  - Campaign fields
  - AdSet fields 
  - Ad fields
  - Lead fields (with full field_data)

This script dumps the RAW JSON responses so we can identify
all available keys, including branch data.
"""
import requests
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv()

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
if not ACCESS_TOKEN:
    print("Error: META_ACCESS_TOKEN not found in environment variables.")
    sys.exit(1)

BASE_URL = "https://graph.facebook.com/v24.0"


def api_get(url, params=None):
    """Helper to make API calls and return JSON."""
    if params is None:
        params = {}
    params["access_token"] = ACCESS_TOKEN
    resp = requests.get(url, params=params)
    return resp.json()


def collect_all_keys(data_list, label=""):
    """Collect and print all unique keys from a list of API objects."""
    all_keys = set()
    for item in data_list:
        all_keys.update(item.keys())
    print(f"\n{'='*60}")
    print(f"ALL KEYS at [{label}] level ({len(all_keys)} keys):")
    print(f"{'='*60}")
    for key in sorted(all_keys):
        print(f"  - {key}")
    return sorted(all_keys)


def explore():
    # Step 1: Get user
    print("--- Step 1: Get User ---")
    user = api_get(f"{BASE_URL}/me")
    if 'error' in user:
        print(f"Error: {json.dumps(user, indent=2)}")
        return
    user_id = user['id']
    print(f"User ID: {user_id}, Name: {user.get('name', 'N/A')}")

    # Step 2: Get Ad Accounts
    print("\n--- Step 2: Get Ad Accounts ---")
    accounts = api_get(f"{BASE_URL}/{user_id}/adaccounts")
    if not accounts.get('data'):
        print("No ad accounts found.")
        return
    
    ad_account_id = accounts['data'][0]['id']
    print(f"Using Ad Account: {ad_account_id}")

    # Step 3: Get ALL campaigns (requesting ALL possible fields)
    print("\n--- Step 3: Get Campaigns (ALL fields) ---")
    # Request a broad set of campaign fields
    campaign_fields = (
        "id,name,status,objective,start_time,stop_time,created_time,"
        "updated_time,effective_status,daily_budget,lifetime_budget,"
        "budget_remaining,spend_cap,buying_type,configured_status,"
        "special_ad_categories,source_campaign_id,bid_strategy"
    )
    campaigns = api_get(
        f"{BASE_URL}/{ad_account_id}/campaigns",
        {"fields": campaign_fields, "limit": 100}
    )
    
    if not campaigns.get('data'):
        print("No campaigns found.")
        return

    print(f"Found {len(campaigns['data'])} campaigns")
    collect_all_keys(campaigns['data'], "CAMPAIGN")
    
    # Print first campaign raw data as sample
    print("\n--- Sample Campaign (raw JSON) ---")
    print(json.dumps(campaigns['data'][0], indent=2))

    # Find an active campaign with leads, or just use the first
    target_campaign = None
    for c in campaigns['data']:
        if c.get('status') == 'ACTIVE' or c.get('effective_status') == 'ACTIVE':
            target_campaign = c
            break
    if not target_campaign:
        target_campaign = campaigns['data'][0]
    
    campaign_id = target_campaign['id']
    print(f"\n*** Using Campaign: {target_campaign['name']} ({campaign_id}) ***")

    # Step 4: Get ALL Ad Sets for campaign (with many fields)
    print("\n--- Step 4: Get AdSets (ALL fields) ---")
    adset_fields = (
        "id,name,status,campaign_id,daily_budget,lifetime_budget,"
        "start_time,end_time,created_time,updated_time,effective_status,"
        "bid_amount,billing_event,optimization_goal,targeting,"
        "promoted_object,destination_type"
    )
    adsets = api_get(
        f"{BASE_URL}/{campaign_id}/adsets",
        {"fields": adset_fields, "limit": 100}
    )
    
    if not adsets.get('data'):
        print("No ad sets found for this campaign.")
    else:
        print(f"Found {len(adsets['data'])} ad sets")
        collect_all_keys(adsets['data'], "ADSET")
        print("\n--- Sample AdSet (raw JSON) ---")
        print(json.dumps(adsets['data'][0], indent=2))

    # Step 5: Get ALL Ads for the campaign (with many fields)
    print("\n--- Step 5: Get Ads (ALL fields) ---")
    ad_fields = (
        "id,name,status,adset_id,campaign_id,created_time,updated_time,"
        "effective_status,creative,tracking_specs,conversion_specs"
    )
    ads = api_get(
        f"{BASE_URL}/{campaign_id}/ads",
        {"fields": ad_fields, "limit": 100}
    )
    
    if not ads.get('data'):
        print("No ads found for this campaign.")
        return
    
    print(f"Found {len(ads['data'])} ads")
    collect_all_keys(ads['data'], "AD")
    print("\n--- Sample Ad (raw JSON) ---")
    print(json.dumps(ads['data'][0], indent=2))

    # Step 6: Get leads from each Ad - dump ALL fields
    print("\n\n" + "=" * 80)
    print("STEP 6: GET LEADS WITH ALL FIELDS")
    print("=" * 80)
    
    # Request ALL known lead fields
    lead_fields = (
        "id,created_time,field_data,ad_id,ad_name,adset_id,adset_name,"
        "campaign_id,campaign_name,form_id,is_organic,platform,"
        "retailer_item_id,partner_name"
    )
    
    total_leads_found = 0
    all_field_data_keys = set()  # Track all keys inside field_data
    all_lead_top_keys = set()   # Track all top-level lead keys
    
    for ad in ads['data']:
        ad_id = ad['id']
        ad_name = ad.get('name', 'N/A')
        
        leads = api_get(
            f"{BASE_URL}/{ad_id}/leads",
            {"fields": lead_fields, "limit": 25}
        )
        
        lead_data = leads.get('data', [])
        if lead_data:
            total_leads_found += len(lead_data)
            print(f"\n  Ad: {ad_name} ({ad_id}) -> {len(lead_data)} leads")
            
            for lead in lead_data:
                all_lead_top_keys.update(lead.keys())
                
                # Extract all field_data keys
                fd = lead.get('field_data', [])
                for field in fd:
                    field_name = field.get('name', '')
                    all_field_data_keys.add(field_name)
            
            # Print first lead as raw sample
            if lead_data:
                print(f"\n  --- Sample Lead from Ad '{ad_name}' (raw JSON) ---")
                print(json.dumps(lead_data[0], indent=2))
    
    # Summary
    print("\n\n" + "=" * 80)
    print("SUMMARY OF ALL KEYS FOUND")
    print("=" * 80)
    
    print(f"\nTotal leads found: {total_leads_found}")
    
    print(f"\n--- TOP-LEVEL Lead Keys ({len(all_lead_top_keys)}) ---")
    for k in sorted(all_lead_top_keys):
        print(f"  - {k}")
    
    print(f"\n--- field_data Keys (inside each lead) ({len(all_field_data_keys)}) ---")
    for k in sorted(all_field_data_keys):
        print(f"  - {k}")
    
    # Step 7: Try to get lead gen forms for the campaign/page to find form structure
    print("\n\n" + "=" * 80)
    print("STEP 7: EXPLORE LEAD GEN FORMS")
    print("=" * 80)
    
    # Get forms from the page if we can find a page_id
    # First check if any adset has promoted_object with page_id
    page_id = None
    if adsets.get('data'):
        for adset in adsets['data']:
            po = adset.get('promoted_object', {})
            if isinstance(po, dict) and po.get('page_id'):
                page_id = po['page_id']
                break
    
    if page_id:
        print(f"\nFound Page ID: {page_id}")
        forms = api_get(
            f"{BASE_URL}/{page_id}/leadgen_forms",
            {"fields": "id,name,status,questions,created_time", "limit": 50}
        )
        if forms.get('data'):
            print(f"Found {len(forms['data'])} lead gen forms")
            for form in forms['data']:
                print(f"\n  Form: {form.get('name')} ({form.get('id')})")
                questions = form.get('questions', [])
                if questions:
                    print(f"  Questions/Fields ({len(questions)}):")
                    for q in questions:
                        print(f"    - key: {q.get('key', 'N/A')} | type: {q.get('type', 'N/A')} | label: {q.get('label', 'N/A')}")
        else:
            print(f"No forms found or error: {json.dumps(forms, indent=2)}")
    else:
        print("Could not find page_id from adsets to query forms.")


if __name__ == "__main__":
    explore()
