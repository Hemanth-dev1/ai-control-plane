"""Tests for the control plane authentication module."""

from __future__ import annotations

from uuid import uuid4

import pytest
from jose import jwt

from app.auth import create_access_token, decode_access_token, hash_api_key, revoke_token, verify_api_key
from app.config import settings


class TestAPIKeyHashing:
    def test_hash_and_verify(self):
        api_key = "test-api-key-12345"
        hashed = hash_api_key(api_key)
        assert hashed != api_key
        assert verify_api_key(api_key, hashed)

    def test_wrong_key_fails(self):
        hashed = hash_api_key("correct-key")
        assert not verify_api_key("wrong-key", hashed)


class TestJWTTokens:
    def test_create_and_decode_token(self):
        agent_id = uuid4()
        scopes = ["crm.lookup_customer"]
        token = create_access_token(agent_id, scopes)

        payload = decode_access_token(token)
        assert payload["sub"] == str(agent_id)
        assert payload["scopes"] == scopes
        assert payload["iss"] == settings.service_name
        assert payload["token_type"] == "access_token"

    def test_token_expiry(self):
        from datetime import timedelta

        agent_id = uuid4()
        token = create_access_token(agent_id, [], expires_delta=timedelta(seconds=-1))

        with pytest.raises(Exception):
            decode_access_token(token)

    def test_invalid_signature(self):
        token = jwt.encode({"sub": "test"}, "wrong-secret", algorithm="HS256")
        with pytest.raises(Exception):
            decode_access_token(token)

    def test_revoked_token(self):
        agent_id = uuid4()
        token = create_access_token(agent_id, [])
        revoke_token(token)

        with pytest.raises(Exception, match="revoked"):
            decode_access_token(token)
