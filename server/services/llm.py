"""OpenAI 호출 래퍼: 피드백·점수·Delayed 요약 (Responses API, JSON 출력, 재시도)."""
import asyncio
import json
import re

from openai import AsyncOpenAI

from ..config import settings

_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


async def generate_json(prompt: str, *, model: str | None = None, effort: str | None = None, retries: int = 2) -> dict:
    """프롬프트 하나를 보내 JSON 객체를 받는다.

    GPT-5 계열은 temperature 대신 reasoning.effort 로 추론 강도를 조절한다 (.env FEEDBACK_REASONING_EFFORT).
    """
    kwargs: dict = {
        "model": model or settings.feedback_model,
        "input": [{"role": "user", "content": prompt}],
        "text": {"format": {"type": "json_object"}},
    }
    effort = settings.feedback_reasoning_effort if effort is None else effort
    if effort:
        kwargs["reasoning"] = {"effort": effort}
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client().responses.create(**kwargs)
            return parse_json((resp.output_text or "").strip())
        except Exception as e:  # 네트워크 오류, 속도 제한, JSON 깨짐 등
            last_error = e
            # 모델이 reasoning 옵션을 지원하지 않으면 빼고 다시 시도
            if "reasoning" in str(e).lower() and "reasoning" in kwargs:
                kwargs.pop("reasoning")
                continue
            await asyncio.sleep(0.8 * (attempt + 1))
    raise last_error  # type: ignore[misc]


async def ping() -> str:
    """연결 확인용 아주 짧은 호출. 모델마다 지원하는 추론 강도가 달라 none → minimal → 기본값 순으로 시도한다."""
    kwargs: dict = {"model": settings.feedback_model, "input": "Reply with the single word: ok", "max_output_tokens": 256}
    last: Exception | None = None
    for effort in ("none", "minimal", None):
        try:
            extra = {"reasoning": {"effort": effort}} if effort else {}
            resp = await client().responses.create(**kwargs, **extra)
            return (resp.output_text or "").strip() or "(응답 받음)"
        except Exception as e:
            last = e
            if "reasoning" not in str(e).lower() and "effort" not in str(e).lower():
                raise
    raise last  # type: ignore[misc]
