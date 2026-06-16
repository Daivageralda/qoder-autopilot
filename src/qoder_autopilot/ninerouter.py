"""
Qoder Autopilot — 9Router Integration
=======================================
Insert Qoder account connections directly into 9Router's SQLite database.
This bypasses the 9Router REST API (which requires authentication) by
writing to the database file directly.

Requirements:
    - 9Router must be installed and running on the same machine
    - The SQLite database file must be accessible via filesystem
    - No password required for direct DB access
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from . import config
from .errors import NineRouterDBNotFound, NineRouterError
from .logger import log, log_ok


def add_to_9router_device(
    email: str,
    display_name: str,
    device_token_body: dict,
    machine_id: str,
    db_path: str | None = None,
) -> bool:
    """Add a Qoder connection to 9Router DB using device token response.

    If a relay URL is configured, sends the token to the remote relay server.
    Otherwise, inserts directly into the local SQLite database.

    Args:
        email: The Qoder account email.
        display_name: Display name for the connection.
        device_token_body: Response from poll_device_token() containing
            token, refresh_token, user_id, expires_at, expires_in.
        machine_id: The machine_id from initiate_device_flow().
        db_path: Override path to 9Router SQLite DB.

    Returns:
        True if successfully inserted, False otherwise.
    """
    # Check if relay is configured
    if config.settings.has_relay:
        from .relay import send_to_relay

        return send_to_relay(
            relay_url=config.settings.ninerouter_relay_url,
            relay_token=config.settings.ninerouter_relay_token,
            email=email,
            display_name=display_name,
            device_token_body=device_token_body,
            machine_id=machine_id,
        )

    # Local insert (existing logic)
    db = db_path or config.NINEROUTER_DB
    log("💾 Adding to 9Router DB (device token flow)...")

    if not os.path.exists(db):
        raise NineRouterDBNotFound(db)

    try:
        at = device_token_body["token"]
        rt = device_token_body.get("refresh_token", "")
        user_id = device_token_body.get("user_id", "")
        expires_at = device_token_body.get("expires_at")
        expires_in = device_token_body.get("expires_in", 2592000)

        # Cap at 30 days (API sometimes returns unreasonable values)
        if expires_in > 2592000:
            expires_in = 2592000
        if not expires_at:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        conn = sqlite3.connect(db)
        c = conn.cursor()

        # Get next priority
        c.execute(
            "SELECT COALESCE(MAX(priority),0)+1 FROM providerConnections WHERE provider='qoder'"
        )
        prio = c.fetchone()[0]

        data = json.dumps(
            {
                "displayName": display_name,
                "accessToken": at,
                "refreshToken": rt,
                "expiresAt": expires_at,
                "testStatus": "active",
                "expiresIn": expires_in,
                "providerSpecificData": {
                    "authMethod": "device",
                    "userId": user_id,
                    "machineId": machine_id,
                    "organizationId": "",
                },
            }
        )

        now = datetime.now(timezone.utc).isoformat()
        c.execute(
            """INSERT INTO providerConnections
            (id, provider, authType, name, email, priority, isActive, data,
             createdAt, updatedAt)
            VALUES (?, 'qoder', 'oauth', ?, ?, ?, 1, ?, ?, ?)""",
            (str(uuid.uuid4()), display_name, email, prio, data, now, now),
        )
        conn.commit()
        conn.close()

        log_ok(f"Added to 9Router as #{prio} (device token)")
        return True

    except (sqlite3.Error, KeyError) as e:
        raise NineRouterError("DB insert failed", str(e)) from e
