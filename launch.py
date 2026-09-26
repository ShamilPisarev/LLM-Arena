"""Double-click launcher: prepare dependencies, open the browser, serve locally."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent


def is_arena(port):
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
            return json.load(response).get("app") == "llm-arena"
    except Exception:
        return False


def select_port():
    for port in range(8000, 8021):
        if is_arena(port):
            return port, True
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port, False
            except OSError:
                continue
    raise RuntimeError("Ports 8000–8020 are busy. Close an unused local server and try again.")


def main():
    os.chdir(ROOT)
    # Keep installation isolated in this project, including on first launch.
    if Path(sys.prefix).resolve() not in (ROOT / "venv", ROOT / ".venv"):
        python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not python.exists():
            print("Preparing the app's Python environment…", flush=True)
            subprocess.check_call([sys.executable, "-m", "venv", str(ROOT / ".venv")])
        return subprocess.call([str(python), str(ROOT / "launch.py")])
    if any(importlib.util.find_spec(name) is None for name in ("fastapi", "uvicorn", "openai", "httpx")):
        print("Installing app dependencies (first launch)…", flush=True)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])
    import uvicorn
    port, existing = select_port()
    url = f"http://127.0.0.1:{port}"
    if existing:
        webbrowser.open(url)
        return 0

    def open_when_ready():
        for _ in range(100):
            if is_arena(port):
                webbrowser.open(url)
                return
            time.sleep(0.2)

    threading.Thread(target=open_when_ready, daemon=True).start()
    print(f"LLM Arena: {url}\nKeep this window open. Close it or press Ctrl+C to stop.", flush=True)
    uvicorn.run("main:app", host="127.0.0.1", port=port)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Could not start LLM Arena: {exc}", file=sys.stderr)
        sys.exit(1)
