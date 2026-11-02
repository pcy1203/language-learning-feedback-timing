"""prompts/*.txt 를 읽어 {{변수}} 를 채운다. 매번 새로 읽으므로 파일을 고치면 바로 반영된다."""
from ..config import PROMPTS_DIR


def render(name: str, **variables) -> str:
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text
