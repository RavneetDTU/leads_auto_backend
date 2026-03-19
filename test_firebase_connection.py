import sys
import os

# Ensure app module can be found
sys.path.append(os.getcwd())

from app.firebase_setup import initialize_firebase
from firebase_admin import firestore

def test_connection():
    print("Initializing Firebase...")
    db = initialize_firebase()
    
    if db is None:
        print("Failed to initialize Firebase. DB is None.")
        return

    print("Firebase initialized. Testing Firestore connection...")
    try:
        # Try to list collections (this verifies connection and basic permissions)
        # Note: list_collections() returns a generator
        collections = db.collections()
        print("Successfully connected to Firestore!")
        print("Collections found:")
        count = 0
        for collection in collections:
            print(f" - {collection.id}")
            count += 1
        
        if count == 0:
            print(" - No collections found (but connection is successful)")
            
    except Exception as e:
        print(f"Error connecting to Firestore: {e}")

if __name__ == "__main__":
    test_connection()
