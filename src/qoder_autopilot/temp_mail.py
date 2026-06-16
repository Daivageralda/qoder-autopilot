"""
Qoder Autopilot — Temporary Email Client (Multi-Provider)
===========================================================
Supports multiple temp mail backends via provider pattern.

Providers:
    - **cloudflare**: Cloudflare Worker-based (default, no API key needed)
    - **moca**: Supabase-based API by Moca (requires x-api-key)

Usage:
    from qoder_autopilot.temp_mail import create_temp_mail

    tm = create_temp_mail()          # auto-detect from config
    addr = tm.generate()             # {"address": "abc@domain.com", ...}
    msgs = tm.inbox(addr["address"]) # [{"id": "...", "subject": "..."}, ...]
    msg  = tm.message(msgs[0]["id"]) # {"html": "...", "text": "..."}

    # Or pick provider explicitly:
    tm = create_temp_mail(provider="moca")
"""

import time
from abc import ABC, abstractmethod
from urllib.parse import quote as url_quote

import requests

from . import config
from .errors import TempMailError
from .logger import log, log_err, log_ok

# ═══════════════════════════════════════════════════════════════════════════════
# BASE CLASS
# ═══════════════════════════════════════════════════════════════════════════════


class TempMailProvider(ABC):
    """Abstract base class for temp mail providers."""

    @abstractmethod
    def generate(self) -> dict:
        """Generate a new temporary email address.

        Returns:
            dict with at least 'address' key.

        Raises:
            TempMailError: On API or network failure.
        """
        ...

    @abstractmethod
    def inbox(self, address: str) -> list[dict]:
        """Fetch inbox messages for the given address.

        Returns:
            List of message dicts with at least 'id' key.
        """
        ...

    @abstractmethod
    def message(self, msg_id: str) -> dict | None:
        """Fetch a single message by ID.

        Returns:
            Message dict with 'html' and/or 'text' keys, or None.
        """
        ...

    def wait_for_email(
        self,
        address: str,
        timeout: int = 180,
        interval: int = 5,
    ) -> list[dict]:
        """Poll inbox until at least one email arrives or timeout.

        Returns:
            List of messages if received, empty list on timeout.
        """
        log(f"   ⏳ Waiting for email at {address}...")
        start = time.time()
        while time.time() - start < timeout:
            try:
                msgs = self.inbox(address)
                if msgs:
                    log_ok(f"Got {len(msgs)} email(s)!")
                    return msgs
            except TempMailError as e:
                log(f"   ⚠️ Inbox error (will retry): {e}")
            time.sleep(interval)
        log_err("Timeout waiting for email")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER: CLOUDFLARE WORKER
# ═══════════════════════════════════════════════════════════════════════════════


class CloudflareProvider(TempMailProvider):
    """Cloudflare Worker-based temp mail (default, no API key needed).

    Endpoints:
        POST /api/generate           → create inbox
        GET  /api/inbox/{address}    → list messages
        GET  /api/message/{id}       → get message detail
    """

    def __init__(self, worker_url: str | None = None):
        self.url = (worker_url or config.WORKER_URL).rstrip("/")
        self._session = requests.Session()  # R4: connection pooling

    def generate(self) -> dict:
        last_err = None
        for attempt in range(1, 4):  # 3 retries
            try:
                r = self._session.post(f"{self.url}/api/generate", timeout=15)
                r.raise_for_status()
            except requests.RequestException as e:
                last_err = str(e)
                if attempt < 3:
                    log(f"   ⚠️ Generate attempt {attempt}/3 failed, retrying...")
                    time.sleep(2 * attempt)
                    continue
                raise TempMailError("Failed to generate email", str(e)) from e

            d = r.json()
            if d.get("code") != 0:
                last_err = d.get("error", "unknown")
                if attempt < 3:
                    log(f"   ⚠️ Generate attempt {attempt}/3 failed: {last_err}")
                    time.sleep(2 * attempt)
                    continue
                raise TempMailError("Generate failed", last_err)
            return d["data"]

        raise TempMailError("Failed to generate email after 3 attempts", last_err or "unknown")

    def inbox(self, address: str) -> list[dict]:
        try:
            r = self._session.get(f"{self.url}/api/inbox/{url_quote(address)}", timeout=15)
            r.raise_for_status()
        except requests.RequestException as e:
            raise TempMailError("Inbox fetch failed", str(e)) from e

        d = r.json()
        return d["data"].get("rows", []) if d.get("code") == 0 else []

    def message(self, msg_id: str) -> dict | None:
        try:
            r = self._session.get(f"{self.url}/api/message/{msg_id}", timeout=15)
            r.raise_for_status()
        except requests.RequestException as e:
            raise TempMailError("Message fetch failed", str(e)) from e

        d = r.json()
        return d["data"] if d.get("code") == 0 else None


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER: MOCA SUPABASE
# ═══════════════════════════════════════════════════════════════════════════════


