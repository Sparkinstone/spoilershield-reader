#!/usr/bin/env python3
"""One real call against the configured LLM endpoint.

    python scripts/check_llm.py

Use this after changing LLM_* settings: it prints the effective endpoint/model
(never the key) and the classified error if the call fails.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.services.llm import LLMError, LLMService  # noqa: E402

HINTS = {
    "config": "在 .env 里配置 LLM_API_KEY（或 OPENAI_API_KEY / DEEPSEEK_API_KEY）。",
    "auth": "API Key 无效或没有该模型权限，检查 LLM_API_KEY。",
    "model_not_found": "端点不认识这个模型名，检查 LLM_MODEL / LLM_BASE_URL。",
    "connection": "网络不可达：检查 LLM_BASE_URL、代理，或网关证书是否过期。",
    "timeout": "请求超时：调大 LLM_TIMEOUT 或检查网络。",
    "rate_limit": "被限流：稍后再试，或调大 LLM_MAX_RETRIES。",
    "bad_response": "模型没有按 JSON 返回：换模型或检查提示词兼容性。",
}


def main() -> int:
    print(f"model      = {settings.LLM_MODEL}")
    print(f"base_url   = {settings.LLM_BASE_URL}")
    print(f"api_key    = {'set' if settings.llm_configured else 'MISSING'}")
    print(f"ssl_verify = {settings.LLM_SSL_VERIFY}")
    print(f"timeout    = {settings.LLM_TIMEOUT}s (retries={settings.LLM_MAX_RETRIES})")
    print()

    if not settings.llm_configured:
        print("FAILED: 未配置 API Key")
        print("  " + HINTS["config"])
        return 2

    service = LLMService()
    try:
        result = service.judge_spoiler(
            comment="凶手其实就是管家。",
            current_paragraph="两人在客厅里喝茶，聊着天气。",
            future_paragraphs=["侦探最后指出，管家才是真正的凶手。"],
        )
    except LLMError as exc:
        print(f"FAILED: {exc}")
        print("  " + HINTS.get(exc.kind, "查看 app/services/llm.py 中的错误分类。"))
        if not settings.LLM_SSL_VERIFY:
            print("  注意：LLM_SSL_VERIFY=false，已跳过证书校验。")
        return 1

    print("OK: 模型返回可解析的 JSON")
    print(f"  is_spoiler = {result['is_spoiler']}")
    print(f"  confidence = {result['confidence']}")
    print(f"  reason     = {result['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
