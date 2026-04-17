"""Fixture: hardcoded credentials and API keys committed in source."""

DATABASE_PASSWORD = "admin123"
# Fixture values — intentionally NOT valid API key formats so GitHub's secret
# scanner does not flag this file, while the LLM still sees the assignment
# pattern and flags it as a hardcoded credential.
STRIPE_API_KEY = "FAKE_STRIPE_KEY_FOR_BENCHMARK_DO_NOT_USE"
AWS_ACCESS_KEY_ID = "FAKE_AWS_ID_FOR_BENCHMARK_DO_NOT_USE"
AWS_SECRET_ACCESS_KEY = "FAKE_AWS_SECRET_FOR_BENCHMARK_DO_NOT_USE"


def get_db_connection():
    return {"host": "prod-db.example.com", "password": DATABASE_PASSWORD}
