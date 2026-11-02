"""API 키 없이 화면·흐름을 점검하기 위한 가짜 응답 (MOCK 모드)."""
import re

_QUESTIONS = [
    "That sounds interesting! Can you tell me more about it?",
    "Oh, I see. How did that make you feel?",
    "Nice! Why do you think it was so memorable?",
    "That's great. What would you like to do differently next time?",
    "Interesting! Could you give me a specific example?",
]

# (찾을 표현, 바꿀 표현, 유형, 설명)
_RULES = [
    (r"\bI go\b", "I went", "meaning", "지난 일을 말하고 있으니 과거형 went를 써야 시점이 분명해져요."),
    (r"\bwe eat\b", "we ate", "meaning", "지난 일이라 과거형 ate로 말해요."),
    (r"\bI eat\b", "I ate", "meaning", "지난 일이라 과거형 ate로 말해요."),
    (r"\bpeoples\b", "people", "meaning", "people은 이미 복수형이에요."),
    (r"\bvery fun\b", "a lot of fun", "expression", "fun은 주로 명사로 쓰여 a lot of와 더 자연스럽게 어울려요."),
    (r"\bvery good\b", "really great", "expression", "very good보다 really great가 감정을 더 생생하게 전해요."),
    (r"\bvery interesting\b", "really fascinating", "expression", "더 구체적인 형용사를 쓰면 느낌이 잘 전달돼요."),
]


def opening(topic_label: str, topic_hint: str) -> str:
    return f"Hi there! Today let's chat about {topic_hint}. To start, could you tell me a little about it?"


def reply(turns: list[dict]) -> str:
    n = sum(1 for t in turns if t.get("role") == "user")
    return _QUESTIONS[(n - 1) % len(_QUESTIONS)]


def feedback(utterance: str) -> dict:
    revised = utterance
    items = []
    for pattern, repl, kind, why in _RULES:
        m = re.search(pattern, revised, re.I)
        if m and len(items) < 3:
            items.append({"type": kind, "original": m.group(0), "revised": repl, "explanation": why})
            revised = re.sub(pattern, repl, revised, count=1, flags=re.I)
    words = utterance.split()
    # 규칙에 안 걸려도 긴 발화는 가끔 표현 피드백을 만든다 (화면 점검용)
    if not items and len(words) >= 8 and len(utterance) % 2 == 0:
        items.append({
            "type": "expression", "original": words[-1], "revised": words[-1].rstrip(".!?") + ", actually.",
            "explanation": "(MOCK) 문장 끝에 actually를 붙이면 말투가 더 자연스러워질 수 있어요.",
        })
        revised = " ".join(words[:-1] + [words[-1].rstrip(".!?") + ", actually."])
    has_issue = bool(items)
    severity = 0 if not has_issue else (2 if any(i["type"] == "meaning" for i in items) else 1)
    if revised and revised[-1] not in ".!?":
        revised += "."
    return {
        "intended_meaning": f"(MOCK) 참가자가 말하려던 내용: {utterance[:60]}",
        "has_issue": has_issue,
        "severity": severity,
        "revised": revised[:1].upper() + revised[1:] if revised else revised,
        "items": items,
    }


def summary(feedback_turns: list[dict]) -> dict:
    meaning = sum(1 for t in feedback_turns for i in t["feedback"]["items"] if i["type"] == "meaning")
    expression = sum(1 for t in feedback_turns for i in t["feedback"]["items"] if i["type"] == "expression")
    patterns = [p for p in [{"label": "의미 전달", "count": meaning}, {"label": "더 자연스러운 표현", "count": expression}] if p["count"]]
    patterns.sort(key=lambda p: -p["count"])
    return {"patterns": patterns, "overview": "(MOCK) 전체적으로 하고 싶은 말을 잘 전달했어요. 지난 일을 말할 때 과거형을 쓰는 연습을 해 보세요."}
