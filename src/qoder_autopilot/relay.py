"""
Qoder Autopilot — Relay Server
================================
Lightweight API server that receives device tokens from a remote
qoder-autopilot client and inserts them into the local 9Router
SQLite database.

Usage (on the server where 9Router runs):
    qoder-autopilot relay

The relay:
    1. Auto-detects the 9Router DB path (OS-aware)
    2. Generates a persistent auth token (saved to relay.json)
    3. Starts a FastAPI server on 0.0.0.0:8765
    4. Accepts POST /insert-token with Bearer auth

Install:
    pip install qoder-autopilot[relay]
"""

from __future__ import annotations

import hmac
import json
import os
import platform
import secrets
import sqlite3
import stat
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

RELAY_CONFIG_DIR = Path.home() / ".qoder-autopilot"
RELAY_CONFIG_FILE = RELAY_CONFIG_DIR / "relay.json"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8765


# ═══════════════════════════════════════════════════════════════════════════════
# TOKEN PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════


def _load_or_create_token(custom_token: str | None = None) -> str:
    """Load existing relay token from config file, or generate a new one.

    Priority:
        1. custom_token (from --token flag)
        2. Existing token in relay.json
        3. Generate new token and save
    """
    if custom_token:
        _save_token(custom_token)
        return custom_token

    if RELAY_CONFIG_FILE.exists():
        try:
            data = json.loads(RELAY_CONFIG_FILE.read_text())
            if token := data.get("auth_token"):
                return token
        except (json.JSONDecodeError, OSError):
            pass

    # Generate new token
    token = secrets.token_urlsafe(32)
    _save_token(token)
    return token


