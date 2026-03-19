import requests
import os
from app.config import settings
from typing import List, Dict, Any, Optional
from datetime import datetime




class MetaService:
    def __init__(self):
        self.access_token = os.getenv("META_ACCESS_TOKEN")
        self.base_url = "https://graph.facebook.com/v24.0"
        
    def _get_headers(self):
        return {} # Params usually passed in query string

    def get_ad_accounts(self) -> List[Dict[str, Any]]:
        if not self.access_token:
             print("Meta Access Token missing")
             return []
             
        url = f"{self.base_url}/me/adaccounts"
        params = {
            "access_token": self.access_token
        }
        try:
            response = requests.get(url, params=params, timeout=120)
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as e:
            print(f"Error fetching ad accounts: {e}")
            return []

    def get_campaigns(self, ad_account_id: str) -> List[Dict[str, Any]]:
        # Ensure ad_account_id starts with 'act_' if not present, though usually API returns it with act_
        if not ad_account_id.startswith("act_"):
            # It's safer to assume the caller passes the full ID, but let's be careful.
            # In get_ad_accounts response: "id": "act_227..."
            pass
            
        url = f"{self.base_url}/{ad_account_id}/campaigns"
        params = {
            "fields": "id,name,status,objective,start_time,stop_time",
            "access_token": self.access_token,
            "limit": 100
        }
        try:
            response = requests.get(url, params=params, timeout=120)
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as e:
            print(f"Error fetching campaigns for {ad_account_id}: {e}")
            return []

    def get_ads(self, campaign_id: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/{campaign_id}/ads"
        params = {
            "fields": "id,name,adset_id", # Fetch adset_id too if needed
            "access_token": self.access_token,
             "limit": 100
        }
        try:
            response = requests.get(url, params=params, timeout=120)
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as e:
            print(f"Error fetching ads for {campaign_id}: {e}")
            return []
            
    def get_adsets(self, campaign_id: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/{campaign_id}/adsets"
        params = {
            "fields": "id,name",
            "access_token": self.access_token,
             "limit": 100
        }
        try:
            response = requests.get(url, params=params, timeout=120)
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as e:
            print(f"Error fetching adsets for {campaign_id}: {e}")
            return []

    def get_leads_from_ad(self, ad_id: str, since_timestamp: Optional[int] = None, limit_total: int = 500) -> List[Dict[str, Any]]:
        """
        Fetches leads for an ad. Supports pagination up to limit_total.
        """
        url = f"{self.base_url}/{ad_id}/leads"
        params = {
            "fields": "created_time,field_data,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name",
            "access_token": self.access_token,
            "limit": 100 
        }
        
        if since_timestamp:
            params["since"] = since_timestamp
            
        all_leads = []
        
        try:
            while url and len(all_leads) < limit_total:
                response = requests.get(url, params=params, timeout=120)
                response.raise_for_status()
                data = response.json()
                
                leads_page = data.get("data", [])
                all_leads.extend(leads_page)
                
                # Check pagination
                paging = data.get("paging", {})
                url = paging.get("next")
                if url:
                    # Next URL already contains params, so clear them for subsequent requests
                    params = {} 
                else:
                    break
                    
            return all_leads
            
        except Exception as e:
            print(f"Error fetching leads for ad {ad_id}: {e}")
            return []

    # Mapping of Meta field_data key names -> normalized DB column names
    BRANCH_FIELD_MAP = {
        "please_select_your_province": "province",
        "please_select_your_preferred_practice": "preferred_practice",
        "select_the_practice_that_you_would_like_to_visit": "practice_to_visit",
        "which_practice_location_do_you_prefer?": "practice_location",
        "which_practice_would_you_prefer_to_attend?": "practice_to_attend",
    }

    def _clean_value(self, value: str) -> str:
        """Return None for empty, 'n/a', 'na', 'none' values, else stripped value."""
        if not value:
            return None
        stripped = value.strip()
        if stripped.lower() in ("", "n/a", "na", "none", "null", "-"):
            return None
        return stripped

    def parse_lead_field_data(self, field_data: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Parses the field_data list into a dictionary.
        Example field_data:
        [
            {"name": "full_name", "values": ["Masebidi ..."]},
            {"name": "contact_number?", "values": ["081..."]},
            {"name": "email", "values": ["..."]},
            {"name": "please_select_your_province", "values": ["somerset_west_"]}
        ]
        """
        result = {}
        for field in field_data:
            name = field.get("name", "")
            values = field.get("values", [])
            if values:
                value = values[0]
                # Normalize core keys
                if "name" in name.lower():
                    result["name"] = self._clean_value(value) or value
                elif "number" in name.lower() or "phone" in name.lower() or "whatsapp" in name.lower():
                    raw_phone = self._clean_value(value) or value
                    if raw_phone:
                        result["phone"] = raw_phone.replace("+", "").replace(" ", "").replace("-", "").strip()
                    else:
                        result["phone"] = raw_phone
                elif "email" in name.lower():
                    result["email"] = self._clean_value(value)
                # Check branch/practice keys
                elif name in self.BRANCH_FIELD_MAP:
                    col_name = self.BRANCH_FIELD_MAP[name]
                    result[col_name] = self._clean_value(value)
                else:
                    result[name] = self._clean_value(value)
        
        # Ensure all branch keys exist (default None)
        for col_name in self.BRANCH_FIELD_MAP.values():
            result.setdefault(col_name, None)
        
        return result

meta_service = MetaService()
