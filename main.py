import asyncio
import json
import os
import time
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

app = FastAPI()
ROOT = Path(__file__).resolve().parent
_catalog = []
_catalog_time = 0.0


def load_config() -> dict:
    with open(ROOT / "models_config.json") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with open(ROOT / "models_config.json", "w") as f:
        json.dump(config, f, indent=2)


# ── Model discovery ───────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"app": "llm-arena"}


@app.get("/api/openrouter-models")
async def openrouter_models():
    global _catalog, _catalog_time
    if _catalog and time.monotonic() - _catalog_time < 300:
        return {"data": _catalog}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            _catalog = response.json()["data"]
            _catalog_time = time.monotonic()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(502, "Could not load OpenRouter model settings. Try again.") from exc
    return {"data": _catalog}

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


class GenerationSettings(BaseModel):
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, strict=True)


class CompareRequest(BaseModel):
    prompt: str
    history: list[HistoryTurn] = []
    models: list[dict]
    system_prompt: str = ""
    openrouter_key: str = ""
    parameters: dict[str, GenerationSettings] = Field(default_factory=dict)


def generation_options(settings: GenerationSettings, metadata: dict | None = None) -> dict:
    options = settings.model_dump(exclude_none=True)
    if metadata is not None:
        supported = metadata.get("supported_parameters")
        if supported is not None:
            unsupported = set(options) - set(supported)
            if unsupported:
                raise HTTPException(422, "Unsupported settings: " + ", ".join(sorted(unsupported)))
        limit = (metadata.get("top_provider") or {}).get("max_completion_tokens")
        if limit and options.get("max_tokens", 0) > limit:
            raise HTTPException(422, f"Output limit exceeds the advertised model maximum ({limit} tokens).")
    return options


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


async def stream_model(client, model_id, model_str, messages, queue, options=None):
    try:
        stream = await client.chat.completions.create(
            model=model_str, messages=messages, stream=True, **(options or {}),
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
    options_by_id = {}
    for cfg in request.models:
        settings = request.parameters.get(cfg["id"], GenerationSettings())
        metadata = None
        if cfg["provider"] == "openrouter" and settings.model_dump(exclude_none=True):
            catalog = (await openrouter_models())["data"]
            metadata = next((m for m in catalog if m["id"] == cfg["model"]), None)
            if metadata is None:
                raise HTTPException(422, "Model settings unavailable; use model defaults or choose a current model.")
        options_by_id[cfg["id"]] = generation_options(settings, metadata)
        if cfg["provider"] == "openrouter" and options_by_id[cfg["id"]]:
            options_by_id[cfg["id"]]["extra_body"] = {"provider": {"require_parameters": True}}

    async def generate() -> AsyncGenerator[str, None]:
        tasks = []
        for cfg in request.models:
            client = make_client(cfg, request.openrouter_key)
            if not client:
                continue
            msgs = build_messages(cfg["id"], request.system_prompt, request.history, request.prompt)
            tasks.append(asyncio.create_task(
                stream_model(client, cfg["id"], cfg["model"], msgs, queue, options_by_id[cfg["id"]])
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
    return FileResponse(ROOT / "index.html")
