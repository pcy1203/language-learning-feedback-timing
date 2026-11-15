"""learner_sentence.csv 의 발화를 실험과 똑같은 로직으로 채점하고, 결과를 오른쪽 열에 붙여 새 CSV로 저장한다.

사용법 (프로젝트 폴더에서):
    python tools/score_csv.py learner_sentence.csv
    python tools/score_csv.py learner_sentence.csv --column 발화 --topic 여행 --concurrency 4

입력 CSV
    - 발화가 들어 있는 열: --column 으로 지정. 지정하지 않으면 sentence / utterance / text / 발화 / 문장 중 먼저 있는 열,
      없으면 첫 번째 열을 쓴다.
    - (선택) 대화 맥락 열: --context-column. 직전 대화를 한 칸에 적어 두면 의도 추정에 쓴다.
    - (선택) 주제: --topic (기본: 일상 대화)

출력 CSV (기본: 입력파일명_scored.csv) — 원래 열은 그대로 두고 오른쪽에 추가
    l1_score, l2_score            발화 안 문장들 중 가장 높은 점수
    feedback_shown                기준값(config/settings.json → feedback_threshold) 이상인 문장이 있으면 Y
    l1_scores, l2_scores          문장별 점수 (| 로 구분)
    simple_feedback               점수와 상관없이 모든 문장을 고친 문장 (간단한 피드백)
    detailed_feedback             고친 문장 + 바뀐 부분별 한국어 이유 (자세한 피드백)
    intended_ko, literal_ko       화자 의도 번역 / 청자 직역
    sentences_json                문장별 채점 근거 전체
    error                         채점에 실패한 경우 이유

API 키(.env 의 OPENAI_API_KEY)가 없으면 가짜 응답(MOCK)으로 채점된다.
"""
import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.config import settings, thresholds  # noqa: E402
from server.services import feedback_agent  # noqa: E402

CANDIDATES = ("sentence", "utterance", "text", "발화", "문장")
TYPE_LABEL = {"meaning": "의미 전달", "expression": "더 나은 표현"}
OUT_COLUMNS = [
    "l1_score", "l2_score", "feedback_shown", "l1_scores", "l2_scores",
    "simple_feedback", "detailed_feedback", "intended_ko", "literal_ko", "sentences_json", "error",
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
    lines = [fb["revised_all"]]
    for it in fb["items_all"]:
        change = f"{it['original']} → {it['revised']}" if it["original"] else it["revised"]
        lines.append(f"- [{TYPE_LABEL.get(it['type'], it['type'])}] {change}: {it['explanation']}")
    return "\n".join(lines)


async def score_row(text: str, context: str, topic: str) -> dict:
    ctx = [{"role": "user", "text": context}] if context else []
    raw = await feedback_agent.score_raw(topic, ctx, text)
    fb = feedback_agent.apply_thresholds(raw, text)
    ss = fb["sentences"]
    return {
        "l1_score": fb["max_l1"],
        "l2_score": fb["max_l2"],
        "feedback_shown": "Y" if fb["has_issue"] else "N",
        "l1_scores": "|".join(str(s["l1"]["score"]) for s in ss),
        "l2_scores": "|".join(str(s["l2"]["score"]) for s in ss),
        "simple_feedback": fb["revised_all"],
        "detailed_feedback": detailed_text(fb),
        "intended_ko": " ".join(s["l1"]["intended_ko"] for s in ss),
        "literal_ko": " ".join(s["l1"]["literal_ko"] for s in ss),
        "sentences_json": json.dumps(ss, ensure_ascii=False),
        "error": "",
    }


async def main() -> None:
    ap = argparse.ArgumentParser(description="학습자 발화 CSV 채점 (L1·L2 점수 + 간단/자세한 피드백)")
    ap.add_argument("csv", help="입력 CSV 경로 (예: learner_sentence.csv)")
    ap.add_argument("--out", help="출력 CSV 경로 (기본: 입력파일명_scored.csv)")
    ap.add_argument("--column", help="발화가 들어 있는 열 이름")
    ap.add_argument("--context-column", help="대화 맥락이 들어 있는 열 이름 (선택)")
    ap.add_argument("--topic", default="일상 대화", help="대화 주제 (기본: 일상 대화)")
    ap.add_argument("--concurrency", type=int, default=4, help="동시에 채점할 행 수 (기본 4)")
    args = ap.parse_args()

    src = Path(args.csv)
    out = Path(args.out) if args.out else src.with_name(f"{src.stem}_scored.csv")
    with open(src, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        rows = list(reader)
    if not header:
        raise SystemExit("CSV 첫 줄(열 이름)을 읽지 못했어요.")
    col = pick_column(header, args.column)
    th = thresholds()
    mode = "MOCK (가짜 응답)" if settings.mock_feedback else settings.feedback_model
    print(f"채점: {src.name} · 발화 열 '{col}' · {len(rows)}행 · 모델 {mode} · 기준 L1≥{th['l1']} 또는 L2≥{th['l2']}")

    sem = asyncio.Semaphore(max(1, args.concurrency))
    done = 0

    async def work(i: int, row: dict) -> dict:
        nonlocal done
        text = (row.get(col) or "").strip()
        result = {k: "" for k in OUT_COLUMNS}
        if text:
            async with sem:
                try:
                    result = await score_row(text, (row.get(args.context_column) or "").strip() if args.context_column else "", args.topic)
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
