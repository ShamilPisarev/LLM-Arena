# LLM Arena

Compare responses from multiple LLMs side-by-side with a single prompt. Supports OpenRouter (200+ cloud models), Ollama, and LM Studio in one UI.

## Features

- **Multi-turn conversations** — each model maintains its own independent history
- **Parallel streaming** — all selected models respond simultaneously
- **OpenRouter** — browse and filter 200+ models, filter to free-only
- **Local models** — auto-discovers Ollama and LM Studio with one click
- **Markdown rendering** — code blocks, tables, lists rendered after streaming
- **No build step** — plain HTML + FastAPI, runs anywhere Python runs

## Quick Start

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Open **http://localhost:8000**

## Setup

### OpenRouter (cloud models)

1. Get a free API key at [openrouter.ai](https://openrouter.ai)
2. Click **API Key** in the top-right → paste → **Test** → **Save**
3. In the sidebar, click **Browse & add models** to pick what you want
   - Use the **Free only** filter to find models with no cost

### Ollama (local)

1. Install from [ollama.ai](https://ollama.ai)
2. Pull a model: `ollama pull llama3.2`
3. Click **↻ Refresh local** in the sidebar — it appears automatically

### LM Studio (local)

1. Open LM Studio → load a model → start the local server (port 1234)
2. Click **↻ Refresh local** — loaded models appear automatically

## Usage

- Select models via checkboxes in the sidebar
- Type a prompt → **Send →** (or **Ctrl+Enter**)
- Follow-up prompts continue the conversation for each model independently
- Click **↺ New chat** to start fresh

## Stack

- **Backend**: FastAPI, openai SDK, httpx
- **Frontend**: Vanilla HTML/CSS/JS (no framework, no build)
- **Model config**: `models_config.json` (auto-updated when you add/remove models)
