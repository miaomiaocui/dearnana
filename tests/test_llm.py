"""Unit tests for the LLM provider abstraction."""

import httpx
import pytest
from pydantic import BaseModel

from dearnana.llm import AnthropicProvider, OllamaProvider, get_provider


class _Schema(BaseModel):
    answer: str


class TestGetProvider:
    def test_default_no_key_is_none(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("DEARNANA_LLM_PROVIDER", raising=False)
        assert get_provider() is None

    def test_anthropic_with_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("DEARNANA_LLM_PROVIDER", raising=False)
        assert isinstance(get_provider(), AnthropicProvider)

    def test_ollama_selected(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("DEARNANA_LLM_PROVIDER", "ollama")
        assert isinstance(get_provider(), OllamaProvider)

    def test_ollama_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("DEARNANA_LLM_PROVIDER", " Ollama ")
        assert isinstance(get_provider(), OllamaProvider)


class TestOllamaProvider:
    def _mock_post(self, mocker, content):
        resp = mocker.Mock()
        resp.json.return_value = {"message": {"content": content}}
        resp.raise_for_status.return_value = None
        return mocker.patch("dearnana.llm.httpx.post", return_value=resp)

    def test_generate(self, mocker):
        post = self._mock_post(mocker, "hello from llama")
        assert OllamaProvider().generate("hi") == "hello from llama"
        payload = post.call_args.kwargs["json"]
        assert payload["stream"] is False
        assert "format" not in payload

    def test_parse_sends_schema_and_validates(self, mocker):
        post = self._mock_post(mocker, '{"answer": "42"}')
        result = OllamaProvider().parse("question", _Schema)
        assert result == _Schema(answer="42")
        payload = post.call_args.kwargs["json"]
        assert payload["format"] == _Schema.model_json_schema()

    def test_parse_invalid_json_returns_none(self, mocker):
        self._mock_post(mocker, "not json at all")
        assert OllamaProvider().parse("question", _Schema) is None

    def test_connection_error_returns_none(self, mocker):
        mocker.patch("dearnana.llm.httpx.post", side_effect=httpx.ConnectError("refused"))
        p = OllamaProvider()
        assert p.generate("hi") is None
        assert p.parse("hi", _Schema) is None

    def test_http_error_returns_none(self, mocker):
        resp = mocker.Mock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=mocker.Mock(), response=mocker.Mock()
        )
        mocker.patch("dearnana.llm.httpx.post", return_value=resp)
        assert OllamaProvider().generate("hi") is None

    def test_model_env_overrides(self, monkeypatch):
        monkeypatch.setenv("DEARNANA_LLM_MODEL", "qwen2.5:14b")
        monkeypatch.delenv("DEARNANA_PARSER_MODEL", raising=False)
        p = OllamaProvider()
        assert p._model == "qwen2.5:14b"
        assert p._parser_model == "qwen2.5:14b"  # falls back to main model

    def test_default_model(self, monkeypatch):
        monkeypatch.delenv("DEARNANA_LLM_MODEL", raising=False)
        monkeypatch.delenv("DEARNANA_PARSER_MODEL", raising=False)
        assert OllamaProvider()._model == "llama3.1:8b"

    def test_host_trailing_slash_stripped(self):
        assert OllamaProvider(host="http://box:11434/")._host == "http://box:11434"
