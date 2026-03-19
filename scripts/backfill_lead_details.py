#!/usr/bin/env python3
"""
Backfill script: Creates LeadDetail rows for ALL existing leads that don't have one.

This is a one-time operation. It is safe to run multiple times — leads that
already have a LeadDetail row are skipped.

Auto-populates from the Lead record:
  name         ← Lead.name
  email        ← Lead.email
  phone_number ← Lead.phone
  branch_name  ← first non-null of: preferred_practice → practice_to_attend
                 → practice_to_visit → practice_location

Usage:
    cd /home/rpsoftwarelab/Documents/2026_Projects/leads_auto
    source venv/bin/activate
    python scripts/backfill_lead_details.py
"""

import asyncio
import os
import sys
import logging
from datetime import datetime

# Allow importing app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import AsyncSessionLocal
from app.sql_models import Lead, LeadDetail
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE = os.path.join(os.path.dirname(__file__), "backfill_lead_details.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("backfill_details")

BATCH_SIZE = 100  # Commit every N inserts


def _resolve_branch_name(lead: Lead) -> str | None:
    """Return the first non-null/non-empty practice field as the branch name."""
    for value in (
        lead.preferred_practice,
        lead.practice_to_attend,
        lead.practice_to_visit,
        lead.practice_location,
    ):
        if value and value.strip():
            return value.strip()
    return None


async def backfill():
    log.info("=" * 60)
    log.info("STARTING LeadDetail BACKFILL")
    log.info("=" * 60)

    async with AsyncSessionLocal() as session:
        # Fetch all leads that have NO LeadDetail row yet
        stmt = (
            select(Lead)
            .outerjoin(LeadDetail, LeadDetail.lead_id == Lead.lead_id)
            .where(LeadDetail.lead_id == None)   # noqa: E711 – SQLAlchemy syntax
            .order_by(Lead.created_at)
        )
        result = await session.execute(stmt)
        leads = result.scalars().all()

        total = len(leads)
        log.info(f"Found {total} lead(s) without a LeadDetail row.")

        if total == 0:
            log.info("Nothing to do. Exiting.")
            return

        created = 0
        skipped = 0

        for i, lead in enumerate(leads, 1):
            # Double-check: skip if a detail row already exists
            existing = await session.execute(
                select(LeadDetail).where(LeadDetail.lead_id == lead.lead_id)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            branch_name = _resolve_branch_name(lead)

            detail = LeadDetail(
                lead_id=lead.lead_id,
                name=lead.name,
                email=lead.email,
                phone_number=lead.phone,
                branch_name=branch_name,
                updated_at=datetime.utcnow(),
            )
            session.add(detail)
            created += 1

            log.info(
                f"  [{i}/{total}] {lead.name} ({lead.lead_id}) "
                f"→ branch: {branch_name or 'n/a'}"
            )

            # Commit in batches
            if created % BATCH_SIZE == 0:
                await session.commit()
                log.info(f"  ✅ Committed batch ({created} so far)...")

        # Final commit for remaining rows
        await session.commit()

    log.info("")
    log.info("=" * 60)
    log.info("BACKFILL COMPLETE")
    log.info(f"  LeadDetail rows created : {created}")
    log.info(f"  Already existed (skipped): {skipped}")
    log.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(backfill())
    except KeyboardInterrupt:
        log.info("\nBackfill interrupted by user. Progress so far is saved.")
    except Exception as e:
        log.error(f"Backfill failed: {e}", exc_info=True)
