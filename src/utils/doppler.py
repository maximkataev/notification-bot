"""Doppler secrets management."""

import subprocess
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_secret(key: str) -> Optional[str]:
    """Fetch secret from Doppler, fallback to .env."""
    # First try environment variable (works with .env via python-dotenv)
    env_secret = os.getenv(key)
    if env_secret:
        logger.debug(f"✓ Secret from env: {key}")
        return env_secret

    # Then try Doppler
    try:
        logger.debug(f"Fetching secret from Doppler: {key}")
        result = subprocess.run(
            ["doppler", "secrets", "get", key, "--plain"],
            capture_output=True,
            text=True,
            check=True,
        )
        secret = result.stdout.strip()
        logger.info(f"✓ Secret fetched from Doppler: {key}")
        return secret
    except subprocess.CalledProcessError as e:
        logger.debug(f"Doppler failed for {key}: {e.stderr}")
        return None


def get_all_secrets() -> dict:
    """Fetch all secrets from Doppler as JSON."""
    try:
        logger.debug("Fetching all secrets from Doppler")
        result = subprocess.run(
            ["doppler", "secrets", "download", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
        secrets = json.loads(result.stdout)
        logger.info(f"✓ Loaded {len(secrets)} secrets from Doppler")
        return secrets
    except subprocess.CalledProcessError as e:
        logger.error(f"✗ Failed to fetch secrets: {e.stderr}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"✗ Failed to parse secrets JSON: {e}")
        return {}
