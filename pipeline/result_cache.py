"""Disk-based result cache for pipeline stages.

Cache key: SHA1(stage + model + system_prompt + user_content)
Cache location: .aicritic_cache/<stage>/<key[:2]>/<key>.json
TTL: AICRITIC_CACHE_TTL seconds (default 86400 = 24 h). Set to 0 to disable.

Effect:
- Re-running on unchanged code is near-instant (all three stages skipped).
- Any change to a file, role, or tool flips the key and forces a fresh run.
- Serves the same purpose as Anthropic prompt caching but works with the
  GitHub Models (Azure) endpoint which doesn't expose cache_control.
"""
import hashlib
import json
import os
import time

_DEFAULT_TTL = 86_400  # 24 hours


def _ttl() -> int:
    try:
        return int(os.environ.get("AICRITIC_CACHE_TTL", _DEFAULT_TTL))
    except ValueError:
        return _DEFAULT_TTL


def _cache_root() -> str:
    return os.environ.get("AICRITIC_CACHE_DIR", ".aicritic_cache")


def _key(stage: str, model: str, system_prompt: str, user_content: str) -> str:
    h = hashlib.sha1(usedforsecurity=False)
    for part in (stage, model, system_prompt, user_content):
        h.update(part.encode("utf-8", errors="replace"))
    return h.hexdigest()


def get(stage: str, model: str, system_prompt: str, user_content: str) -> dict | None:
    """Return cached result or None (miss / expired / disabled)."""
    if _ttl() == 0:
        return None
    digest = _key(stage, model, system_prompt, user_content)
    path = os.path.join(_cache_root(), stage, digest[:2], f"{digest}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
        if time.time() - record["ts"] > _ttl():
            return None
        return record["result"]
    except (OSError, KeyError, json.JSONDecodeError, TypeError):
        return None


def put(stage: str, model: str, system_prompt: str, user_content: str, result: dict) -> None:
    """Write result to cache (silently ignores write errors)."""
    if _ttl() == 0:
        return
    digest = _key(stage, model, system_prompt, user_content)
    subdir = os.path.join(_cache_root(), stage, digest[:2])
    try:
        os.makedirs(subdir, exist_ok=True)
        path = os.path.join(subdir, f"{digest}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"ts": time.time(), "result": result}, fh)
    except OSError:
        pass


def clear() -> int:
    """Delete all cache entries. Returns number of files removed."""
    root = _cache_root()
    removed = 0
    if not os.path.isdir(root):
        return 0
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if fname.endswith(".json"):
                try:
                    os.remove(os.path.join(dirpath, fname))
                    removed += 1
                except OSError:
                    pass
    return removed
