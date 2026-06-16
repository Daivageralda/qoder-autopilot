"""
Qoder Autopilot — OAuth / PKCE Device Auth Flow
=================================================
Implements the PKCE (Proof Key for Code Exchange) device authorization flow
for Qoder, reverse-engineered from 9Router's QoderService.

Flow:
    1. Generate PKCE verifier + challenge
    2. Build auth URL with oauth_callback parameters
    3. User completes auth in browser (sign-up / sign-in)
    4. Poll device token endpoint until authorized
    5. Use access token for API calls
"""

import base64
import hashlib
import os
import time
import uuid
from urllib.parse import quote as url_quote
from urllib.parse import urlencode

import requests

from . import config
from .logger import log, log_err, log_ok


def base64url_encode(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE verifier + S256 challenge (32 random bytes).

    Returns:
        Tuple of (verifier, challenge).
    """
    verifier = base64url_encode(os.urandom(32))
    challenge = base64url_encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def initiate_device_flow() -> dict:
    """Generate the full device auth URL and parameters.

    Returns:
        dict with keys: auth_url, callback_url, verifier, challenge, nonce, machine_id
    """
    verifier, challenge = generate_pkce_pair()
    nonce = str(uuid.uuid4())
    machine_id = str(uuid.uuid4())

    # Build the oauth_callback params (mirrors 9Router dashboard)
    callback_params = urlencode({
        "challenge": challenge,
        "challenge_method": "S256",
        "directLogin": "true",
        "machine_id": machine_id,
        "nonce": nonce,
    })
    callback_url = f"{config.QODER_LOGIN_URL}?{callback_params}"

    # Wrap in sign-in page with oauth_callback
    auth_url = (
        f"{config.QODER_SIGNIN_URL}"
        f"?oauth_callback={url_quote(callback_url, safe='')}"
    )

    return {
        "auth_url": auth_url,
        "callback_url": callback_url,
        "verifier": verifier,
        "challenge": challenge,
        "nonce": nonce,
        "machine_id": machine_id,
    }


def poll_device_token(
    nonce: str,
    verifier: str,
    max_attempts: int = 120,
    interval: int = 2,
) -> dict | None:
    """Poll Qoder deviceToken endpoint until user authorizes.

    Args:
        nonce: The nonce from initiate_device_flow().
        verifier: The PKCE verifier from initiate_device_flow().
        max_attempts: Maximum number of polling attempts.
        interval: Seconds between polls.

    Returns:
        dict with {token, refresh_token, user_id, expires_at} or None on timeout.
    """
    url = (
        f"{config.QODER_DEVICE_TOKEN_URL}"
        f"?nonce={url_quote(nonce)}"
        f"&verifier={url_quote(verifier)}"
        f"&challenge_method=S256"
    )
    headers = {"Accept": "application/json", "User-Agent": "Go-http-client/2.0"}

    log(f"   🔄 Polling device token (max {max_attempts * interval}s)...")
    for i in range(max_attempts):
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code in (202, 404):
                # Still pending
                if i % 10 == 0 and i > 0:
                    log(f"   ⏳ Poll #{i} — still waiting...")
                time.sleep(interval)
                continue
            if r.status_code == 200:
                body = r.json()
                if body.get("token"):
                    log_ok(
                        f"Device token received! "
                        f"user_id={body.get('user_id', '?')}"
                    )
                    return body
                else:
                    log(f"   ⚠️ 200 but no token: {body}")
            else:
                log(f"   ⚠️ Poll #{i} unexpected status: {r.status_code}")
            time.sleep(interval)
        except requests.RequestException as e:
            log(f"   ⚠️ Poll error: {e}")
            time.sleep(interval)

    log_err("Device token poll timed out")
    return None


def fetch_userinfo(access_token: str) -> dict:
    """Fetch Qoder user profile. Best-effort, returns {} on failure."""
    try:
        r = requests.get(
            config.QODER_USERINFO_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": "Go-http-client/2.0",
            },
            timeout=15,
        )
        if r.ok:
            return r.json()
    except requests.RequestException:
        pass
    return {}
