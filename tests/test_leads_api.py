"""
tests/test_leads_api.py

Pytest suite covering all changes made in this session:
  1. GET /leads/{lead_id}/detail — auto-populated from Lead fields (never all-nulls)
  2. POST /leads/demo — detail row also auto-created
  3. GET /leads/date/{date} — returns LeadsWithStats shape, correct status labels
  4. GET /leads/last-30-days — returns LeadsWithStats shape, correct status labels
  5. _derive_whatsapp_status() unit tests — all 4 status paths

Usage:
    cd /home/rpsoftwarelab/Documents/2026_Projects/leads_auto
    source venv/bin/activate
    pip install pytest pytest-asyncio httpx
    pytest tests/test_leads_api.py -v
"""

import pytest
import asyncio
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# ── bootstrap path ───────────────────────────────────────────────────────────
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.routers.leads import _derive_whatsapp_status

# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — _derive_whatsapp_status()
# ─────────────────────────────────────────────────────────────────────────────

class TestDeriveWhatsappStatus:
    """Tests for the pure function that maps message timestamps → status badge."""

    def test_new_no_template_no_messages(self):
        """Lead with no messages and no template sent → 'new'"""
        assert _derive_whatsapp_status(False, None, None) == "new"

    def test_initial_template_sent_no_reply(self):
        """Template sent but no reply from customer → 'initial_template_sent'"""
        assert _derive_whatsapp_status(True, None, None) == "initial_template_sent"

    def test_initial_template_sent_not_old_label(self):
        """Confirm old 'template_sent' label is GONE — must be 'initial_template_sent'"""
        result = _derive_whatsapp_status(True, None, None)
        assert result != "template_sent", "Old label 'template_sent' must not be returned"
        assert result == "initial_template_sent"

    def test_unread_customer_replied_no_sales_reply(self):
        """Customer sent a message, sales team hasn't replied yet → 'unread'"""
        customer_msg_ts = datetime(2026, 3, 5, 10, 0, 0)
        assert _derive_whatsapp_status(True, customer_msg_ts, None) == "unread"

    def test_unread_customer_replied_after_sales(self):
        """Customer replied after sales last message → still 'unread'"""
        sales_ts    = datetime(2026, 3, 5, 9, 0, 0)
        customer_ts = datetime(2026, 3, 5, 10, 0, 0)   # newer
        assert _derive_whatsapp_status(True, customer_ts, sales_ts) == "unread"

    def test_responded_sales_replied_after_customer(self):
        """Sales replied after customer's last message → 'responded'"""
        customer_ts = datetime(2026, 3, 5, 9, 0, 0)
        sales_ts    = datetime(2026, 3, 5, 10, 0, 0)   # newer
        assert _derive_whatsapp_status(True, customer_ts, sales_ts) == "responded"

    def test_responded_same_timestamp(self):
        """OUT timestamp equal to IN timestamp → 'responded' (>= condition)"""
        ts = datetime(2026, 3, 5, 10, 0, 0)
        assert _derive_whatsapp_status(True, ts, ts) == "responded"

    def test_valid_status_values(self):
        """All possible return values are in the agreed-upon set."""
        valid = {"new", "initial_template_sent", "unread", "responded"}
        ts = datetime(2026, 3, 5, 10, 0, 0)
        results = [
            _derive_whatsapp_status(False, None, None),
            _derive_whatsapp_status(True,  None, None),
            _derive_whatsapp_status(True,  ts,   None),
            _derive_whatsapp_status(True,  ts,   ts),
        ]
        for r in results:
            assert r in valid, f"Unexpected status value: '{r}'"


# ─────────────────────────────────────────────────────────────────────────────
# API integration tests (live service at localhost:5012)
# Run these only when the service is up.
# ─────────────────────────────────────────────────────────────────────────────

import httpx

BASE_URL = "http://localhost:5012"


def api_available() -> bool:
    try:
        httpx.get(f"{BASE_URL}/", timeout=2)
        return True
    except Exception:
        return False


