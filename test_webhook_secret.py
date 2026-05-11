#!/usr/bin/env python3
"""Test webhook secret validation logic with constant-time comparison."""

import asyncio
import hmac
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
import json

app = FastAPI()

# Simulated webhook secret from config
WEBHOOK_SECRET = "webhook_secret_123"

@app.post("/webhook")
async def webhook(request: Request):
    """Test webhook handler with secure secret validation (constant-time comparison)."""
    secret = request.headers.get("X-Telegram-Bot-API-Secret-Token", "")
    # Use hmac.compare_digest for constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(secret, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid secret")

    data = await request.json()
    return {"ok": True, "message": f"Received update: {data.get('update_id')}"}

# Test with client
client = TestClient(app)

print("Testing webhook secret validation:\n")

# Test 1: Request with correct secret
print("Test 1: Request with CORRECT secret")
response = client.post(
    "/webhook",
    json={"update_id": 123, "message": {"text": "hello"}},
    headers={"X-Telegram-Bot-API-Secret-Token": WEBHOOK_SECRET}
)
print(f"  Status: {response.status_code}")
print(f"  Response: {response.json()}")
print(f"  Expected: 200 ✓\n" if response.status_code == 200 else f"  Expected: 200 ❌\n")

# Test 2: Request with wrong secret
print("Test 2: Request with WRONG secret")
response = client.post(
    "/webhook",
    json={"update_id": 456, "message": {"text": "world"}},
    headers={"X-Telegram-Bot-API-Secret-Token": "wrong_secret"}
)
print(f"  Status: {response.status_code}")
print(f"  Response: {response.json()}")
print(f"  Expected: 401 ✓\n" if response.status_code == 401 else f"  Expected: 401 ❌\n")

# Test 3: Request with missing secret
print("Test 3: Request with MISSING secret")
response = client.post(
    "/webhook",
    json={"update_id": 789, "message": {"text": "missing"}}
)
print(f"  Status: {response.status_code}")
print(f"  Response: {response.json()}")
print(f"  Expected: 401 ✓\n" if response.status_code == 401 else f"  Expected: 401 ❌\n")
