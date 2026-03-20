import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")
    WATI_API_ENDPOINT = os.getenv("WATI_API_ENDPOINT", "")
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN", "")
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://leads_user:leads_password@localhost/leads_auto_db")


settings = Settings()
