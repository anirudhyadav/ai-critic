"""
GitHub Copilot Extension — request signature verification.

GitHub signs every inbound request with an ECDSA-P256 key.
The public key is fetched live from GitHub's API.

Set AICRITIC_DEV_MODE=true to skip verification during local development.
"""
import base64
import os

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA

_GITHUB_KEYS_URL = "https://api.github.com/meta/public_keys/copilot_api"
_key_cache: dict = {}   # key_id → PEM bytes (cached for the process lifetime)


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


async def verify_request(body: bytes, key_id: str, signature: str) -> bool:
    """
    Return True if the request signature is valid.
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
    except Exception:
        return False