def _save_token(token: str) -> None:
    """Save relay token to config file with restricted permissions (600)."""
    RELAY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if RELAY_CONFIG_FILE.exists():
        try:
            data = json.loads(RELAY_CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    data["auth_token"] = token
    RELAY_CONFIG_FILE.write_text(json.dumps(data, indent=2))
    # Restrict file permissions: owner read/write only
    try:
        os.chmod(RELAY_CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 600
    except OSError:
        pass  # Windows may not support chmod the same way


# ═══════════════════════════════════════════════════════════════════════════════
# 9ROUTER DB PATH DETECTION
# ═══════════════════════════════════════════════════════════════════════════════


def _detect_9router_db(custom_path: str | None = None) -> str:
    """Auto-detect 9Router SQLite database path based on OS."""
    if custom_path:
        return os.path.expanduser(custom_path)

    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return os.path.join(appdata, "9router", "db", "data.sqlite")
        return os.path.join(str(Path.home()), "AppData", "Roaming", "9router", "db", "data.sqlite")

    return os.path.expanduser("~/.9router/db/data.sqlite")


# ═══════════════════════════════════════════════════════════════════════════════
# SQLITE INSERT (mirrors ninerouter.py logic exactly)
# ═══════════════════════════════════════════════════════════════════════════════


def _insert_token_into_db(
    db_path: str,
    email: str,
    display_name: str,
    device_token_body: dict,
    machine_id: str,
) -> dict:
    """Insert a device token into 9Router's providerConnections table.

    This replicates the exact logic from ninerouter.add_to_9router_device()
    so the relay can run independently without importing the full package.
    """
    at = device_token_body["token"]
    rt = device_token_body.get("refresh_token", "")
    user_id = device_token_body.get("user_id", "")
    expires_at = device_token_body.get("expires_at")
    expires_in = device_token_body.get("expires_in", 2592000)

    if expires_in > 2592000:
        expires_in = 2592000
    if not expires_at:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Get next priority
    c.execute("SELECT COALESCE(MAX(priority),0)+1 FROM providerConnections WHERE provider='qoder'")
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

    return {"priority": prio, "id": str(uuid.uuid4())}


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT: POST to relay
# ═══════════════════════════════════════════════════════════════════════════════


def send_to_relay(
    relay_url: str,
    relay_token: str,
    email: str,
    display_name: str,
    device_token_body: dict,
    machine_id: str,
) -> bool:
    """Send device token to remote relay server.

    Called from cli.py when ninerouter_relay_url is configured.

    Returns:
        True if successfully sent, False otherwise.
    """
    import requests

    url = f"{relay_url.rstrip('/')}/insert-token"
    try:
        resp = requests.post(
            url,
            json={
                "email": email,
                "display_name": display_name,
                "device_token_body": device_token_body,
                "machine_id": machine_id,
            },
            headers={"Authorization": f"Bearer {relay_token}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        prio = data.get("priority", "?")
        print(f"  ✅ Token sent to relay (priority #{prio})")
        return True
    except requests.ConnectionError:
        print(f"  ❌ Cannot reach relay at {relay_url}")
        return False
    except requests.Timeout:
        print(f"  ❌ Relay timeout: {relay_url}")
        return False
    except Exception as e:
        print(f"  ❌ Relay error: {e}")
        return False


def check_relay_connection(relay_url: str, relay_token: str) -> bool:
    """Test connectivity to relay server via health endpoint."""
    import requests

    url = f"{relay_url.rstrip('/')}/health"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {relay_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"  ✅ Relay connected: {data.get('status', 'ok')}")
        print(f"     DB: {data.get('db_path', '?')}")
        return True
    except Exception as e:
        print(f"  ❌ Relay unreachable: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# SERVER: Start relay
# ═══════════════════════════════════════════════════════════════════════════════


def start_relay(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    custom_token: str | None = None,
    custom_db_path: str | None = None,
) -> None:
    """Start the relay server.

    This function:
        1. Resolves the 9Router DB path
        2. Loads or generates an auth token
        3. Starts FastAPI on the given host:port

    Requires: pip install qoder-autopilot[relay]
    """
    try:
        import uvicorn
        from fastapi import Depends, FastAPI, HTTPException, Request
        from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    except ImportError:
        print("❌ Relay dependencies not installed.")
        print()
        print("  Install with:")
        print("  pip install qoder-autopilot[relay]")
        print()
        sys.exit(1)

    # Resolve DB path
    db_path = _detect_9router_db(custom_db_path)
    db_exists = os.path.exists(db_path)

    # Load/create token
    auth_token = _load_or_create_token(custom_token)

    # Build FastAPI app
    app = FastAPI(title="qoder-autopilot relay", version="1.1.0")
    security = HTTPBearer()

    # ── Rate limiting (in-memory, per-IP) ──
    _rate_limits: dict[str, list[float]] = {}
    RATE_LIMIT_WINDOW = 60  # seconds  # noqa: N806
    RATE_LIMIT_MAX = 30  # requests per window  # noqa: N806

    def _check_rate_limit(client_ip: str) -> bool:
        """Return True if request is allowed, False if rate-limited."""
        now = time.monotonic()
        if client_ip not in _rate_limits:
            _rate_limits[client_ip] = []
        # Prune old entries
        _rate_limits[client_ip] = [
            t for t in _rate_limits[client_ip] if now - t < RATE_LIMIT_WINDOW
        ]
        if len(_rate_limits[client_ip]) >= RATE_LIMIT_MAX:
            return False
        _rate_limits[client_ip].append(now)
        return True

    async def verify_token(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> str:
        # Timing-safe comparison to prevent side-channel attacks
        if not hmac.compare_digest(credentials.credentials, auth_token):
            raise HTTPException(status_code=401, detail="Invalid auth token")
        return credentials.credentials

    @app.get("/health")
    async def health(_: str = Depends(verify_token)):
        return {
            "status": "healthy",
            "db_path": db_path,
            "db_exists": os.path.exists(db_path),
            "version": "1.1.0",
        }

    @app.post("/insert-token")
    async def insert_token(
        payload: dict,
        request: Request,
        _: str = Depends(verify_token),
    ):
        # Rate limit check
        client_ip = request.client.host if request.client else "unknown"
        if not _check_rate_limit(client_ip):
            raise HTTPException(
                status_code=429,
                detail=f"Rate limited ({RATE_LIMIT_MAX} req/{RATE_LIMIT_WINDOW}s)",
            )
        # Validate required fields
        required = ["email", "display_name", "device_token_body", "machine_id"]
        missing = [f for f in required if f not in payload]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Missing fields: {', '.join(missing)}",
            )

        if not os.path.exists(db_path):
            raise HTTPException(
                status_code=503,
                detail=f"9Router DB not found at {db_path}",
            )

        try:
            result = _insert_token_into_db(
                db_path,
                email=payload["email"],
                display_name=payload["display_name"],
                device_token_body=payload["device_token_body"],
                machine_id=payload["machine_id"],
            )
            return {
                "status": "ok",
                "priority": result["priority"],
                "message": f"Token inserted for {payload['email']}",
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DB insert failed: {e}") from e

    # Print startup info
    # Detect if we're behind HTTPS (not directly, since uvicorn is HTTP)
    relay_url_is_https = False  # uvicorn always serves plain HTTP

    BOLD = "\033[1m"  # noqa: N806
    GREEN = "\033[32m"  # noqa: N806
    YELLOW = "\033[33m"  # noqa: N806
    CYAN = "\033[36m"  # noqa: N806
    NC = "\033[0m"  # noqa: N806

    print()
    print(f"  {BOLD}╔══════════════════════════════════════════════════╗{NC}")
    print(f"  {BOLD}║       📡 qoder-autopilot relay server            ║{NC}")
    print(f"  {BOLD}╚══════════════════════════════════════════════════╝{NC}")
    print()
    print(f"  {BOLD}9Router DB:{NC}  {db_path}")
    print(f"  {BOLD}DB status:{NC}   {'✅ Found' if db_exists else f'{YELLOW}⚠️  Not found{NC}'}")
    print(f"  {BOLD}Listen:{NC}       http://{host}:{port}")
    print(f"  {BOLD}Auth:{NC}         Bearer token (timing-safe + rate-limited)")
    print(f"  {BOLD}Token file:{NC}  {RELAY_CONFIG_FILE} (chmod 600)")
    print()
    print(f"  {GREEN}🔑{NC} {BOLD}Auth token:{NC} {CYAN}{auth_token}{NC}")
    print()
    print(f"  {BOLD}On your local machine, run:{NC}")
    print(f"    qoder-autopilot config set ninerouter-relay-url http://<your-server-ip>:{port}")
    print(f"    qoder-autopilot config set ninerouter-relay-token {auth_token}")
    print()

    # HTTPS warning for non-localhost bindings
    if host != "127.0.0.1" and not relay_url_is_https:
        print(f"  {YELLOW}⚠️  SECURITY: Running over plain HTTP!{NC}")
        print(f"  {YELLOW}   Tokens are sent unencrypted. For production, use a reverse proxy:{NC}")
        print(f"  {YELLOW}   → nginx/caddy with HTTPS → proxy_pass http://127.0.0.1:{port}{NC}")
        print(f"  {YELLOW}   Or bind to 127.0.0.1 and use an SSH tunnel.{NC}")
        print()

    if not db_exists:
        print(f"  {YELLOW}⚠️  DB not found. Relay will accept requests but inserts will fail.{NC}")
        print(f"  {YELLOW}   Make sure 9Router is installed and has been run at least once.{NC}")
        print()

    uvicorn.run(app, host=host, port=port, log_level="info")
