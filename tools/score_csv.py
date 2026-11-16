"""learner_sentence.csv 의 발화를 실험과 같은 프롬프트로 처리하고, 결과를 오른쪽 열에 붙여 새 CSV로 저장한다.

사용법 (프로젝트 폴더에서):
    python tools/score_csv.py learner_sentence.csv
    python tools/score_csv.py learner_sentence.csv --condition ai --column 발화 --topic 여행 --concurrency 4

--condition 으로 어느 조건의 프롬프트를 쓸지 고른다 (기본 user).
    user     prompts/feedback_user_trigger.txt  (학습자가 요청했다고 보고, 두 기준에 해당하면 피드백)
    ai       prompts/feedback_ai_decision.txt   (지금 꼭 필요한지 판단 + 근거)
    delayed  prompts/feedback_delayed_turn.txt

입력 CSV
    - 발화가 들어 있는 열: --column 으로 지정. 지정하지 않으면 sentence / utterance / text / 발화 / 문장 중 먼저 있는 열,
      없으면 첫 번째 열을 쓴다.
    - (선택) 대화 맥락 열: --context-column. 직전 대화를 한 칸에 적어 두면 의도 추정에 쓴다.
    - (선택) 주제: --topic (기본: 일상 대화)

출력 CSV (기본: 입력파일명_scored_{condition}.csv) — 원래 열은 그대로 두고 오른쪽에 추가
    l1_meaning, l2_naturalness, urgency   점수 1~10 (기록용, 피드백 결정에는 쓰지 않음)
    needs_feedback                모델이 피드백이 필요하다고 판단했으면 Y
    simple_feedback               고친 발화 (간단한 피드백, 필요 없으면 빈칸)
    detailed_feedback             고친 발화 + 바뀐 부분별 한국어 이유 (자세한 피드백)
    intended_ko                   화자 의도
    rationale / likely_concern    AI Decision 판단 근거 / User Trigger 에서 추정한 학습자의 궁금증
    error                         처리에 실패한 경우 이유

API 키(.env 의 OPENAI_API_KEY)가 없으면 가짜 응답(MOCK)으로 채점된다.
"""
import argparse
import asyncio
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.config import settings  # noqa: E402
from server.services import feedback_agent  # noqa: E402

CANDIDATES = ("sentence", "utterance", "text", "발화", "문장")
TYPE_LABEL = {"meaning": "의미 전달", "expression": "더 나은 표현"}
OUT_COLUMNS = [
    "l1_meaning", "l2_naturalness", "urgency", "needs_feedback",
    "simple_feedback", "detailed_feedback", "intended_ko", "rationale", "likely_concern", "error",
]


def pick_column(header: list[str], wanted: str | None) -> str:
    if wanted:
        if wanted not in header:
            raise SystemExit(f"'{wanted}' 열이 없어요. 있는 열: {header}")
        return wanted
    lower = {h.strip().lower(): h for h in header}
    for c in CANDIDATES:
        if c in lower:
            return lower[c]
    return header[0]


def detailed_text(fb: dict) -> str:
    lines = [fb["revised"]]
    for it in fb["items"]:
        change = f"{it['original']} → {it['revised']}" if it["original"] else it["revised"]
        lines.append(f"- [{TYPE_LABEL.get(it['type'], it['type'])}] {change}: {it['explanation']}")
    return "\n".join(lines)


async def score_row(text: str, context: str, topic: str, condition: str) -> dict:
    ctx = [{"role": "user", "text": context}] if context else []
    fb = await feedback_agent.generate(condition, {"label": topic}, ctx, text)
    sc = fb["scores"]
    return {
        "l1_meaning": sc["l1"], "l2_naturalness": sc["l2"], "urgency": sc["urgency"],
        "needs_feedback": "Y" if fb["has_issue"] else "N",
        "simple_feedback": fb["revised"] if fb["has_issue"] else "",
        "detailed_feedback": detailed_text(fb) if fb["has_issue"] else "",
        "intended_ko": fb["intended_meaning"],
        "rationale": fb.get("rationale", ""), "likely_concern": fb.get("likely_concern", ""),
        "error": "",
    }


async def main() -> None:
    ap = argparse.ArgumentParser(description="학습자 발화 CSV 처리 (점수 + 피드백 필요 여부 + 간단/자세한 피드백)")
    ap.add_argument("csv", help="입력 CSV 경로 (예: learner_sentence.csv)")
    ap.add_argument("--condition", choices=("user", "ai", "delayed"), default="user", help="사용할 조건의 프롬프트 (기본 user)")
    ap.add_argument("--out", help="출력 CSV 경로 (기본: 입력파일명_scored_{condition}.csv)")
    ap.add_argument("--column", help="발화가 들어 있는 열 이름")
    ap.add_argument("--context-column", help="대화 맥락이 들어 있는 열 이름 (선택)")
    ap.add_argument("--topic", default="일상 대화", help="대화 주제 (기본: 일상 대화)")
    ap.add_argument("--concurrency", type=int, default=4, help="동시에 채점할 행 수 (기본 4)")
    args = ap.parse_args()

    src = Path(args.csv)
    out = Path(args.out) if args.out else src.with_name(f"{src.stem}_scored_{args.condition}.csv")
    with open(src, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        rows = list(reader)
    if not header:
        raise SystemExit("CSV 첫 줄(열 이름)을 읽지 못했어요.")
    col = pick_column(header, args.column)
    mode = "MOCK (가짜 응답)" if settings.mock_feedback else settings.feedback_model
    print(f"처리: {src.name} · 발화 열 '{col}' · {len(rows)}행 · 모델 {mode} · 프롬프트 {feedback_agent.PROMPTS[args.condition]}")

    sem = asyncio.Semaphore(max(1, args.concurrency))
    done = 0

    async def work(i: int, row: dict) -> dict:
        nonlocal done
        text = (row.get(col) or "").strip()
        result = {k: "" for k in OUT_COLUMNS}
        if text:
            async with sem:
                try:
                    result = await score_row(text, (row.get(args.context_column) or "").strip() if args.context_column else "", args.topic, args.condition)
                except Exception as e:
                    result["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        done += 1
        print(f"\r  {done}/{len(rows)}", end="", flush=True)
        return {**row, **result}

    results = await asyncio.gather(*(work(i, r) for i, r in enumerate(rows)))
    fields = header + [c for c in OUT_COLUMNS if c not in header]
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)
    errors = sum(1 for r in results if r.get("error"))
    print(f"\n완료 → {out}" + (f" (실패 {errors}행, error 열 확인)" if errors else ""))


if __name__ == "__main__":
    # Windows 콘솔(cp949)에서 출력할 수 없는 문자가 있어도 멈추지 않게
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    asyncio.run(main())
