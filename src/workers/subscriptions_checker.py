"""
Subscriptions checker — monitors Google Sheet for expiring VPS and domains.

Reads a public Google Sheet (two tabs: "VPS" and "Домены") via CSV export and
returns items whose "Оплачено до" date is within the next 7 days (or already
expired), so the user can renew them in time.

"""

import csv
import io
import logging
from datetime import date, datetime
from typing import List, Optional, Dict

import httpx

from src.utils.doppler import get_secret

logger = logging.getLogger(__name__)

CSV_URL = (
    "https://docs.google.com/spreadsheets/d/{sheet_id}"
    "/gviz/tq?tqx=out:csv&sheet={sheet_name}"
)

# How many days ahead to warn before expiration
WARN_DAYS = 7

# Date formats seen in the "Оплачено до" column
DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y")


def _parse_date(raw: str) -> Optional[date]:
    """Parse a date string from the sheet, trying several known formats."""
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    logger.warning(f"Could not parse 'Оплачено до' date: {raw!r}")
    return None


def _get_sheet_id() -> Optional[str]:
    """Read the Google Sheet ID from Doppler (SUBSCRIPTIONS_SHEET_ID)."""
    sheet_id = get_secret("SUBSCRIPTIONS_SHEET_ID")
    if not sheet_id:
        logger.error("SUBSCRIPTIONS_SHEET_ID is not set in Doppler")
        return None
    return sheet_id


async def _fetch_csv(sheet_id: str, sheet_name: str) -> Optional[List[Dict[str, str]]]:
    """Fetch one tab of the sheet as a list of dict rows (keyed by header)."""
    url = CSV_URL.format(sheet_id=sheet_id, sheet_name=sheet_name)
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch sheet '{sheet_name}': {type(e).__name__}: {e}")
        return None

    try:
        reader = csv.DictReader(io.StringIO(response.text))
        return list(reader)
    except Exception as e:
        logger.error(f"Failed to parse CSV for '{sheet_name}': {type(e).__name__}: {e}")
        return None


def _check_rows(
    rows: List[Dict[str, str]],
    name_col: str,
    kind: str,
    today: date,
) -> List[str]:
    """Find rows expiring within WARN_DAYS and format warning lines."""
    warnings: List[str] = []
    for row in rows:
        due = _parse_date(row.get("Оплачено до", ""))
        if due is None:
            continue
        days_left = (due - today).days
        if days_left > WARN_DAYS:
            continue

        name = (row.get(name_col) or "").strip() or "(без названия)"
        provider = (row.get("Провайдер") or "").strip()
        provider_str = f" ({provider})" if provider else ""
        due_str = due.strftime("%d.%m.%Y")

        if days_left < 0:
            status = f"⚠️ ПРОСРОЧЕНО ({abs(days_left)} дн. назад)"
        elif days_left == 0:
            status = "⚠️ истекает сегодня"
        else:
            status = f"истекает через {days_left} дн."

        warnings.append(f"  • {kind}: {name}{provider_str} — {status} (до {due_str})")
    return warnings


async def check_expiring_subscriptions() -> Optional[List[str]]:
    """
    Check VPS and Domains sheets for items expiring within WARN_DAYS.

    Returns a list of formatted warning lines, or None if nothing is expiring
    or the sheet could not be fetched.
    """
    today = date.today()

    sheet_id = _get_sheet_id()
    if not sheet_id:
        return None

    vps_rows = await _fetch_csv(sheet_id, "VPS")
    # Tab name "Домены" must be URL-encoded for the request
    domain_rows = await _fetch_csv(sheet_id, "%D0%94%D0%BE%D0%BC%D0%B5%D0%BD%D1%8B")

    warnings: List[str] = []

    if vps_rows:
        warnings.extend(_check_rows(vps_rows, "Название", "VPS", today))
    if domain_rows:
        warnings.extend(_check_rows(domain_rows, "Домен", "Домен", today))

    if not warnings:
        return None
    return warnings
