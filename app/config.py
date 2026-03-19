import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")
    WATI_API_ENDPOINT = os.getenv("WATI_API_ENDPOINT", "")
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN", "")


settings = Settings()
