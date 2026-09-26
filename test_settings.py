import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

import main
import launch


class SettingsTests(unittest.IsolatedAsyncioTestCase):
    def test_defaults_and_ranges(self):
        self.assertEqual(main.generation_options(main.GenerationSettings()), {})
        self.assertEqual(main.generation_options(main.GenerationSettings(temperature=0)), {"temperature": 0})
        for values in ({"temperature": -1}, {"temperature": 3}, {"top_p": 0}, {"top_p": 1.1}, {"max_tokens": 0}, {"max_tokens": 1.5}):
            with self.assertRaises(ValidationError):
                main.GenerationSettings(**values)

    def test_model_capabilities(self):
        metadata = {"supported_parameters": ["max_tokens"], "top_provider": {"max_completion_tokens": 8192}}
        for values in ({"temperature": 0.2}, {"max_tokens": 8193}):
            with self.assertRaises(HTTPException):
                main.generation_options(main.GenerationSettings(**values), metadata)
        self.assertEqual(main.generation_options(main.GenerationSettings(max_tokens=8192), metadata), {"max_tokens": 8192})
        self.assertEqual(main.generation_options(main.GenerationSettings(), {"top_provider": None}), {})

    async def test_request_forwarding_and_defaults(self):
        async def chunks():
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Test response"))])

        create = AsyncMock(side_effect=lambda **kwargs: chunks())
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        model = {"id": "test/model", "model": "test/model", "provider": "openrouter"}
        metadata = {"data": [{"id": "test/model", "supported_parameters": ["temperature", "top_p", "max_tokens"], "top_provider": {"max_completion_tokens": 8192}}]}
        transport = httpx.ASGITransport(app=main.app)
        with patch.object(main, "make_client", return_value=client), patch.object(main, "openrouter_models", AsyncMock(return_value=metadata)):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
                for parameters in ({}, {"temperature": 0, "top_p": 0.9, "max_tokens": 5000}):
                    response = await api.post("/api/compare", json={"prompt": "Hi", "system_prompt": "Be brief", "models": [model], "parameters": {"test/model": parameters}})
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("Test response", response.text)
                    sent = create.call_args.kwargs
                    self.assertEqual(sent["messages"][0], {"role": "system", "content": "Be brief"})
                    for key in ("temperature", "top_p", "max_tokens"):
                        if key in parameters:
                            self.assertEqual(sent[key], parameters[key])
                        else:
                            self.assertNotIn(key, sent)
                    if parameters:
                        self.assertTrue(sent["extra_body"]["provider"]["require_parameters"])
                response = await api.post("/api/compare", json={"prompt": "Hi", "models": [model], "parameters": {"test/model": {"max_tokens": 9000}}})
                self.assertEqual(response.status_code, 422)
                self.assertEqual((await api.get("/api/health")).json(), {"app": "llm-arena"})
                self.assertIn("Model settings", (await api.get("/")).text)

    def test_launcher_reuses_running_app(self):
        with patch.object(launch, "is_arena", return_value=True):
            self.assertEqual(launch.select_port(), (8000, True))


if __name__ == "__main__":
    unittest.main()
