"""
Optional local overrides.

Do not store real credentials in source control.
Prefer environment variables in deployment.
"""

# AutoX vendor config (leave empty by default)
AUTOX_BASE_URL = ""
AUTOX_APP_ID = ""
AUTOX_APP_SECRET = ""
AUTOX_APP_CODE = ""
AUTOX_TOKEN_TTL_SECONDS = 3000

# Optional API key map example:
# API_KEYS = {"your-monitor-key": "monitor", "your-operator-key": "operator", "your-admin-key": "admin"}
API_KEYS = {}
