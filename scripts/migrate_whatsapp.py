"""
Migration script to add new WhatsApp columns to existing tables.
Run this ONCE to update the schema without losing data.

Usage:
    cd /home/rpsoftwarelab/Documents/2026_Projects/leads_auto
    python scripts/migrate_whatsapp.py
"""
import asyncio
from sqlalchemy import text
from app.database import engine


async def run_migration():
    print("═" * 50)
    print("  🔧 WhatsApp Schema Migration")
    print("═" * 50)
    
    async with engine.begin() as conn:
        # 1. Add template_message_sent to leads
        try:
            await conn.execute(text(
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS template_message_sent BOOLEAN DEFAULT FALSE"
            ))
            print("  ✅ leads.template_message_sent added")
        except Exception as e:
            print(f"  ⚠️  leads.template_message_sent: {e}")
        
        # 2. Add wati_message_id to messages
        try:
            await conn.execute(text(
                "ALTER TABLE messages ADD COLUMN IF NOT EXISTS wati_message_id VARCHAR"
            ))
            print("  ✅ messages.wati_message_id added")
        except Exception as e:
            print(f"  ⚠️  messages.wati_message_id: {e}")
        
        # 3. Add template_name to messages
        try:
            await conn.execute(text(
                "ALTER TABLE messages ADD COLUMN IF NOT EXISTS template_name VARCHAR"
            ))
            print("  ✅ messages.template_name added")
        except Exception as e:
            print(f"  ⚠️  messages.template_name: {e}")
        
        # 4. Create index on wati_message_id for fast lookups
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_messages_wati_message_id ON messages (wati_message_id)"
            ))
            print("  ✅ Index idx_messages_wati_message_id created")
        except Exception as e:
            print(f"  ⚠️  Index: {e}")
    
    print("═" * 50)
    print("  ✅ Migration complete!")
    print("═" * 50)


if __name__ == "__main__":
    asyncio.run(run_migration())
