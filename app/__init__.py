import os

# PaaS bootstrap-safe defaults. Real env values override these.
os.environ.setdefault("AUTOX_APP_ID", "mock")
os.environ.setdefault("AUTOX_APP_SECRET", "mock")
os.environ.setdefault("AUTOX_APP_CODE", "mock")
os.environ.setdefault("AUTOX_BASE_URL", "http://127.0.0.1:9001")

from .main import app
