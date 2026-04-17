"""Fixture: outbound HTTP calls without timeouts — can hang indefinitely."""
import requests


def fetch_user_profile(user_id):
    response = requests.get(f"https://api.example.com/users/{user_id}")
    return response.json()


def post_webhook(url, payload):
    r = requests.post(url, json=payload)
    return r.status_code
