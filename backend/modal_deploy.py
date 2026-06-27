"""
Deploy DevCopilot backend to Modal.

Usage (from backend/):
    modal deploy modal_deploy.py
"""

import modal

APP_NAME = "devcopilot-backend"
SECRET_NAME = "devcopilot-secrets"

app = modal.App(APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir(
        ".",
        remote_path="/root/backend",
        ignore=[".venv", "__pycache__", "temp_repos", "faiss_indices"],
    )
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    memory=4096,
    timeout=3600,
    cpu=2,
    max_containers=1,
)
@modal.concurrent(max_inputs=10)
@modal.asgi_app()
def fastapi_app():
    import sys

    sys.path.insert(0, "/root/backend")
    from main import app as web_app

    return web_app
