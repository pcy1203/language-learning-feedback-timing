"""API 키 없이 화면·흐름을 점검하기 위한 가짜 응답 (MOCK 모드).

대화 AI(Gemini) 키가 없으면 대화만, 피드백(OpenAI) 키가 없으면 피드백만 가짜로 동작한다.
"""
import re

_QUESTIONS = [
    "That sounds interesting! Can you tell me more about it?",
    "Oh, I see. How did that make you feel?",
    "Nice! Why do you think it was so memorable?",
    "That's great. What would you like to do differently next time?",
    "Interesting! Could you give me a specific example?",
]

# (찾을 표현, 바꿀 표현, 유형, 분류, 설명)
_RULES = [
    (r"\bI go\b", "I went", "meaning", "grammar", "지난 일을 말하고 있으니 과거형 went를 써야 시점이 분명해져요."),
    (r"\bwe eat\b", "we ate", "meaning", "grammar", "지난 일이라 과거형 ate로 말해요."),
    (r"\bI eat\b", "I ate", "meaning", "grammar", "지난 일이라 과거형 ate로 말해요."),
    (r"\bpeoples\b", "people", "meaning", "grammar", "people은 이미 복수형이에요."),
    (r"\bI'm boring\b", "I'm bored", "meaning", "vocabulary", "boring은 '지루하게 만드는'이라는 뜻이라, 내가 지루할 때는 bored를 써요."),
    (r"\bvery fun\b", "a lot of fun", "expression", "vocabulary", "fun은 주로 명사로 쓰여 a lot of와 더 자연스럽게 어울려요."),
    (r"\bvery good\b", "really great", "expression", "vocabulary", "very good보다 really great가 감정을 더 생생하게 전해요."),
    (r"\bvery interesting\b", "really fascinating", "expression", "vocabulary", "더 구체적인 형용사를 쓰면 느낌이 잘 전달돼요."),
]


def opening(topic_label: str, topic_hint: str) -> str:
    return f"Hi there! Today let's chat about {topic_hint}. To start, could you tell me a little about it?"


def reply(turns: list[dict]) -> str:
    n = sum(1 for t in turns if t.get("role") == "user")
    return _QUESTIONS[(n - 1) % len(_QUESTIONS)]


def _split(utterance: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\s+(?:and then|but)\s+", utterance) if p.strip()]
    return parts or [utterance.strip()]


def _sentence(original: str) -> dict:
    revised = original
    items = []
    for pattern, repl, kind, cat, why in _RULES:
        m = re.search(pattern, revised, re.I)
        if m and len(items) < 3:
            items.append({"type": kind, "category": cat, "original": m.group(0), "revised": repl, "explanation": why})
            revised = re.sub(pattern, repl, revised, count=1, flags=re.I)
    meaning = any(i["type"] == "meaning" for i in items)
    expression = any(i["type"] == "expression" for i in items)
    revised = revised[:1].upper() + revised[1:]
    if revised and revised[-1] not in ".!?":
        revised += "."
    return {
        "original": original,
        "l1": {
            "literal_ko": f"(MOCK 직역) {original[:40]}",
            "other_interpretation": False,
            "needs_effort": meaning,
            "intended_ko": f"(MOCK 의도) {original[:40]}",
            "same_meaning": True,
            "score": 6 if meaning else 2,
            "reason_ko": "(MOCK) 규칙 기반 점수",
        },
        "l2": {
            "minimal_revision": revised,
            "natural_revision": revised,
            "score": 6 if expression else (3 if meaning else 2),
            "reason_ko": "(MOCK) 규칙 기반 점수",
        },
        "revised": revised,
        "items": items,
    }


def feedback_raw(utterance: str) -> dict:
    """feedback_turn.txt 의 출력 형식과 같은 모양의 가짜 채점 결과."""
    return {"sentences": [_sentence(s) for s in _split(utterance)]}


def summary(feedback_turns: list[dict]) -> dict:
    meaning = sum(1 for t in feedback_turns for i in t["feedback"]["items"] if i["type"] == "meaning")
    expression = sum(1 for t in feedback_turns for i in t["feedback"]["items"] if i["type"] == "expression")
    patterns = [p for p in [{"label": "의미 전달", "count": meaning}, {"label": "더 자연스러운 표현", "count": expression}] if p["count"]]
    patterns.sort(key=lambda p: -p["count"])
    return {"patterns": patterns, "overview": "(MOCK) 전체적으로 하고 싶은 말을 잘 전달했어요. 지난 일을 말할 때 과거형을 쓰는 연습을 해 보세요."}
