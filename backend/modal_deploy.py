"""
Deploy DevCopilot backend to Modal.

Usage (from backend/):
    modal deploy modal_deploy.py
"""

import modal

APP_NAME = "devcopilot-backend"
SECRET_NAME = "devcopilot-secrets"
VOLUME_NAME = "devcopilot-data"
DATA_MOUNT = "/data"

app = modal.App(APP_NAME)

# Ingested repos (graph, FAISS index, metadata) live here and survive restarts
data_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install_from_requirements("requirements.txt")
    .env({"DATA_DIR": DATA_MOUNT, "MODAL_VOLUME_NAME": VOLUME_NAME})
    .add_local_dir(
        ".",
        remote_path="/root/backend",
        # .env stays local: keys come from the Modal secret
        ignore=[".venv", "__pycache__", "temp_repos", "faiss_indices", ".env"],
    )
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    volumes={DATA_MOUNT: data_volume},
    memory=4096,
    timeout=3600,
    cpu=2,
    max_containers=1,
    scaledown_window=20 * 60,  # stay warm 20 min after the last request
)
@modal.concurrent(max_inputs=10)
@modal.asgi_app()
def fastapi_app():
    import sys

    sys.path.insert(0, "/root/backend")
    from main import app as web_app

    return web_app