class MocaProvider(TempMailProvider):
    """Supabase-based temp mail API by Moca (requires API key).

    Auth: x-api-key header (format: tmk_ + 64 hex chars)
    Base: https://ijrccpgiulrmfpavazsl.supabase.co/functions/v1/temp-mail-api

    Endpoints:
        GET  ?action=domains                          → list domains
        POST ?action=create      {desired_local, ...} → create inbox
        GET  ?action=messages    &address=&owner_token= → list messages
        GET  ?action=message     &id=&owner_token=     → message detail
        POST ?action=delete      {address, owner_token} → delete inbox
    """

    DEFAULT_BASE = "https://ijrccpgiulrmfpavazsl.supabase.co/functions/v1/temp-mail-api"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or config.MOCA_API_KEY
        if not self.api_key:
            raise TempMailError(
                "Moca provider requires API key",
                "Get one from @rubuskap on Telegram, then: "
                "qoder-autopilot config set moca-api-key tmk_xxx",
            )
        self.base = (base_url or config.MOCA_BASE_URL).rstrip("/")
        self._owner_token: str | None = None
        self._session = requests.Session()  # R4: connection pooling

    def _headers(self) -> dict:
        return {"x-api-key": self.api_key, "Content-Type": "application/json"}

    def _request(self, method: str, action: str, **kwargs) -> dict:
        """Make an API request."""
        url = f"{self.base}?action={action}"
        for k, v in kwargs.get("params", {}).items():
            url += f"&{k}={url_quote(str(v))}"

        try:
            r = self._session.request(
                method,
                url,
                headers=self._headers(),
                json=kwargs.get("json"),
                timeout=15,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            raise TempMailError(f"Request failed ({action})", str(e)) from e

        return r.json()

    def generate(self) -> dict:
        """Create a new inbox. Stores owner_token for subsequent calls."""
        body = {}
        # Optional: reuse owner_token to group inboxes
        if self._owner_token:
            body["owner_token"] = self._owner_token

        d = self._request("POST", "create", json=body)

        if "error" in d:
            raise TempMailError("Create inbox failed", d["error"])

        # Store owner_token for inbox/message calls
        self._owner_token = d.get("owner_token")

        return {
            "address": d["address"],
            "owner_token": d.get("owner_token", ""),
            "domain": d.get("domain", ""),
        }

    def inbox(self, address: str) -> list[dict]:
        if not self._owner_token:
            raise TempMailError(
                "No owner_token",
                "Call generate() first, or set owner_token manually",
            )

        d = self._request(
            "GET",
            "messages",
            params={"address": address, "owner_token": self._owner_token},
        )

        if "error" in d:
            raise TempMailError("Inbox fetch failed", d["error"])

        return d.get("messages", [])

    def message(self, msg_id: str) -> dict | None:
        if not self._owner_token:
            raise TempMailError("No owner_token", "Call generate() first")

        d = self._request(
            "GET",
            "message",
            params={"id": msg_id, "owner_token": self._owner_token},
        )

        if "error" in d:
            return None

        return d  # Full message object with html/text

    def delete_inbox(self, address: str) -> bool:
        """Delete an inbox and all its messages."""
        if not self._owner_token:
            return False

        d = self._request(
            "POST",
            "delete",
            json={"address": address, "owner_token": self._owner_token},
        )
        return d.get("ok", False)


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY
# ═══════════════════════════════════════════════════════════════════════════════


def create_temp_mail(provider: str | None = None) -> TempMailProvider:
    """Create a temp mail provider instance.

    Auto-detects provider from config if not specified:
        - If MOCA_API_KEY is set → MocaProvider
        - Otherwise → CloudflareProvider (default)

    Args:
        provider: "cloudflare" or "moca". None = auto-detect.

    Returns:
        TempMailProvider instance.
    """
    if provider is None:
        provider = config.MAIL_PROVIDER

    if provider == "moca":
        return MocaProvider()
    elif provider == "cloudflare":
        return CloudflareProvider()
    else:
        raise TempMailError(
            f"Unknown provider: {provider}",
            "Available: cloudflare, moca",
        )


# Backward compat: TempMail() returns the default provider
def TempMail() -> TempMailProvider:  # noqa: N802
    """Backward-compatible alias for create_temp_mail()."""
    return create_temp_mail()
