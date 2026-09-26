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

**Windows:** double-click **Start LLM Arena.cmd** in this folder (or your local **LLM Arena** shortcut, if present). Machine-specific `.lnk` shortcuts are kept locally and excluded from Git. The launcher uses the existing project environment, or creates `.venv`, installs missing dependencies on first launch, and opens your browser when the server is ready. Python 3.10+ is required. Keep its terminal window open; close it or press Ctrl+C to stop. If port 8000 is occupied, it tries ports up to 8020.

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

- **Chats** in the sidebar lists conversations saved automatically in this browser. Messages, partial responses, drafts, system prompts, selected models, and generation settings are restored when you reopen a chat.
- **New chat** keeps the previous conversation. **Delete chat** deletes only the active chat after confirmation. Switching/deleting chats is disabled while a response is streaming.
- History uses browser local storage, not a cloud account or a backup. Use the same browser/profile and URL (including hostname and port); clearing site data removes saved chats. Storage failures show a warning instead of claiming the chat was saved.

- Click **Model settings** to set temperature, top-p, and output tokens separately for each selected model. Settings are saved in your browser.
- Blank fields use model/provider defaults: the app omits those parameters entirely, including the former fixed 4,096-token cap. **Use model defaults**, then **Save**, clears overrides for the selected models.
- OpenRouter's live catalog supplies published default values, supported controls, and advertised maximum output tokens. Missing defaults are labeled rather than guessed; unavailable model details allow defaults only. Provider/context limits still apply. Explicit overrides require a provider that supports them.

- Select models via checkboxes in the sidebar
- Type a prompt → **Send →** (or **Ctrl+Enter**)
- Follow-up prompts continue the conversation for each model independently
- Click **↺ New chat** to start fresh

## Stack

- **Backend**: FastAPI, openai SDK, httpx
- **Frontend**: Vanilla HTML/CSS/JS (no framework, no build)
- **Model config**: `models_config.json` (auto-updated when you add/remove models)
