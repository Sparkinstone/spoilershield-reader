"""LLM client for spoiler judgement.

The project originally called Anthropic directly with a hard-coded model name.
It now talks to any OpenAI-compatible endpoint and defaults to DeepSeek Flash
(``LLM_MODEL=deepseek-flash``), which is what the product runs on.

Configuration (all optional, environment driven):

* ``LLM_API_KEY``   / ``DEEPSEEK_API_KEY`` / ``OPENAI_API_KEY``
* ``LLM_BASE_URL``  / ``OPENAI_API_BASE``   (default ``https://api.deepseek.com/v1``)
* ``LLM_MODEL``     (default ``deepseek-flash``)
* ``LLM_TIMEOUT``, ``LLM_MAX_RETRIES``, ``LLM_TEMPERATURE``, ``LLM_MAX_TOKENS``
* ``LLM_SSL_VERIFY`` (default ``true``; set ``false`` only for a private
  gateway with a broken certificate)
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any

import httpx
from openai import APIConnectionError, APITimeoutError, OpenAI

from app.config import settings as default_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a spoiler-detection classifier for a Chinese online reading platform. "
    "Decide whether a reader's comment reveals plot information that appears AFTER "
    "the paragraph being commented on. Reply with a single JSON object and nothing else."
)

_JSON_SCHEMA_HINT = (
    '{"is_spoiler": true|false, "confidence": 0.0-1.0, "reason": "short explanation"}'
)

_MAX_FUTURE_CHARS = 4000


class LLMError(RuntimeError):
    """A classified LLM failure, safe to show to operators (never contains the key)."""

    def __init__(
        self,
        message: str,
        *,
        kind: str = "api",
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.status_code = status_code

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.kind}] {super().__str__()}"


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "是", "剧透"}:
            return True
        if lowered in {"false", "no", "0", "否", "不是", "非剧透"}:
            return False
    raise LLMError(f"模型返回了无法解析的 is_spoiler: {value!r}", kind="bad_response")


def _coerce_confidence(value: Any) -> float:
    if value is None or value == "":
        # A missing score must not auto-publish: send it to human review.
        return 0.5
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise LLMError(f"模型返回了无法解析的 confidence: {value!r}", kind="bad_response") from exc
    if confidence != confidence:  # NaN
        raise LLMError("模型返回了 NaN confidence", kind="bad_response")
    return min(1.0, max(0.0, confidence))


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def parse_judgement(text: str) -> dict:
    """Parse the model's reply into ``{is_spoiler, confidence, reason}``."""
    if not text or not text.strip():
        raise LLMError("模型返回了空响应", kind="bad_response")

    payload = _strip_code_fence(text)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        # Some models wrap the object in prose; grab the outermost {...}.
        match = re.search(r"\{.*\}", payload, flags=re.DOTALL)
        if not match:
            raise LLMError(f"模型响应不是 JSON: {payload[:200]!r}", kind="bad_response")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError(f"模型响应不是合法 JSON: {payload[:200]!r}", kind="bad_response") from exc

    if not isinstance(data, dict):
        raise LLMError(f"模型响应不是 JSON 对象: {payload[:200]!r}", kind="bad_response")

    is_spoiler = _coerce_bool(data.get("is_spoiler"))
    confidence = _coerce_confidence(data.get("confidence"))
    reason = str(data.get("reason") or "").strip()
    if not reason:
        reason = "（模型未给出理由）"

    return {"is_spoiler": is_spoiler, "confidence": confidence, "reason": reason[:500]}


