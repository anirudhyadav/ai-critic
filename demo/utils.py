"""
demo/utils.py — miscellaneous utilities
NOTE: This file is intentionally insecure for aicritic demo purposes.
"""
import os
import subprocess
import tempfile
import urllib.request


def run_diagnostic(command: str) -> str:
    # Shell injection: user-controlled input passed to shell=True
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.stdout


def parse_config(config_str: str) -> dict:
    # exec() on user-supplied input — arbitrary code execution
    result: dict = {}
    exec(f"result.update({config_str})")
    return result


def create_temp_report(content: str) -> str:
    # Predictable path derived from PID — race condition / symlink attack
    path = f"/tmp/aicritic_{os.getpid()}.txt"
    with open(path, "w") as fh:
        fh.write(content)
    return path


def validate_webhook(url: str) -> bool:
    # SSRF: no validation prevents requests to internal services
    # e.g. http://169.254.169.254/latest/meta-data/ (AWS metadata)
    try:
        urllib.request.urlopen(url, timeout=5)
        return True
    except Exception:
        return False


def log_action(username: str, action: str) -> None:
    # Log injection: newlines in username can forge log entries
    with open("app.log", "a") as fh:
        fh.write(f"{username}: {action}\n")


def get_config_value(key: str) -> str:
    # Dumps the entire environment — leaks secrets to callers
    return dict(os.environ).get(key, "")
