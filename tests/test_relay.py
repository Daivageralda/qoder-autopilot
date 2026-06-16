"""Tests for relay module."""

import json
import os
import sqlite3
import tempfile
import uuid

import pytest

from qoder_autopilot.relay import (
    _detect_9router_db,
    _insert_token_into_db,
    _load_or_create_token,
    _save_token,
    check_relay_connection,
    send_to_relay,
)


# ═══════════════════════════════════════════════════════════════════════════════
# TOKEN PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════


class TestTokenPersistence:
    def test_generate_new_token(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "qoder_autopilot.relay.RELAY_CONFIG_DIR", tmp_path
        )
        monkeypatch.setattr(
            "qoder_autopilot.relay.RELAY_CONFIG_FILE", tmp_path / "relay.json"
        )
        token = _load_or_create_token()
        assert len(token) > 20  # secrets.token_urlsafe(32) is ~43 chars

    def test_custom_token(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "qoder_autopilot.relay.RELAY_CONFIG_DIR", tmp_path
        )
        monkeypatch.setattr(
            "qoder_autopilot.relay.RELAY_CONFIG_FILE", tmp_path / "relay.json"
        )
        token = _load_or_create_token(custom_token="my-custom-token")
        assert token == "my-custom-token"

    def test_persist_and_reload(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "qoder_autopilot.relay.RELAY_CONFIG_DIR", tmp_path
        )
        monkeypatch.setattr(
            "qoder_autopilot.relay.RELAY_CONFIG_FILE", tmp_path / "relay.json"
        )
        # Generate first token
        token1 = _load_or_create_token()
        # Reload should return same token
        token2 = _load_or_create_token()
        assert token1 == token2

    def test_save_token(self, tmp_path, monkeypatch):
        config_file = tmp_path / "relay.json"
        monkeypatch.setattr(
            "qoder_autopilot.relay.RELAY_CONFIG_DIR", tmp_path
        )
        monkeypatch.setattr(
            "qoder_autopilot.relay.RELAY_CONFIG_FILE", config_file
        )
        _save_token("test-token-123")
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data["auth_token"] == "test-token-123"


# ═══════════════════════════════════════════════════════════════════════════════
# DB PATH DETECTION
# ═══════════════════════════════════════════════════════════════════════════════


class TestDBDetection:
    def test_custom_path(self):
        path = _detect_9router_db("/custom/path/db.sqlite")
        assert path == "/custom/path/db.sqlite"

    def test_default_path_macos(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        path = _detect_9router_db()
        assert "9router" in path
        assert "data.sqlite" in path

    def test_default_path_windows(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Windows")
        monkeypatch.setenv("APPDATA", "C:\\Users\\Test\\AppData\\Roaming")
        path = _detect_9router_db()
        assert "9router" in path


# ═══════════════════════════════════════════════════════════════════════════════
# SQLITE INSERT
# ═══════════════════════════════════════════════════════════════════════════════


class TestInsertToken:
    def _create_test_db(self, tmp_path):
        """Create a minimal 9Router-like SQLite DB for testing."""
        db_path = str(tmp_path / "test.sqlite")
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE providerConnections (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                authType TEXT,
                name TEXT,
                email TEXT,
                priority INTEGER DEFAULT 0,
                isActive INTEGER DEFAULT 1,
                data TEXT,
                createdAt TEXT,
                updatedAt TEXT
            )
        """)
        conn.commit()
        conn.close()
        return db_path

    def test_insert_success(self, tmp_path):
        db_path = self._create_test_db(tmp_path)
        device_token = {
            "token": "test-access-token-123",
            "refresh_token": "test-refresh-token",
            "user_id": "user-456",
            "expires_at": "2025-12-31T23:59:59Z",
            "expires_in": 2592000,
        }
        result = _insert_token_into_db(
            db_path,
            email="test@example.com",
            display_name="Test User",
            device_token_body=device_token,
            machine_id="machine-789",
        )
        assert result["priority"] == 1

        # Verify the insert
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT * FROM providerConnections").fetchone()
        conn.close()
        assert row is not None
        assert row[4] == "test@example.com"  # email column

    def test_insert_increments_priority(self, tmp_path):
        db_path = self._create_test_db(tmp_path)
        device_token = {
            "token": "tok1",
            "refresh_token": "rt1",
            "user_id": "u1",
        }
        r1 = _insert_token_into_db(db_path, "a@b.com", "A", device_token, "m1")
        r2 = _insert_token_into_db(db_path, "c@d.com", "B", device_token, "m2")
        assert r2["priority"] == r1["priority"] + 1

    def test_insert_missing_db(self, tmp_path):
        with pytest.raises(Exception):
            _insert_token_into_db(
                str(tmp_path / "nonexistent.sqlite"),
                "a@b.com",
                "A",
                {"token": "tok"},
                "m1",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT: send_to_relay / test_relay_connection
# ═══════════════════════════════════════════════════════════════════════════════


class TestRelayClient:
    def test_send_to_relay_connection_error(self):
        """Connection to unreachable server should return False."""
        result = send_to_relay(
            relay_url="http://localhost:19999",
            relay_token="fake-token",
            email="test@example.com",
            display_name="Test",
            device_token_body={"token": "tok"},
            machine_id="m1",
        )
        assert result is False

    def test_check_relay_connection_error(self):
        """Health check to unreachable server should return False."""
        result = check_relay_connection(
            relay_url="http://localhost:19999",
            relay_token="fake-token",
        )
        assert result is False
