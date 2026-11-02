"""OpenAI 호출 래퍼 (재시도, JSON 파싱)."""
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


async def chat(
    messages: list[dict],
    model: str,
    *,
    json_mode: bool = False,
    temperature: float | None = None,
    retries: int = 2,
) -> str:
    kwargs: dict = {"model": model, "messages": messages}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if temperature is not None:
        kwargs["temperature"] = temperature
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client().chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:  # 네트워크 오류, 속도 제한 등
            last_error = e
            # 일부 모델은 temperature 를 지원하지 않는다 → 빼고 다시 시도
            if "temperature" in str(e) and "temperature" in kwargs:
                kwargs.pop("temperature")
                continue
            await asyncio.sleep(0.8 * (attempt + 1))
    raise last_error  # type: ignore[misc]


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


async def chat_json(messages: list[dict], model: str, *, temperature: float | None = None) -> dict:
    text = await chat(messages, model, json_mode=True, temperature=temperature)
    return parse_json(text)