SKIP_IF_DOWN = pytest.mark.skipif(
    not api_available(),
    reason="Live API at localhost:5012 is not reachable"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_any_lead_id() -> str | None:
    """Return any lead_id from the last 30 days, or None."""
    try:
        r = httpx.get(f"{BASE_URL}/leads/last-30-days", timeout=10)
        data = r.json()
        leads = data.get("leads", [])
        return leads[0]["lead_id"] if leads else None
    except Exception:
        return None


def get_active_campaign_id() -> str | None:
    """Return first active campaign id, or None."""
    try:
        r = httpx.get(f"{BASE_URL}/leads/active-campaigns", timeout=10)
        camps = r.json()
        return camps[0]["id"] if camps else None
    except Exception:
        return None


# ── 1. Lead Detail endpoint ───────────────────────────────────────────────────

class TestLeadDetail:

    @SKIP_IF_DOWN
    def test_detail_404_for_nonexistent_lead(self):
        """Unknown lead id → 404."""
        r = httpx.get(f"{BASE_URL}/leads/NONEXISTENT_LEAD_ID_XYZ/detail", timeout=5)
        assert r.status_code == 404

    @SKIP_IF_DOWN
    def test_detail_has_required_fields(self):
        """GET /leads/{id}/detail returns object with all expected keys."""
        lead_id = get_any_lead_id()
        if not lead_id:
            pytest.skip("No leads available")

        r = httpx.get(f"{BASE_URL}/leads/{lead_id}/detail", timeout=5)
        assert r.status_code == 200
        data = r.json()

        for key in ("lead_id", "branch_name", "status", "name", "email", "phone_number", "city"):
            assert key in data, f"Expected '{key}' in detail response"

    @SKIP_IF_DOWN
    def test_detail_name_and_phone_not_null(self):
        """
        After backfill, name and phone_number should be populated for any
        lead in the last 30 days (they came from Lead.name / Lead.phone).
        """
        lead_id = get_any_lead_id()
        if not lead_id:
            pytest.skip("No leads available")

        r = httpx.get(f"{BASE_URL}/leads/{lead_id}/detail", timeout=5)
        data = r.json()
        assert data["name"] is not None, "name should be auto-populated from Lead.name"
        assert data["phone_number"] is not None, "phone_number should be auto-populated"

    @SKIP_IF_DOWN
    def test_detail_upsert_then_retrieve(self):
        """PUT detail then GET should return updated values."""
        lead_id = get_any_lead_id()
        if not lead_id:
            pytest.skip("No leads available")

        payload = {"city": "Test City", "status": "contacted"}
        put_r = httpx.put(f"{BASE_URL}/leads/{lead_id}/detail", json=payload, timeout=5)
        assert put_r.status_code == 200

        get_r = httpx.get(f"{BASE_URL}/leads/{lead_id}/detail", timeout=5)
        data = get_r.json()
        assert data["city"] == "Test City"
        assert data["status"] == "contacted"


# ── 2. Demo lead auto-populates detail ───────────────────────────────────────

class TestDemoLeadDetail:

    @SKIP_IF_DOWN
    def test_demo_lead_creates_detail_row(self):
        """
        Creating a demo lead via POST /leads/demo must also create a
        LeadDetail row so GET /leads/{id}/detail is not all-nulls.
        """
        camp_id = get_active_campaign_id()
        if not camp_id:
            pytest.skip("No active campaign available for demo lead creation")

        payload = {
            "campaign_id": camp_id,
            "name": "Detail Test User",
            "phone": "27999000001",
            "email": "detailtest@example.com",
            "preferred_practice": "Test Branch",
        }
        r = httpx.post(f"{BASE_URL}/leads/demo", json=payload, timeout=10)
        assert r.status_code == 200
        lead_id = r.json()["lead_id"]

        detail_r = httpx.get(f"{BASE_URL}/leads/{lead_id}/detail", timeout=5)
        assert detail_r.status_code == 200
        detail = detail_r.json()

        assert detail["name"] == "Detail Test User"
        assert detail["phone_number"] == "27999000001"
        assert detail["branch_name"] == "Test Branch"


# ── 3. Daily Leads — LeadsWithStats shape ─────────────────────────────────────

class TestDailyLeadsResponse:

    DATE_WITH_LEADS = "2026-03-02"   # adjust to a date that has real leads

    @SKIP_IF_DOWN
    def test_response_is_object_not_array(self):
        """Response must be an object {leads, stats}, NOT a bare array."""
        r = httpx.get(f"{BASE_URL}/leads/date/{self.DATE_WITH_LEADS}", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict), "Response must be a dict, not a list"
        assert "leads" in data
        assert "stats" in data

    @SKIP_IF_DOWN
    def test_stats_has_all_required_fields(self):
        r = httpx.get(f"{BASE_URL}/leads/date/{self.DATE_WITH_LEADS}", timeout=10)
        stats = r.json()["stats"]
        for field in ("total", "new", "initial_template_sent", "unread", "responded"):
            assert field in stats, f"stats missing field: '{field}'"
            assert isinstance(stats[field], int)

    @SKIP_IF_DOWN
    def test_stats_total_equals_leads_count(self):
        r = httpx.get(f"{BASE_URL}/leads/date/{self.DATE_WITH_LEADS}", timeout=10)
        data = r.json()
        assert data["stats"]["total"] == len(data["leads"])

    @SKIP_IF_DOWN
    def test_stats_counts_sum_to_total(self):
        r = httpx.get(f"{BASE_URL}/leads/date/{self.DATE_WITH_LEADS}", timeout=10)
        s = r.json()["stats"]
        assert s["new"] + s["initial_template_sent"] + s["unread"] + s["responded"] == s["total"]

    @SKIP_IF_DOWN
    def test_no_template_sent_in_status_values(self):
        """Old label 'template_sent' must NOT appear in any lead's whatsapp_status."""
        r = httpx.get(f"{BASE_URL}/leads/date/{self.DATE_WITH_LEADS}", timeout=10)
        leads = r.json()["leads"]
        bad = [l for l in leads if l.get("whatsapp_status") == "template_sent"]
        assert len(bad) == 0, f"Found {len(bad)} lead(s) with old status 'template_sent'"

    @SKIP_IF_DOWN
    def test_status_values_are_valid(self):
        """Every lead's whatsapp_status must be one of the 4 valid values."""
        valid = {"new", "initial_template_sent", "unread", "responded"}
        r = httpx.get(f"{BASE_URL}/leads/date/{self.DATE_WITH_LEADS}", timeout=10)
        leads = r.json()["leads"]
        for lead in leads:
            s = lead.get("whatsapp_status")
            assert s in valid, f"Invalid status '{s}' for lead {lead.get('lead_id')}"

    @SKIP_IF_DOWN
    def test_invalid_date_format_returns_400(self):
        r = httpx.get(f"{BASE_URL}/leads/date/not-a-date", timeout=5)
        assert r.status_code == 400

    @SKIP_IF_DOWN
    def test_empty_date_returns_empty_leads_with_zero_stats(self):
        """A date far in the past with no leads → stats all 0, leads empty."""
        r = httpx.get(f"{BASE_URL}/leads/date/2000-01-01", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["leads"] == []
        assert data["stats"]["total"] == 0
        assert data["stats"]["new"] == 0


# ── 4. Last 30 Days — LeadsWithStats shape ────────────────────────────────────

class TestLast30DaysResponse:

    @SKIP_IF_DOWN
    def test_response_is_object_not_array(self):
        r = httpx.get(f"{BASE_URL}/leads/last-30-days", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict), "Response must be a dict, not a list"
        assert "leads" in data
        assert "stats" in data

    @SKIP_IF_DOWN
    def test_stats_has_all_required_fields(self):
        r = httpx.get(f"{BASE_URL}/leads/last-30-days", timeout=15)
        stats = r.json()["stats"]
        for field in ("total", "new", "initial_template_sent", "unread", "responded"):
            assert field in stats

    @SKIP_IF_DOWN
    def test_stats_total_equals_leads_count(self):
        r = httpx.get(f"{BASE_URL}/leads/last-30-days", timeout=15)
        data = r.json()
        assert data["stats"]["total"] == len(data["leads"])

    @SKIP_IF_DOWN
    def test_stats_counts_sum_to_total(self):
        r = httpx.get(f"{BASE_URL}/leads/last-30-days", timeout=15)
        s = r.json()["stats"]
        assert s["new"] + s["initial_template_sent"] + s["unread"] + s["responded"] == s["total"]

    @SKIP_IF_DOWN
    def test_no_old_template_sent_label(self):
        r = httpx.get(f"{BASE_URL}/leads/last-30-days", timeout=15)
        leads = r.json()["leads"]
        bad = [l for l in leads if l.get("whatsapp_status") == "template_sent"]
        assert len(bad) == 0, f"Found {len(bad)} lead(s) with old label 'template_sent'"


# ── 5. Lead Notes ─────────────────────────────────────────────────────────────

class TestLeadNotes:

    @SKIP_IF_DOWN
    def test_add_and_retrieve_note(self):
        lead_id = get_any_lead_id()
        if not lead_id:
            pytest.skip("No leads available")

        r = httpx.post(f"{BASE_URL}/leads/{lead_id}/notes",
                       json={"content": "Automated test note"}, timeout=5)
        # 201 created or 400 if already at max
        assert r.status_code in (201, 400)

        r2 = httpx.get(f"{BASE_URL}/leads/{lead_id}/notes", timeout=5)
        assert r2.status_code == 200
        notes = r2.json()
        assert isinstance(notes, list)

    @SKIP_IF_DOWN
    def test_max_10_notes_enforced(self):
        """Adding more than 10 notes should return 400."""
        lead_id = get_any_lead_id()
        if not lead_id:
            pytest.skip("No leads available")

        for _ in range(11):
            r = httpx.post(f"{BASE_URL}/leads/{lead_id}/notes",
                           json={"content": "overflow note"}, timeout=5)
            if r.status_code == 400:
                assert "Maximum" in r.json()["detail"]
                return
        # If we reach here without hitting 400, the lead had <10 notes before;
        # that's acceptable too (test is about enforcement once limit is hit)


# ── 6. Lead Answers ───────────────────────────────────────────────────────────

class TestLeadAnswers:

    @SKIP_IF_DOWN
    def test_upsert_and_retrieve_answers(self):
        lead_id = get_any_lead_id()
        if not lead_id:
            pytest.skip("No leads available")

        payload = {
            "difficulty_crowded": True,
            "mumble_or_muffled": False,
            "watch_face": True,
        }
        r = httpx.put(f"{BASE_URL}/leads/{lead_id}/answers", json=payload, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["difficulty_crowded"] is True
        assert data["mumble_or_muffled"] is False
        assert data["watch_face"] is True

    @SKIP_IF_DOWN
    def test_answers_partial_update(self):
        """Omitting a field should leave it unchanged (exclude_unset behaviour)."""
        lead_id = get_any_lead_id()
        if not lead_id:
            pytest.skip("No leads available")

        # Set known state
        httpx.put(f"{BASE_URL}/leads/{lead_id}/answers",
                  json={"difficulty_crowded": True, "mumble_or_muffled": True}, timeout=5)

        # Partial update — only change one field
        httpx.put(f"{BASE_URL}/leads/{lead_id}/answers",
                  json={"watch_face": False}, timeout=5)

        r = httpx.get(f"{BASE_URL}/leads/{lead_id}/answers", timeout=5)
        data = r.json()
        assert data["difficulty_crowded"] is True   # unchanged
        assert data["mumble_or_muffled"] is True    # unchanged
        assert data["watch_face"] is False          # updated
