from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, leads, webhook, campaigns, whatsapp
from app.config import settings
from app.database import engine, Base
import asyncio
from app.services.scheduler import fetch_and_process_leads


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Startup: launch the background task
    task = asyncio.create_task(schedule_lead_fetch())
    yield
    # Shutdown: cancel the background task
    task.cancel()


app = FastAPI(title="Leads Auto Backend", version="1.0.0", lifespan=lifespan)

async def schedule_lead_fetch():
    while True:
        try:
            print("Running scheduled lead fetch...")
            # Run with a 5-minute overall timeout as a safety net.
            # If Meta is extremely slow, this prevents the job from hanging forever.
            # Missed leads will be picked up on the next 10-minute cycle.
            await asyncio.wait_for(fetch_and_process_leads(), timeout=300)
        except asyncio.TimeoutError:
            print("WARNING: Lead fetch job timed out after 5 minutes. Will retry next cycle.")
        except Exception as e:
            print(f"Error in scheduled task: {e}")
        
        # Wait for 10 minutes (600 seconds)
        await asyncio.sleep(600)

# CORS Setup
origins = ["*"]  # Adjust for production

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,  # Cannot use True with wildcard origins
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(campaigns.router)
app.include_router(leads.router)
app.include_router(whatsapp.router)
app.include_router(webhook.router)

@app.get("/")
def read_root():
    return {"message": "Leads Auto Backend V1 is running 🚀"}

@app.post("/trigger-sync")
async def trigger_sync():
    """Manually trigger the lead fetch job"""
    await fetch_and_process_leads()
    return {"message": "Sync triggered"}
