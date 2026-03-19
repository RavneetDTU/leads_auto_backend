# Leads Auto Backend

FastAPI-based lead management backend with WhatsApp integration via WATI.

## 🚀 Quick Start (Development)

```bash
cd /home/rpsoftwarelab/Documents/2026_Projects/leads_auto
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 5012 --reload
```

## 📋 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/auth/login` | POST | User authentication |
| `/leads/` | GET | List leads (filter by campaign_id, status) |
| `/leads/` | POST | Create a new lead |
| `/leads/{lead_id}` | GET | Get lead details |
| `/leads/{lead_id}/activity/` | GET | Get lead activities |
| `/leads/{lead_id}/activity/` | POST | Add activity to lead |
| `/whatsapp/templates` | GET | Get WhatsApp templates |
| `/whatsapp/send-template` | POST | Send template message |
| `/whatsapp/send-message` | POST | Send session message |
| `/whatsapp/messages/{lead_id}` | GET | Get message history |
| `/campaigns` | GET | List campaigns (use `?sync=true` to force sync) |
| `/campaigns/{id}/template` | POST | Set WATI template for a campaign |

**API Documentation:**
- Swagger UI: `https://leadsautoapis.jarviscalling.ai/docs`
- ReDoc: `https://leadsautoapis.jarviscalling.ai/redoc`

---

## 🔧 Production Deployment

### 1. Install Systemctl Service

```bash
# Copy service file
sudo cp /home/rpsoftwarelab/Documents/2026_Projects/leads_auto/leads_auto.service /etc/systemd/system/

# Reload systemd daemon
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable leads_auto

# Start the service
sudo systemctl start leads_auto

# Check status
sudo systemctl status leads_auto
```

**Service file location:** `/etc/systemd/system/leads_auto.service`  
**Source file:** `/home/rpsoftwarelab/Documents/2026_Projects/leads_auto/leads_auto.service`

### 2. Setup Nginx Reverse Proxy

```bash
# Copy nginx config
sudo cp /home/rpsoftwarelab/Documents/2026_Projects/leads_auto/leadsautoapis.jarviscalling.ai.conf /etc/nginx/sites-available/

# Enable the site
sudo ln -s /etc/nginx/sites-available/leadsautoapis.jarviscalling.ai.conf /etc/nginx/sites-enabled/

# Test nginx config
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

**Nginx config location:** `/etc/nginx/sites-available/leadsautoapis.jarviscalling.ai.conf`  
**Source file:** `/home/rpsoftwarelab/Documents/2026_Projects/leads_auto/leadsautoapis.jarviscalling.ai.conf`

### 3. Setup SSL Certificate

```bash
# Obtain SSL certificate
sudo certbot --nginx -d leadsautoapis.jarviscalling.ai

# Follow the prompts to complete setup
# Certbot will auto-renew the certificate
```

### 4. DNS Configuration

Add an A record in your DNS provider:
```
Type: A
Name: leadsauto
Value: <YOUR_SERVER_IP>
TTL: 3600
```

---

## 📁 Project Structure

```
leads_auto/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Settings and environment vars
│   ├── firebase_setup.py    # Firebase initialization
│   ├── models.py            # Pydantic models
│   └── routers/
│       ├── auth.py          # Authentication endpoints
│       ├── leads.py         # Lead management endpoints
│       ├── activities.py    # Lead activity endpoints
│       ├── whatsapp.py      # WhatsApp/WATI endpoints
│       ├── webhook.py       # WATI webhook handler
│       └── campaigns.py     # Campaign endpoints
│   ├── services/            # External services
│   │   ├── meta.py          # Meta Ads integration
│   │   ├── wati.py          # WATI integration
│   │   └── scheduler.py     # Background tasks
├── venv/                    # Python virtual environment
├── leads_auto.service       # Systemctl service file
├── leadsautoapis.jarviscalling.ai.conf  # Nginx config
├── test_endpoints.py        # API tests
├── .env.example             # Environment template
└── README.md                # This file
```

---

## ⚙️ Configuration

### Environment Variables (.env)

```bash
FIREBASE_CREDENTIALS_PATH=serviceAccountKey.json
WATI_API_ENDPOINT=https://live-server-XXXX.wati.io
WATI_ACCESS_TOKEN=your_wati_access_token
```

> **Note:** Currently running in demo mode with mock data. Add `serviceAccountKey.json` for Firebase integration.

---

## 🔍 Service Management Commands

```bash
# Check service status
sudo systemctl status leads_auto

# Start service
sudo systemctl start leads_auto

# Stop service
sudo systemctl stop leads_auto

# Restart service
sudo systemctl restart leads_auto

# View logs
sudo journalctl -u leads_auto -f

# View last 100 log lines
sudo journalctl -u leads_auto -n 100
```

---

## 🧪 Testing

```bash
cd /home/rpsoftwarelab/Documents/2026_Projects/leads_auto
source venv/bin/activate
python test_endpoints.py
```

---

## 📞 Support

**Server:** Ubuntu with Nginx 1.24.0  
**Port:** 5012 (internal), 443 (HTTPS via Nginx)  
**Domain:** leadsautoapis.jarviscalling.ai  
**API Version:** 1.0.0
