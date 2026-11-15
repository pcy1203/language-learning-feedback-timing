"""Gemini Live (Live API) 호출: 대화 상대 AI의 다음 말을 만든다.

Live 모델은 음성으로 답하고, 글자는 '출력 음성 받아쓰기(output_audio_transcription)'로 따로 받는다.
발화마다 짧은 세션을 열어 → 지금까지의 대화를 한 번에 보내고(send_client_content) → 답 하나를 받은 뒤 닫는다.
대화 기록은 우리 서버의 세션 파일에 있으므로, 서버를 다시 켜도 대화가 그대로 이어진다.

반환: (받아쓰기 글자, PCM 음성 bytes: 16-bit little-endian, mono, 24kHz)
"""
import asyncio

from google import genai
from google.genai import types

from ..config import settings

SAMPLE_RATE = 24000
_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        # google-genai 3.x 는 기본 API 버전이 v1 인데, Live API(WebSocket)는 v1beta 에만 있어 v1 이면 HTTP 404 가 난다
        _client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(api_version="v1beta"))
    return _client


def _config(system_instruction: str) -> types.LiveConnectConfig:
    cfg: dict = {
        "response_modalities": [types.Modality.AUDIO],
        "system_instruction": system_instruction,
        "output_audio_transcription": types.AudioTranscriptionConfig(),
    }
    if settings.live_voice:
        cfg["speech_config"] = types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=settings.live_voice))
        )
    return types.LiveConnectConfig(**cfg)


async def _respond_once(system_instruction: str, turns: list[tuple[str, str]]) -> tuple[str, bytes]:
    contents = [types.Content(role=role, parts=[types.Part(text=text)]) for role, text in turns]
    audio = bytearray()
    transcript: list[str] = []
    async with client().aio.live.connect(model=settings.chat_model, config=_config(system_instruction)) as session:
        await session.send_client_content(turns=contents, turn_complete=True)
        async for msg in session.receive():
            if msg.data:
                audio.extend(msg.data)
            sc = msg.server_content
            if sc is None:
                continue
            if sc.output_transcription and sc.output_transcription.text:
                transcript.append(sc.output_transcription.text)
            if sc.turn_complete:
                break
    text = " ".join("".join(transcript).split())
    return text, bytes(audio)


async def respond(system_instruction: str, turns: list[tuple[str, str]], timeout: float = 45, retries: int = 1) -> tuple[str, bytes]:
    """turns: [(role, text)] — role 은 'user' 또는 'model'. 마지막은 'user' 여야 모델이 답한다."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            text, audio = await asyncio.wait_for(_respond_once(system_instruction, turns), timeout=timeout)
            if not text and not audio:
                raise RuntimeError("empty response from Gemini Live")
            return text, audio
        except Exception as e:
            last_error = e
            await asyncio.sleep(0.6 * (attempt + 1))
    raise last_error  # type: ignore[misc]


async def ping() -> str:
    text, audio = await respond("Answer in one short sentence.", [("user", "Say: connection ok.")], timeout=30, retries=0)
    return text or f"(audio {len(audio)} bytes)"