class LLMService:
    def __init__(self, config=None, client: OpenAI | None = None, sleep=time.sleep) -> None:
        self.settings = config or default_settings
        self.model = self.settings.LLM_MODEL
        self.temperature = self.settings.LLM_TEMPERATURE
        self.max_tokens = self.settings.LLM_MAX_TOKENS
        self.timeout = self.settings.LLM_TIMEOUT
        self.max_retries = self.settings.LLM_MAX_RETRIES
        self.verify_ssl = getattr(self.settings, "LLM_SSL_VERIFY", True)
        self.api_key = self.settings.LLM_API_KEY
        self.base_url = self.settings.LLM_BASE_URL
        self._client = client
        self._sleep = sleep

    # ------------------------------------------------------------------ client
    def _get_client(self) -> OpenAI:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise LLMError(
                "未配置 LLM_API_KEY（或 OPENAI_API_KEY / DEEPSEEK_API_KEY），无法调用模型",
                kind="config",
            )
        http_client = None
        if not self.verify_ssl:
            logger.warning("LLM_SSL_VERIFY=false, TLS certificate verification is disabled")
            http_client = httpx.Client(verify=False, timeout=self.timeout)
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=0,  # retries are handled here so they are observable
            http_client=http_client,
        )
        return self._client

    # ------------------------------------------------------------------ prompt
    def build_prompt(
        self,
        comment: str,
        current_paragraph: str,
        future_paragraphs: list[str],
        no_context: bool = False,
    ) -> str:
        if no_context or not future_paragraphs:
            future_text = (
                "（没有检索到相关后续段落。）仅根据评论内容与常识判断；"
                "如果评论看起来只是对当前段落的感受，请判为非剧透。"
            )
        else:
            joined = "\n\n---\n\n".join(future_paragraphs)
            future_text = joined[:_MAX_FUTURE_CHARS]

        return (
            "任务：判断下面的读者评论是否剧透了「当前段落」之后的情节。\n\n"
            f"【当前段落】\n{current_paragraph}\n\n"
            f"【书中更靠后的相关段落】\n{future_text}\n\n"
            f"【读者评论】\n{comment}\n\n"
            "判断规则：\n"
            "1. 只有泄露了当前段落之后才会发生的情节、结局、人物身份等才算剧透；\n"
            "2. 对当前段落本身的感受、文笔评价、合理猜测不算剧透；\n"
            "3. confidence 表示你对该判断的把握，0 到 1 之间的小数；\n"
            "4. 没有把握时请给低 confidence，系统会转人工审核。\n\n"
            f"只输出 JSON，格式：{_JSON_SCHEMA_HINT}"
        )

    # ------------------------------------------------------------------ errors
    @staticmethod
    def _classify(exc: Exception) -> LLMError:
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)

        if status in (401, 403):
            return LLMError(
                f"模型鉴权失败（HTTP {status}），请检查 API Key",
                kind="auth",
                status_code=status,
            )
        if status == 404:
            return LLMError(
                "模型或接口不存在（HTTP 404），请检查 LLM_MODEL / LLM_BASE_URL",
                kind="model_not_found",
                status_code=status,
            )
        if status == 429:
            return LLMError(
                "模型限流（HTTP 429）", kind="rate_limit", retryable=True, status_code=status
            )
        if status is not None and status >= 500:
            return LLMError(
                f"模型服务异常（HTTP {status}）", kind="api", retryable=True, status_code=status
            )
        if status in (408, 409):
            return LLMError(
                f"模型请求冲突（HTTP {status}）", kind="api", retryable=True, status_code=status
            )
        if isinstance(exc, (APITimeoutError, httpx.TimeoutException, TimeoutError)):
            return LLMError(f"模型请求超时（{exc}）", kind="timeout", retryable=True)
        if isinstance(exc, (APIConnectionError, httpx.TransportError, ConnectionError)):
            cause = exc.__cause__ or exc
            return LLMError(f"无法连接模型服务：{cause}", kind="connection", retryable=True)
        if isinstance(exc, LLMError):
            return exc
        return LLMError(f"模型调用失败：{exc}", kind="api")

    # ------------------------------------------------------------------ call
    def _chat(self, prompt: str) -> str:
        client = self._get_client()
        last_error: LLMError | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                content = response.choices[0].message.content
                if not content or not str(content).strip():
                    raise LLMError("模型返回了空内容", kind="bad_response")
                return str(content)
            except Exception as exc:  # noqa: BLE001 - normalised below
                error = self._classify(exc)
                last_error = error
                if not error.retryable or attempt >= self.max_retries:
                    raise error from exc
                delay = min(0.5 * (2**attempt), 4.0) + random.uniform(0, 0.2)
                logger.warning(
                    "LLM call failed (attempt %s/%s): %s; retrying in %.1fs",
                    attempt + 1,
                    self.max_retries + 1,
                    error,
                    delay,
                )
                self._sleep(delay)

        raise last_error or LLMError("模型调用失败", kind="api")

    def judge_spoiler(
        self,
        comment: str,
        current_paragraph: str,
        future_paragraphs: list[str],
        no_context: bool = False,
    ) -> dict:
        prompt = self.build_prompt(comment, current_paragraph, future_paragraphs, no_context)
        raw = self._chat(prompt)
        return parse_judgement(raw)
