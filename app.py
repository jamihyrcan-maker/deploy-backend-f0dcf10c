import os

# Keep startup validation from failing if env injection happens after source validation.
os.environ.setdefault("AUTOX_APP_ID", "mock")
os.environ.setdefault("AUTOX_APP_SECRET", "mock")
os.environ.setdefault("AUTOX_APP_CODE", "mock")
os.environ.setdefault("AUTOX_BASE_URL", "http://127.0.0.1:9001")

from app.main import app

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
