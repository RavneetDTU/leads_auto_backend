import httpx
import time
import sys

BASE_URL = "http://localhost:8000"

def test_root():
    print("Testing Root...")
    try:
        r = httpx.get(f"{BASE_URL}/")
        assert r.status_code == 200
        print("✅ Root OK")
    except Exception as e:
        print(f"❌ Root Failed: {e}")

def test_auth():
    print("Testing Auth...")
    payload = {"email": "agent@company.com", "password": "123456"}
    try:
        r = httpx.post(f"{BASE_URL}/auth/login", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        print("✅ Auth OK")
    except Exception as e:
        print(f"❌ Auth Failed: {e}")

def test_leads_flow():
    print("Testing Leads Flow...")
    try:
        # Create Lead
        lead_payload = {
            "name": "Test Lead",
            "phone": "1234567890",
            "email": "test@example.com",
            "status": "new"
        }
        r = httpx.post(f"{BASE_URL}/leads/", json=lead_payload)
        if r.status_code == 503: # DB Disconnected
             print("⚠️ DB Disconnected - Skipping Create Lead verification fully")
             return None
             
        assert r.status_code == 200
        lead_data = r.json()
        lead_id = lead_data["lead_id"]
        print(f"✅ Create Lead OK: {lead_id}")
        
        # Get Lead
        r = httpx.get(f"{BASE_URL}/leads/{lead_id}")
        assert r.status_code == 200
        assert r.json()["name"] == "Test Lead"
        print("✅ Get Lead OK")
        
        # Get Leads List
        r = httpx.get(f"{BASE_URL}/leads/?status=new")
        assert r.status_code == 200
        assert len(r.json()) >= 1
        print("✅ List Leads OK")
        
        return lead_id
    except Exception as e:
        print(f"❌ Leads Flow Failed: {e}")
        return None

def test_activities(lead_id):
    if not lead_id: return
    print("Testing Activities...")
    try:
        payload = {"type": "note", "data": {"text": "Test Note"}}
        r = httpx.post(f"{BASE_URL}/leads/{lead_id}/activity/", json=payload)
        assert r.status_code == 200
        print("✅ Add Activity OK")
        
        r = httpx.get(f"{BASE_URL}/leads/{lead_id}/activity/")
        assert r.status_code == 200
        assert len(r.json()) >= 1
        print("✅ Get Activities OK")
    except Exception as e:
        print(f"❌ Activities Failed: {e}")

def test_whatsapp(lead_id):
    if not lead_id: return
    print("Testing WhatsApp...")
    try:
        # Templates
        r = httpx.get(f"{BASE_URL}/whatsapp/templates")
        assert r.status_code == 200
        print("✅ Get Templates OK")
        
        # Send Message
        payload = {"lead_id": lead_id, "message": "Hello test"}
        r = httpx.post(f"{BASE_URL}/whatsapp/send-message", json=payload)
        assert r.status_code == 200
        print("✅ Send Message OK")
        
        # Get History
        r = httpx.get(f"{BASE_URL}/whatsapp/messages/{lead_id}")
        assert r.status_code == 200
        print("✅ Get History OK")
        
    except Exception as e:
        print(f"❌ WhatsApp Failed: {e}")

def main():
    test_root()
    test_auth()
    lead_id = test_leads_flow()
    if lead_id:
        test_activities(lead_id)
        test_whatsapp(lead_id)

if __name__ == "__main__":
    main()
