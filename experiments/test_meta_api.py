import requests
import json
import os
import sys

# Ensure app module can be found if needed, but for this independent script it might not be strictly necessary
# However, good practice to separate concerns.
sys.path.append(os.getcwd())

# Configuration - REPLACE WITH YOUR ACTUAL TOKENS OR LOAD FROM ENV
# For this experiment, I will use the values provided in the prompt or loaded from .env if available.
from dotenv import load_dotenv
load_dotenv()

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
# If not in env, fall back to hardcoded for testing (user provided in prompt)
if not ACCESS_TOKEN:
    print("Error: META_ACCESS_TOKEN not found in environment variables.")
    sys.exit(1)

BASE_URL = "https://graph.facebook.com/v23.0"

def get_me():
    """Verify functionality and get user ID."""
    url = f"{BASE_URL}/me?access_token={ACCESS_TOKEN}"
    response = requests.get(url)
    return response.json()

def get_ad_accounts(user_id):
    """Get ad accounts for the user."""
    url = f"{BASE_URL}/{user_id}/adaccounts?access_token={ACCESS_TOKEN}"
    response = requests.get(url)
    return response.json()

def get_campaigns(ad_account_id):
    """Get campaigns for an ad account (v24.0 per prompt)."""
    # Note: Prompt mentions v24.0 for campaigns, sticking to that.
    url = f"https://graph.facebook.com/v24.0/{ad_account_id}/campaigns?fields=id,name,status,objective,start_time,stop_time&access_token={ACCESS_TOKEN}"
    response = requests.get(url)
    return response.json()

def get_ads(campaign_id):
    """Get ads for a campaign (v24.0)."""
    url = f"https://graph.facebook.com/v24.0/{campaign_id}/ads?access_token={ACCESS_TOKEN}"
    response = requests.get(url)
    return response.json()

def get_leads(ad_id):
    """Get leads for an ad (via Ad Set, typically, but prompt says ad_id -> leads).
    WAIT: The prompt says `GET .../{AD_SET_ID}/leads`.
    So I need to get Ad Sets first, OR check if I can get leads from Ad directly.
    The prompt hierarchy is: System User -> Ad Account -> Campaign -> Ad Set -> Leads.
    
    Correction: The prompt says `GET .../{CAMPAIGN_ID}/ads`.
    And then `GET .../{AD_SET_ID}/leads`.
    
    Let's check if we can bridge Campaign -> Ad Set.
    Usually: Campaign -> AdSets -> Ads.
    
    Let's try to get Ad Sets for a campaign.
    """
    # Get Ad Sets for the campaign
    # url = f"https://graph.facebook.com/v24.0/{campaign_id}/adsets?access_token={ACCESS_TOKEN}"
    
    # Prompt explicitly listed:
    # 4. Get Ads for a Specific Campaign: .../{CAMPAIGN_ID}/ads
    # 5. Get Leads from a Specific Ad Set: .../{AD_SET_ID}/leads
    
    # So I need to get Ad Sets. Let's try to get Ad Sets from the campaign first.
    pass

def get_adsets(campaign_id):
    url = f"https://graph.facebook.com/v24.0/{campaign_id}/adsets?access_token={ACCESS_TOKEN}"
    response = requests.get(url)
    return response.json()

def get_leads_from_adset(adset_id):
    url = f"https://graph.facebook.com/v24.0/{adset_id}/leads?fields=created_time,field_data&access_token={ACCESS_TOKEN}"
    response = requests.get(url)
    return response.json()


def run_experiment():
    print("--- 1. Get User ---")
    user_data = get_me()
    print(json.dumps(user_data, indent=2))
    
    if 'error' in user_data:
        print("Stopping due to error.")
        return

    user_id = user_data['id']
    
    print("\n--- 2. Get Ad Accounts ---")
    ad_accounts_data = get_ad_accounts(user_id)
    print(json.dumps(ad_accounts_data, indent=2))
    
    if 'data' not in ad_accounts_data or not ad_accounts_data['data']:
        print("No ad accounts found.")
        return

    # Use the first ad account
    ad_account_id = ad_accounts_data['data'][0]['id']
    print(f"\nUsing Ad Account: {ad_account_id}")
    
    print("\n--- 3. Get Campaigns ---")
    campaigns_data = get_campaigns(ad_account_id)
    print(json.dumps(campaigns_data, indent=2))
    
    if 'data' not in campaigns_data or not campaigns_data['data']:
        print("No campaigns found.")
        return

    # Pick the first active campaign or just the first one
    campaign = campaigns_data['data'][0]
    campaign_id = campaign['id']
    print(f"\nUsing Campaign: {campaign['name']} ({campaign_id})")
    
    print("\n--- 4. Get Ad Sets (to get leads) ---")
    # I'll try to get adsets for this campaign
    adsets_data = get_adsets(campaign_id)
    print(json.dumps(adsets_data, indent=2))
    
    if 'data' not in adsets_data or not adsets_data['data']:
        print("No ad sets found for this campaign.")
        return
        
    adset = adsets_data['data'][0]
    adset_id = adset['id']
    print(f"\nUsing Ad Set: {adset_id}")
    
    print("\n--- 5. Get Leads (Trying Ad Set) ---")
    # leads_data = get_leads_from_adset(adset_id)
    # print(json.dumps(leads_data, indent=2))
    
    # Error received: (#100) Tried accessing nonexisting field (leads) on node type (AdSet)
    # Let's try getting Ads for this AdSet and then leads from Ad.
    
    print("\n--- 5a. Get Ads for Ad Set ---")
    url = f"https://graph.facebook.com/v24.0/{adset_id}/ads?access_token={ACCESS_TOKEN}"
    ads_resp = requests.get(url).json()
    print(json.dumps(ads_resp, indent=2))
    
    if 'data' in ads_resp and ads_resp['data']:
        ad_id = ads_resp['data'][0]['id']
        print(f"\nUsing Ad: {ad_id}")
        
        print("\n--- 5b. Get Leads from Ad ---")
        url = f"https://graph.facebook.com/v24.0/{ad_id}/leads?fields=created_time,field_data&access_token={ACCESS_TOKEN}"
        leads_resp = requests.get(url).json()
        print(json.dumps(leads_resp, indent=2))
    else:
        print("No Ads found in Ad Set.")

if __name__ == "__main__":
    run_experiment()
