import requests
import json
import os
import sys

# Ensure app module can be found
sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

WATI_API_ENDPOINT = os.getenv("WATI_API_ENDPOINT")
WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN")

if not WATI_API_ENDPOINT or not WATI_ACCESS_TOKEN:
    print("Error: WATI credentials not found in environment variables.")
    sys.exit(1)

# Ensure endpoint doesn't look like "https://.../{TENANT_ID}" literally if user copied that
# But based on my .env update, I put the correct URL.

def get_headers():
    return {
        "Authorization": f"Bearer {WATI_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

def get_templates():
    url = f"{WATI_API_ENDPOINT}/api/v1/getMessageTemplates?pageSize=5"
    print(f"Fetching templates from: {url}")
    try:
        response = requests.get(url, headers=get_headers())
        if response.status_code != 200:
             print(f"Error fetching templates: {response.status_code} - {response.text}")
             return None
        return response.json()
    except Exception as e:
        print(f"Exception fetching templates: {e}")
        return None

def send_template_message(phone, template_name, params=None):
    url = f"{WATI_API_ENDPOINT}/api/v1/sendTemplateMessage?whatsappNumber={phone}"
    print(f"Sending template '{template_name}' to {phone}...")
    
    payload = {
        "template_name": template_name,
        "broadcast_name": "test_experiment_broadcast",
        "parameters": params or []
    }
    
    try:
        response = requests.post(url, headers=get_headers(), json=payload)
        print(f"Response Status: {response.status_code}")
        print(f"Response Body: {response.text}")
        return response.json()
    except Exception as e:
        print(f"Exception sending message: {e}")
        return None

def run_experiment():
    print("--- 1. Get Templates ---")
    templates_data = get_templates()
    
    if not templates_data or "messageTemplates" not in templates_data:
        print("No templates found or error occurred.")
        return

    # Print first few templates to see what we have
    print(json.dumps(templates_data, indent=2))
    
    # Pick a template to send. 
    # Use the first approved one.
    template_to_send = None
    for tmpl in templates_data.get("messageTemplates", []):
        if tmpl.get("status") == "APPROVED":
            template_to_send = tmpl.get("elementName")
            print(f"\nSelected Template: {template_to_send}")
            break
    
    if not template_to_send:
        print("No approved templates found to test sending.")
        return

    # Test Numbers requested by user
    # +918930276263 and +918930971204
    # WATI usually expects number with country code, no plus. 
    # But let's try with what user gave, or strip plus if needed.
    # WATI docs often say: "whatsappNumber": "918120510615" (so no plus).
    
    test_numbers = ["918930276263", "918930971204"]
    
    print("\n--- 2. Send Template Message ---")
    pass
    # We will send to both numbers
    for number in test_numbers:
         # Construct parameters if the template needs them.
         # For st_new_lead_auto_reply, it likely needs {{name}} based on common patterns.
         # Let's try adding a name parameter.
         params = [{"name": "name", "value": "Test User"}]
         
         send_template_message(number, template_to_send, params)

if __name__ == "__main__":
    run_experiment()
