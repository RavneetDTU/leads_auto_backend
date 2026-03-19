"""
One-time DB cleanup script to fix two WhatsApp message issues:

1. DIRECTION FIX: Messages synced from WATI using eventType logic (wrong) are corrected.
   We inspect the wati_raw_data JSON to re-derive direction using the `owner` field.
   - owner=True → OUT (agent-sent)
   - owner=False → IN (customer-sent)

2. DUPLICATE REMOVAL: Remove duplicate messages (same phone + text + timestamp within 5s).
   Keep the row with the most data (prefer non-null wati_message_id, prefer longer text).

Usage:
  cd /home/rpsoftwarelab/Documents/2026_Projects/leads_auto
  source venv/bin/activate
  python scripts/fix_message_direction_and_dupes.py
"""

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete, text
from datetime import timedelta

DATABASE_URL = "postgresql+asyncpg://leads_user:leads_password@localhost/leads_auto_db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def fix_directions(db: AsyncSession):
    """Re-derive direction from wati_raw_data.owner field for all synced messages."""
    print("\n=== STEP 1: Fixing message directions ===")

    # Fetch all messages that have wati_raw_data (i.e. synced from WATI)
    result = await db.execute(
        text("SELECT message_id, direction, wati_raw_data FROM messages WHERE wati_raw_data IS NOT NULL")
    )
    rows = result.fetchall()

    fixed = 0
    for row in rows:
        msg_id, current_direction, raw_data = row
        if not raw_data:
            continue

        owner = raw_data.get("owner", None)
        if owner is None:
            continue  # No owner field, can't re-derive

        correct_direction = "OUT" if owner else "IN"

        if current_direction != correct_direction:
            await db.execute(
                text("UPDATE messages SET direction = :dir WHERE message_id = :id"),
                {"dir": correct_direction, "id": msg_id}
            )
            fixed += 1

    await db.commit()
    print(f"  ✅ Fixed direction on {fixed} messages.")


async def remove_duplicates(db: AsyncSession):
    """Remove duplicate messages (same phone + text + timestamp within 5s). Keep best row."""
    print("\n=== STEP 2: Removing duplicate messages ===")

    # Get all messages ordered by timestamp
    result = await db.execute(
        text("""
            SELECT message_id, phone, message_text, timestamp, wati_message_id, direction
            FROM messages
            ORDER BY phone, timestamp ASC
        """)
    )
    rows = result.fetchall()

    # Group by phone, then find near-duplicates
    seen = []  # list of (phone, text, timestamp, message_id)
    to_delete = []

    for row in rows:
        msg_id, phone, msg_text, timestamp, wati_id, direction = row

        if not msg_text:
            continue  # Skip empty messages from dedup (they can't be matched reliably)

        is_dup = False
        for s_phone, s_text, s_ts, s_id in seen:
            if (
                s_phone == phone
                and s_text == msg_text
                and abs((timestamp - s_ts).total_seconds()) <= 5
            ):
                # It's a duplicate — mark current row for deletion (keep the first/seen one)
                to_delete.append(msg_id)
                is_dup = True
                break

        if not is_dup:
            seen.append((phone, msg_text, timestamp, msg_id))

    if to_delete:
        print(f"  🗑️  Deleting {len(to_delete)} duplicate messages...")
        for msg_id in to_delete:
            await db.execute(
                text("DELETE FROM messages WHERE message_id = :id"),
                {"id": msg_id}
            )
        await db.commit()
        print(f"  ✅ Removed {len(to_delete)} duplicates.")
    else:
        print("  ✅ No duplicates found.")


async def print_summary(db: AsyncSession):
    """Print a quick summary for verification."""
    print("\n=== VERIFICATION SUMMARY ===")

    result = await db.execute(
        text("""
            SELECT direction, count(*) as cnt
            FROM messages
            WHERE phone = '27609724660'
            GROUP BY direction
            ORDER BY direction
        """)
    )
    rows = result.fetchall()
    print("\nPhone 27609724660 — direction breakdown:")
    for row in rows:
        print(f"  {row[0]:5s} → {row[1]} messages")

    result = await db.execute(
        text("""
            SELECT message_text, direction, count(*) as cnt
            FROM messages
            WHERE phone = '27609724660'
            GROUP BY message_text, direction
            HAVING count(*) > 1
        """)
    )
    dupes = result.fetchall()
    if dupes:
        print(f"\n  ⚠️  Still {len(dupes)} duplicate message groups remaining:")
        for d in dupes:
            print(f"    [{d[1]}] '{d[0][:60]}' × {d[2]}")
    else:
        print("\n  ✅ No duplicates remaining for this phone.")

    result = await db.execute(text("SELECT count(*) FROM messages"))
    total = result.scalar()
    print(f"\nTotal messages in DB: {total}")


async def main():
    async with AsyncSessionLocal() as db:
        await fix_directions(db)
        await remove_duplicates(db)
        await print_summary(db)
    print("\n🎉 Cleanup complete.\n")


if __name__ == "__main__":
    asyncio.run(main())
