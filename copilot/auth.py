"""
GitHub Copilot Extension — request signature verification and org gating.

GitHub signs every inbound request with an ECDSA-P256 key.
The public key is fetched live from GitHub's API.

Set AICRITIC_DEV_MODE=true to skip verification during local development.
Set AICRITIC_ORG=my-org to restrict access to org members only.
"""
import base64
import os
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA

_GITHUB_KEYS_URL = "https://api.github.com/meta/public_keys/copilot_api"
_key_cache: dict = {}   # key_id → PEM bytes

# Org membership cache: token_hash → (is_member: bool, expires_at: float)
# Avoids a GitHub API call on every single request from the same user.
_membership_cache: dict = {}
_MEMBERSHIP_TTL = 300   # seconds — re-check every 5 minutes


async def _fetch_public_key(key_id: str) -> bytes:
    if key_id in _key_cache:
        return _key_cache[key_id]

    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(_GITHUB_KEYS_URL, headers={"Accept": "application/json"})
        r.raise_for_status()
        for key in r.json().get("public_keys", []):
            if key.get("key_identifier") == key_id:
                pem = key["key"].encode()
                _key_cache[key_id] = pem
                return pem

    raise ValueError(f"Public key '{key_id}' not found in GitHub's key list")


def extract_user_token(request_headers: dict) -> str:
    """Pull the bearer token from the Authorization header."""
    auth = request_headers.get("authorization") or request_headers.get("Authorization") or ""
    return auth.removeprefix("Bearer ").removeprefix("bearer ").strip()


async def verify_request(body: bytes, key_id: str, signature: str) -> bool:
    """Return True if the request signature is valid.
    In AICRITIC_DEV_MODE=true, always returns True (local development only).
    """
    if os.getenv("AICRITIC_DEV_MODE", "false").lower() == "true":
        return True

    if not key_id or not signature:
        return False

    try:
        pem = await _fetch_public_key(key_id)
        public_key = serialization.load_pem_public_key(pem)
        sig_bytes = base64.b64decode(signature)
        public_key.verify(sig_bytes, body, ECDSA(hashes.SHA256()))
        return True
    except (ValueError, KeyError, TypeError, httpx.HTTPError):
        return False
    except Exception:
        # cryptography library raises its own exception hierarchy; catch-all is intentional
        return False


async def verify_org_membership(token: str) -> tuple[bool, str]:
    """Check the token belongs to a member of AICRITIC_ORG.

    Returns (allowed: bool, username: str).
    If AICRITIC_ORG is not set, all authenticated users are allowed.
    In AICRITIC_DEV_MODE, always returns (True, "dev-user").
    Results are cached per token for _MEMBERSHIP_TTL seconds.
    """
    org = os.getenv("AICRITIC_ORG", "").strip()

    if os.getenv("AICRITIC_DEV_MODE", "false").lower() == "true":
        return True, "dev-user"

    if not token:
        return False, ""

    # Cache key: first 16 chars of token (enough to disambiguate, not enough to reconstruct)
    cache_key = token[:16]
    cached = _membership_cache.get(cache_key)
    if cached:
        is_member, username, expires_at = cached
        if time.time() < expires_at:
            return is_member, username

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            # Get the user identity first
            me = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            )
            me.raise_for_status()
            username = me.json().get("login", "")

            if not org:
                # No org restriction — any valid Copilot token is fine
                _membership_cache[cache_key] = (True, username, time.time() + _MEMBERSHIP_TTL)
                return True, username

            # Check org membership: 204 = member, 302/404 = not member
            check = await client.get(
                f"https://api.github.com/orgs/{org}/members/{username}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            )
            is_member = check.status_code == 204
            _membership_cache[cache_key] = (is_member, username, time.time() + _MEMBERSHIP_TTL)
            return is_member, username

    except (httpx.HTTPError, KeyError, ValueError):
        return False, ""
