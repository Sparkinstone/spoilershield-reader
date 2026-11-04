"""Unit tests for the DeepSeek Flash / OpenAI-compatible LLM client."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.services.llm import LLMError, LLMService, parse_judgement


class FakeStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class _Completions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))]
        )


class FakeOpenAI:
    def __init__(self, *outcomes):
        self.chat = SimpleNamespace(completions=_Completions(outcomes))


def _service(outcomes, *, retries=0, config=None):
    config = config or Settings()
    config.LLM_MAX_RETRIES = retries
    fake = FakeOpenAI(*outcomes)
    sleeps: list[float] = []
    service = LLMService(config=config, client=fake, sleep=sleeps.append)
    return service, fake, sleeps


# ------------------------------------------------------------------ parsing
def test_parse_plain_json():
    result = parse_judgement('{"is_spoiler": true, "confidence": 0.82, "reason": "结局"}')
    assert result == {"is_spoiler": True, "confidence": 0.82, "reason": "结局"}


def test_parse_fenced_json():
    text = '```json\n{"is_spoiler": false, "confidence": 0.9, "reason": "ok"}\n```'
    assert parse_judgement(text)["is_spoiler"] is False


def test_parse_json_wrapped_in_prose():
    text = '判断如下：\n{"is_spoiler": true, "confidence": 0.7, "reason": "剧透"}'
    assert parse_judgement(text)["is_spoiler"] is True


@pytest.mark.parametrize("value", ["true", "yes", 1, True])
def test_parse_accepts_truthy_variants(value):
    payload = json.dumps(
        {"is_spoiler": value, "confidence": 0.8, "reason": "x"},
        ensure_ascii=False,
    )
    assert parse_judgement(payload)["is_spoiler"] is True


def test_parse_clamps_confidence():
    assert parse_judgement('{"is_spoiler": true, "confidence": 1.7, "reason": "x"}')[
        "confidence"
    ] == 1.0
    assert parse_judgement('{"is_spoiler": true, "confidence": -3, "reason": "x"}')[
        "confidence"
    ] == 0.0


def test_parse_missing_confidence_defaults_to_review():
    assert parse_judgement('{"is_spoiler": true, "reason": "x"}')["confidence"] == 0.5


def test_parse_missing_reason_gets_placeholder():
    assert parse_judgement('{"is_spoiler": false, "confidence": 0.9}')["reason"]


@pytest.mark.parametrize("text", ["", "   ", "not json at all", '{"confidence": 0.9}'])
def test_parse_rejects_bad_payloads(text):
    with pytest.raises(LLMError) as excinfo:
        parse_judgement(text)
    assert excinfo.value.kind == "bad_response"


# ---------------------------------------------------------------- behaviour
def test_judge_spoiler_uses_configured_deepseek_flash_model():
    service, fake, _ = _service(
        ['{"is_spoiler": false, "confidence": 0.95, "reason": "无剧透"}']
    )

    result = service.judge_spoiler(
        comment="这段描写很美。",
        current_paragraph="当前段落内容",
        future_paragraphs=["后续段落"],
    )

    assert result["is_spoiler"] is False
    call = fake.chat.completions.calls[0]
    assert call["model"] == "deepseek-flash"
    assert call["temperature"] == 0.0
    assert call["messages"][0]["role"] == "system"
    assert "这段描写很美。" in call["messages"][1]["content"]
    assert "后续段落" in call["messages"][1]["content"]


def test_build_prompt_without_future_context():
    service = LLMService(config=Settings(), client=FakeOpenAI())
    prompt = service.build_prompt("评论", "当前", [], no_context=True)
    assert "没有检索到相关后续段落" in prompt


def test_retries_transient_errors_then_succeeds():
    service, fake, sleeps = _service(
        [
            FakeStatusError(429),
            '{"is_spoiler": false, "confidence": 0.9, "reason": "ok"}',
        ],
        retries=2,
    )

    result = service.judge_spoiler("评论", "当前", ["后续"])

    assert result["confidence"] == 0.9
    assert len(fake.chat.completions.calls) == 2
    assert len(sleeps) == 1


def test_retries_timeouts():
    service, fake, sleeps = _service(
        [
            httpx.ReadTimeout("timed out"),
            '{"is_spoiler": true, "confidence": 0.8, "reason": "ok"}',
        ],
        retries=1,
    )

    assert service.judge_spoiler("评论", "当前", ["后续"])["is_spoiler"] is True
    assert len(sleeps) == 1


def test_does_not_retry_auth_errors():
    service, fake, sleeps = _service([FakeStatusError(401)], retries=3)

    with pytest.raises(LLMError) as excinfo:
        service.judge_spoiler("评论", "当前", ["后续"])

    assert excinfo.value.kind == "auth"
    assert len(fake.chat.completions.calls) == 1
    assert sleeps == []


def test_exhausted_retries_surface_last_error():
    service, fake, _ = _service([FakeStatusError(500), FakeStatusError(503)], retries=1)

    with pytest.raises(LLMError) as excinfo:
        service.judge_spoiler("评论", "当前", ["后续"])

    assert excinfo.value.retryable is True
    assert len(fake.chat.completions.calls) == 2


def test_connection_errors_keep_the_underlying_cause():
    from openai import APIConnectionError

    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    exc = APIConnectionError(request=request)
    exc.__cause__ = httpx.ConnectError("certificate verify failed")

    error = LLMService._classify(exc)

    assert error.kind == "connection"
    assert error.retryable is True
    assert "certificate verify failed" in str(error)


def test_api_timeout_is_retryable():
    from openai import APITimeoutError

    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    error = LLMService._classify(APITimeoutError(request=request))

    assert error.kind == "timeout"
    assert error.retryable is True


def test_model_not_found_error_is_actionable():
    service, _, _ = _service([FakeStatusError(404)])

    with pytest.raises(LLMError) as excinfo:
        service.judge_spoiler("评论", "当前", ["后续"])

    assert excinfo.value.kind == "model_not_found"
    assert "LLM_MODEL" in str(excinfo.value)


def test_empty_completion_is_a_bad_response():
    service, _, _ = _service(["   "])

    with pytest.raises(LLMError) as excinfo:
        service.judge_spoiler("评论", "当前", ["后续"])

    assert excinfo.value.kind == "bad_response"


def test_missing_api_key_fails_before_any_request():
    config = Settings()
    config.LLM_API_KEY = ""
    service = LLMService(config=config, client=None)

    with pytest.raises(LLMError) as excinfo:
        service.judge_spoiler("评论", "当前", ["后续"])

    assert excinfo.value.kind == "config"


# ------------------------------------------------------------------- config
def test_settings_defaults_to_deepseek_flash():
    config = Settings()
    assert config.LLM_MODEL == "deepseek-flash"
    assert config.LLM_MAX_RETRIES >= 0


def test_settings_prefer_explicit_llm_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "explicit-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1/")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash-preview")

    config = Settings()

    assert config.LLM_API_KEY == "explicit-key"
    assert config.LLM_BASE_URL == "https://example.test/v1"
    assert config.LLM_MODEL == "deepseek-flash-preview"


def test_settings_fall_back_to_legacy_openai_names(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://legacy.test/v1")

    config = Settings()

    assert config.LLM_API_KEY == "legacy-key"
    assert config.LLM_BASE_URL == "https://legacy.test/v1"


def test_threshold_is_clamped(monkeypatch):
    monkeypatch.setenv("SPOILER_CONFIDENCE_THRESHOLD", "5")
    assert Settings().SPOILER_CONFIDENCE_THRESHOLD == 1.0

    monkeypatch.setenv("SPOILER_CONFIDENCE_THRESHOLD", "-1")
    assert Settings().SPOILER_CONFIDENCE_THRESHOLD == 0.0


def test_repr_never_leaks_the_key():
    config = Settings()
    config.LLM_API_KEY = "sk-super-secret"
    assert "sk-super-secret" not in repr(config)
