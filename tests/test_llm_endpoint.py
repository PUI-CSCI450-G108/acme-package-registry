import sys
import types
from typing import Any, Dict

import pytest


def test_is_llm_available_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEN_AI_STUDIO_API_KEY", raising=False)
    monkeypatch.delenv("GENAI_STUDIO_API_KEY", raising=False)
    from src.LLM_endpoint import is_llm_available

    assert is_llm_available() is False


def test_is_llm_available_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Provide API key via env
    monkeypatch.setenv("GEN_AI_STUDIO_API_KEY", "dummy")
    # Stub requests module so import succeeds
    dummy_requests = types.ModuleType("requests")
    monkeypatch.setitem(sys.modules, "requests", dummy_requests)

    from src.LLM_endpoint import is_llm_available

    assert is_llm_available() is True


def test_is_llm_available_import_requests_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEN_AI_STUDIO_API_KEY", "dummy")
    import builtins

    real_import = builtins.__import__

    def raising_import(name, *args, **kwargs):  # type: ignore[no-redef]
        if name == "requests":
            raise ImportError("no requests")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", raising_import, raising=True)

    from src.LLM_endpoint import is_llm_available

    assert is_llm_available() is False


def test_build_prompt_shapes() -> None:
    from src.LLM_endpoint import _build_prompt

    msgs = _build_prompt("code_quality", "readme text", {"k": 1})
    assert isinstance(msgs, list) and len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"

    msgs2 = _build_prompt("perf_claims", "readme text", {})
    assert msgs2[0]["role"] == "system"

    msgs3 = _build_prompt("other", "", {})
    assert msgs3[0]["role"] == "system"


def test_parse_choice_content_variants() -> None:
    from src.LLM_endpoint import _parse_choice_content

    a = {"choices": [{"message": {"content": "hello"}}]}
    b = {"content": "world"}
    assert _parse_choice_content(a) == "hello"
    assert _parse_choice_content(b) == "world"
    assert _parse_choice_content({}) == ""


def test_score_with_llm_success_direct_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import LLM_endpoint as le

    monkeypatch.setenv("GEN_AI_STUDIO_API_KEY", "dummy")
    # Ensure availability regardless of requests presence
    monkeypatch.setattr(le, "is_llm_available", lambda: True, raising=True)

    def fake_post(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"choices": [{"message": {"content": '{"score": 1, "reason": "ok"}'}}]}

    monkeypatch.setattr(le, "_post_chat", fake_post, raising=True)

    assert le.score_with_llm("code_quality", "readme", {}) == 1.0


def test_score_with_llm_success_embedded_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import LLM_endpoint as le

    monkeypatch.setenv("GENAI_STUDIO_API_KEY", "dummy")
    monkeypatch.setattr(le, "is_llm_available", lambda: True, raising=True)

    def fake_post(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"choices": [{"message": {"content": 'prefix {"score": 0.5, "reason": "ok"} suffix'}}]}

    monkeypatch.setattr(le, "_post_chat", fake_post, raising=True)

    assert le.score_with_llm("perf_claims", "readme", {}) == 0.5


def test_score_with_llm_invalid_json_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import LLM_endpoint as le

    monkeypatch.setenv("GENAI_STUDIO_API_KEY", "dummy")
    monkeypatch.setattr(le, "is_llm_available", lambda: True, raising=True)

    def fake_post(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"choices": [{"message": {"content": "no json here"}}]}

    monkeypatch.setattr(le, "_post_chat", fake_post, raising=True)

    assert le.score_with_llm("x", "", {}) is None


def test_score_with_llm_exception_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import LLM_endpoint as le

    monkeypatch.setenv("GEN_AI_STUDIO_API_KEY", "dummy")
    monkeypatch.setattr(le, "is_llm_available", lambda: True, raising=True)

    def boom(payload: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(le, "_post_chat", boom, raising=True)

    assert le.score_with_llm("x", "", {}) is None


def test_score_with_llm_model_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import LLM_endpoint as le

    monkeypatch.setenv("GEN_AI_STUDIO_API_KEY", "dummy")
    monkeypatch.setenv("GENAI_MODEL", "custom-model")
    monkeypatch.setattr(le, "is_llm_available", lambda: True, raising=True)

    captured: Dict[str, Any] = {}

    def fake_post(payload: Dict[str, Any]) -> Dict[str, Any]:
        captured["payload"] = payload
        return {"choices": [{"message": {"content": '{"score": 1, "reason": "ok"}'}}]}

    monkeypatch.setattr(le, "_post_chat", fake_post, raising=True)

    le.score_with_llm("x", "", {})
    assert captured["payload"]["model"] == "custom-model"


def test_score_with_llm_unavailable_early_return(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import LLM_endpoint as le

    monkeypatch.setattr(le, "is_llm_available", lambda: False, raising=True)
    assert le.score_with_llm("x", "", {}) is None


def test_score_with_llm_coerce_string_score(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import LLM_endpoint as le

    monkeypatch.setenv("GEN_AI_STUDIO_API_KEY", "dummy")
    monkeypatch.setattr(le, "is_llm_available", lambda: True, raising=True)

    def fake_post(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"choices": [{"message": {"content": '{"score": "0.5", "reason": "ok"}'}}]}

    monkeypatch.setattr(le, "_post_chat", fake_post, raising=True)
    assert le.score_with_llm("x", "", {}) == 0.5


def test_score_with_llm_non_numeric_score_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import LLM_endpoint as le

    monkeypatch.setenv("GEN_AI_STUDIO_API_KEY", "dummy")
    monkeypatch.setattr(le, "is_llm_available", lambda: True, raising=True)

    def fake_post(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"choices": [{"message": {"content": '{"score": "abc", "reason": "ok"}'}}]}

    monkeypatch.setattr(le, "_post_chat", fake_post, raising=True)
    assert le.score_with_llm("x", "", {}) is None


def test_post_chat_headers_and_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import LLM_endpoint as le

    monkeypatch.setenv("GEN_AI_STUDIO_API_KEY", "secret123")

    captured: Dict[str, Any] = {}

    class Resp:
        def __init__(self):
            self.text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class DummyRequests:
        def post(self, url, headers=None, json=None, timeout=None):  # type: ignore[no-redef]
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["timeout"] = timeout
            return Resp()

    dummy = types.ModuleType("requests")
    dummy.post = DummyRequests().post  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "requests", dummy)

    out = le._post_chat({"k": 1})
    assert out == {"ok": True}
    assert captured["headers"]["Authorization"] == "Bearer secret123"


def test_post_chat_raw_on_json_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import LLM_endpoint as le

    monkeypatch.setenv("GEN_AI_STUDIO_API_KEY", "secret123")

    class Resp:
        text = "plain"

        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("bad json")

    class DummyRequests:
        def post(self, url, headers=None, json=None, timeout=None):  # type: ignore[no-redef]
            return Resp()

    dummy = types.ModuleType("requests")
    dummy.post = DummyRequests().post  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "requests", dummy)

    out = le._post_chat({"k": 1})
    assert out == {"raw": "plain"}


