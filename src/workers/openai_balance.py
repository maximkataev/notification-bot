"""Fetch OpenAI account balance."""
import logging
from typing import Optional
import httpx
from src.utils.openai_client import get_client
from src.utils.doppler import get_secret

logger = logging.getLogger(__name__)


async def get_openai_balance() -> Optional[float]:
    """Get OpenAI account balance in USD.

    Returns balance amount or None if API call fails.
    Uses OpenAI billing API endpoint.
    """
    try:
        # Try using OpenAI SDK billing API (v1.1.0+)
        client = get_client()

        # Method 1: Try billing.credit_grants API (newer versions)
        try:
            credit_grants = await client.billing.credit_grants.list()
            if hasattr(credit_grants, 'data') and credit_grants.data:
                total_balance = sum(grant.balance for grant in credit_grants.data if hasattr(grant, 'balance'))
                logger.info(f"✓ OpenAI balance fetched via SDK: ${total_balance:.2f}")
                return float(total_balance)
        except AttributeError:
            logger.debug("SDK billing API not available, trying direct HTTP request")

        # Method 2: Try direct HTTP request to billing API
        api_key = get_secret("OPENAI_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Python/OpenAI-Balance-Checker"
        }

        async with httpx.AsyncClient(timeout=10.0) as client_http:
            # Try credit_grants endpoint
            try:
                response = await client_http.get(
                    "https://api.openai.com/v1/billing/credit_grants",
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()

                if "data" in data:
                    total_balance = sum(grant.get("balance", 0) for grant in data["data"])
                    logger.info(f"✓ OpenAI balance fetched via HTTP: ${total_balance:.2f}")
                    return float(total_balance)
            except Exception as e:
                logger.debug(f"credit_grants endpoint failed: {type(e).__name__}")

            # Try usage endpoint (alternative)
            try:
                response = await client_http.get(
                    "https://api.openai.com/v1/billing/usage",
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()

                if "total_usage" in data:
                    # This gives usage in cents, convert to dollars
                    usage_cents = data["total_usage"]
                    logger.info(f"✓ OpenAI usage fetched: ${usage_cents / 100:.2f}")
                    return float(usage_cents / 100)
            except Exception as e:
                logger.debug(f"usage endpoint failed: {type(e).__name__}")

        logger.warning("Could not fetch OpenAI balance from any endpoint")
        return None

    except Exception as e:
        logger.warning(f"⚠️  Failed to fetch OpenAI balance: {type(e).__name__}: {e}")
        return None


def format_balance(balance: Optional[float]) -> str:
    """Format balance for display in digest.

    Args:
        balance: Balance in USD or None

    Returns:
        Formatted string with balance and warning if needed
    """
    if balance is None:
        return "Баланс OpenAI: недоступен"

    lines = [f"💳 Баланс OpenAI: ${balance:.2f}"]

    if balance < 0.50:
        lines.append("⚠️  Баланс менее 50¢ — рекомендуется пополнить аккаунт!")

    return "\n".join(lines)
