import requests
import json
from app.config import settings
from typing import List, Dict, Any, Optional


class WatiService:
    def __init__(self):
        self.api_endpoint = settings.WATI_API_ENDPOINT
        self.access_token = settings.WATI_ACCESS_TOKEN
        
    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def _is_configured(self) -> bool:
        return bool(self.api_endpoint and self.access_token)

    def get_templates(self) -> List[Dict[str, Any]]:
        if not self._is_configured():
             return []
             
        url = f"{self.api_endpoint}/api/v1/getMessageTemplates"
        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            return data.get("messageTemplates", [])
        except Exception as e:
            print(f"Error fetching WATI templates: {e}")
            return []

    def send_template_message(self, phone: str, template_name: str, parameters: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Sends a template message.
        phone: WhatsApp number (with country code, no +)
        parameters: List of dicts e.g. [{"name": "name", "value": "John"}]
        """
        if not self._is_configured():
            print("WATI credentials missing")
            return {"result": False, "error": "WATI credentials missing"}
            
        # Clean phone number (remove + if present)
        clean_phone = phone.replace("+", "").strip() if phone else ""
        
        url = f"{self.api_endpoint}/api/v1/sendTemplateMessage?whatsappNumber={clean_phone}"
        
        payload = {
            "template_name": template_name,
            "broadcast_name": f"auto_lead_{template_name}",
            "parameters": parameters or []
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            # Check for non-200 or business logic errors
            if response.status_code != 200:
                print(f"WATI API Error {response.status_code}: {response.text}")
                return {"result": False, "error": response.text}
                
            return response.json()
        except Exception as e:
            print(f"Exception sending WATI message: {e}")
            return {"result": False, "error": str(e)}

    def get_messages(self, phone: str, page_size: int = 30, page_number: int = 1) -> Dict[str, Any]:
        """
        Fetches message history from WATI for a contact.
        GET /api/v1/getMessages/{phone}?pageSize=X&pageNumber=Y
        """
        if not self._is_configured():
            return {"result": "error", "error": "WATI credentials missing"}
        
        clean_phone = phone.replace("+", "").strip() if phone else ""
        url = f"{self.api_endpoint}/api/v1/getMessages/{clean_phone}?pageSize={page_size}&pageNumber={page_number}"
        
        try:
            response = requests.get(url, headers=self._get_headers())
            if response.status_code != 200:
                print(f"WATI getMessages Error {response.status_code}: {response.text}")
                return {"result": "error", "error": response.text}
            return response.json()
        except Exception as e:
            print(f"Exception fetching WATI messages: {e}")
            return {"result": "error", "error": str(e)}

    def send_session_message(self, phone: str, message_text: str) -> Dict[str, Any]:
        """
        Sends a free-text session message within the 24-hour window.
        POST /api/v1/sendSessionMessage/{phone}?messageText=...
        """
        if not self._is_configured():
            return {"result": False, "error": "WATI credentials missing"}
        
        clean_phone = phone.replace("+", "").strip() if phone else ""
        url = f"{self.api_endpoint}/api/v1/sendSessionMessage/{clean_phone}?messageText={requests.utils.quote(message_text)}"
        
        try:
            response = requests.post(url, headers=self._get_headers())
            if response.status_code != 200:
                print(f"WATI sendSessionMessage Error {response.status_code}: {response.text}")
                return {"result": False, "error": response.text}
            return response.json()
        except Exception as e:
            print(f"Exception sending session message: {e}")
            return {"result": False, "error": str(e)}


wati_service = WatiService()
