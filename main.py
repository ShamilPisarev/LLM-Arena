import asyncio
import json
import os
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from openai import AsyncOpenAI

app = FastAPI()


def load_config() -> dict:
    with open("models_config.json") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with open("models_config.json", "w") as f:
        json.dump(config, f, indent=2)


# ── Model discovery ───────────────────────────────────────────────────────────

@app.get("/api/models")
async def get_models():
    return load_config()["models"]


@app.get("/api/discover")
async def discover_local():
    ollama, lmstudio = [], []
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get("http://localhost:11434/api/tags", timeout=2.0)
            if r.status_code == 200:
                for m in r.json().get("models", []):
                    name = m["name"]
                    ollama.append({"id": f"ollama::{name}", "name": name, "model": name,
                                   "provider": "ollama", "base_url": "http://localhost:11434/v1"})
        except Exception:
            pass
        try:
            r = await client.get("http://localhost:1234/v1/models", timeout=2.0)
            if r.status_code == 200:
                for m in r.json().get("data", []):
                    mid = m["id"]
                    lmstudio.append({"id": f"lmstudio::{mid}", "name": mid, "model": mid,
                                     "provider": "lmstudio", "base_url": "http://localhost:1234/v1"})
        except Exception:
            pass
    return {"ollama": ollama, "lmstudio": lmstudio}


# ── Config mutations ──────────────────────────────────────────────────────────

class ModelEntry(BaseModel):
    id: str
    name: str
    model: str
    provider: str
    base_url: str = ""


@app.post("/api/models")
async def add_model(entry: ModelEntry):
    cfg = load_config()
    if any(m["id"] == entry.id for m in cfg["models"]):
        return {"error": "duplicate id"}
    row = entry.model_dump()
    if not row["base_url"]:
        del row["base_url"]
    cfg["models"].append(row)
    save_config(cfg)
    return {"ok": True}


@app.delete("/api/models/{model_id:path}")
async def delete_model(model_id: str):
    cfg = load_config()
    cfg["models"] = [m for m in cfg["models"] if m["id"] != model_id]
    save_config(cfg)
    return {"ok": True}


# ── Streaming compare ─────────────────────────────────────────────────────────

class HistoryTurn(BaseModel):
    user: str
    responses: dict[str, str]   # model_id -> assistant text


class CompareRequest(BaseModel):
    prompt: str
    history: list[HistoryTurn] = []
    models: list[dict]
    system_prompt: str = ""
    openrouter_key: str = ""


def build_messages(model_id: str, system_prompt: str, history: list[HistoryTurn], prompt: str) -> list:
    msgs = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    for turn in history:
        msgs.append({"role": "user", "content": turn.user})
        if turn.responses.get(model_id):
            msgs.append({"role": "assistant", "content": turn.responses[model_id]})
    msgs.append({"role": "user", "content": prompt})
    return msgs


def make_client(cfg: dict, openrouter_key: str) -> AsyncOpenAI | None:
    provider = cfg["provider"]
    if provider == "openrouter":
        return AsyncOpenAI(
            api_key=openrouter_key or os.environ.get("OPENROUTER_API_KEY", "no-key"),
            base_url="https://openrouter.ai/api/v1",
            default_headers={"HTTP-Referer": "http://localhost:8000"},
        )
    if provider in ("ollama", "lmstudio"):
        return AsyncOpenAI(
            api_key="local",
            base_url=cfg.get("base_url", (
                "http://localhost:11434/v1" if provider == "ollama"
                else "http://localhost:1234/v1"
            )),
        )
    return None


async def stream_model(client, model_id, model_str, messages, queue):
    try:
        stream = await client.chat.completions.create(
            model=model_str, messages=messages, stream=True, max_tokens=4096,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                await queue.put({"model_id": model_id, "content": chunk.choices[0].delta.content,
                                 "done": False, "error": None})
        await queue.put({"model_id": model_id, "content": "", "done": True, "error": None})
    except Exception as e:
        await queue.put({"model_id": model_id, "content": "", "done": True, "error": str(e)})


@app.post("/api/compare")
async def compare(request: CompareRequest):
    queue: asyncio.Queue = asyncio.Queue()

    async def generate() -> AsyncGenerator[str, None]:
        tasks = []
        for cfg in request.models:
            client = make_client(cfg, request.openrouter_key)
            if not client:
                continue
            msgs = build_messages(cfg["id"], request.system_prompt, request.history, request.prompt)
            tasks.append(asyncio.create_task(
                stream_model(client, cfg["id"], cfg["model"], msgs, queue)
            ))
        if not tasks:
            return
        done_count = 0
        while done_count < len(tasks):
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("done"):
                done_count += 1
        yield f"data: {json.dumps({'all_done': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
async def root():
    return FileResponse("index.html")
