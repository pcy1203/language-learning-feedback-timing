"""로그를 CSV / ZIP 으로 변환 (Admin 내려받기용).

kind:
  turns        대화 + 피드백 (턴 1개 = 1행)
  events       이벤트 로그 전체
  annotations  Annotation 응답 (질문 1개 = 1행)
  survey       세션별 설문 (Task 1개 = 1행)
"""
import csv
import io
import json
import zipfile

from ..config import DATA_DIR, annotation_config, survey_config, tasks_config, topic_info
from . import codes_store, session_store
from .event_logger import read_events

KINDS = ("turns", "events", "annotations", "survey")


def _csv(fields: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    return buf.getvalue()


def _order_index(participant: dict | None, task: str) -> int | str:
    if participant and task in participant.get("order", []):
        return participant["order"].index(task) + 1
    return ""


def _sessions(code: str, task: str | None) -> dict[str, dict]:
    sessions = session_store.all_sessions(code)
    if task:
        sessions = {k: v for k, v in sessions.items() if k == task}
    return sessions


TURN_FIELDS = [
    "code", "task", "condition", "order_index", "topic", "mode_at_end", "turn_id", "utterance_number", "role", "ts", "text", "duration_s", "input",
    "stt_engine", "stt_raw", "stt_preview", "stt_cleaned", "stt_ms", "recording_file",
    "feedback_status", "feedback_purpose", "feedback_prompt", "feedback_latency_ms", "needs_feedback", "has_issue",
    "l1_meaning_breakdown", "l2_unnaturalness", "urgency", "rationale", "likely_concern",
    "intended_meaning", "revised", "item_count", "items_json", "feedback_state",
    "requested", "requested_at", "request_count",
    "shown", "shown_via", "shown_at", "mode_when_shown", "ai_decision_show",
    "audio_file", "audio_seconds",
]


def _condition(task: str) -> str:
    return tasks_config().get(task, {}).get("name", task)


def turns_rows(code: str, task: str | None = None) -> list[dict]:
    p = codes_store.get(code)
    rows = []
    for tk, s in _sessions(code, task).items():
        for t in s.get("turns", []):
            fb = t.get("feedback") or {}
            iv = t.get("intervention") or {}
            is_user = t.get("role") == "user"
            rows.append({
                "code": code, "task": tk, "condition": _condition(tk), "order_index": _order_index(p, tk),
                "topic": topic_info(s.get("topic", "")).get("label"), "mode_at_end": s.get("mode"),
                "turn_id": t.get("id"), "role": t.get("role"), "ts": t.get("ts"), "text": t.get("text"),
                "duration_s": t.get("duration_s"), "input": t.get("input"),
                "utterance_number": t.get("number"), "stt_engine": t.get("stt_engine"), "stt_raw": t.get("stt_raw"),
                "stt_preview": t.get("stt_preview"), "stt_cleaned": t.get("stt_cleaned"), "stt_ms": t.get("stt_ms"),
                "recording_file": (t.get("recording") or {}).get("name"),
                "feedback_status": t.get("feedback_status"), "feedback_latency_ms": t.get("feedback_latency_ms"),
                "has_issue": fb.get("has_issue") if fb else None,
                "feedback_purpose": t.get("feedback_purpose"), "feedback_prompt": fb.get("prompt"),
                "needs_feedback": fb.get("needs_feedback"),
                "l1_meaning_breakdown": (fb.get("scores") or {}).get("l1"), "l2_unnaturalness": (fb.get("scores") or {}).get("l2"),
                "urgency": (fb.get("scores") or {}).get("urgency"),
                "rationale": fb.get("rationale"), "likely_concern": fb.get("likely_concern"),
                "intended_meaning": fb.get("intended_meaning"), "revised": fb.get("revised"),
                "item_count": len(fb.get("items", [])) if fb else None,
                "items_json": json.dumps(fb.get("items", []), ensure_ascii=False) if fb else None,
                "feedback_state": session_store.feedback_state(tk, t) if is_user else None,
                "requested": bool(t.get("requested")) if is_user and tk == "user" else None,
                "requested_at": t.get("requested_at"), "request_count": t.get("request_count"),
                "shown": t.get("shown") if is_user else None,
                "shown_via": t.get("shown_via"), "shown_at": t.get("shown_at"), "mode_when_shown": t.get("mode_when_shown"),
                "ai_decision_show": iv.get("show") if iv else None,
                "audio_file": (t.get("audio") or {}).get("file"), "audio_seconds": (t.get("audio") or {}).get("seconds"),
            })
    return rows


EVENT_FIELDS = ["ts", "client_ts", "code", "task", "source", "event", "data_json"]


def events_rows(code: str, task: str | None = None) -> list[dict]:
    rows = []
    for e in read_events(code):
        if task and e.get("task") != task:
            continue
        rows.append({**e, "data_json": json.dumps(e.get("data", {}), ensure_ascii=False)})
    return rows


ANNOTATION_FIELDS = ["code", "task", "condition", "order_index", "saved_at", "turn_id", "feedback_state", "question", "question_label", "answer_index", "answer_label", "answered_at"]


def annotation_rows(code: str, task: str | None = None) -> list[dict]:
    p = codes_store.get(code)
    qconf = annotation_config()["questions"]
    rows = []
    for tk, s in _sessions(code, task).items():
        ann = s.get("annotation") or {}
        for a in ann.get("answers", []):
            q = qconf.get(a.get("key"), {})
            rows.append({
                "code": code, "task": tk, "condition": _condition(tk), "order_index": _order_index(p, tk), "saved_at": ann.get("saved_at"),
                "turn_id": a.get("turn_id"), "feedback_state": a.get("feedback_state"),
                "question": a.get("key"), "question_label": q.get("label"),
                "answer_index": a.get("value"), "answer_label": a.get("label"), "answered_at": a.get("answered_at"),
            })
    return rows


def survey_fields() -> list[str]:
    conf = survey_config()
    likert = [f"likert_{i['key']}" for i in conf["likert"]["items"]]
    texts = [f"text_{f['key']}" for f in conf["free_text"]]
    return ["code", "task", "condition", "order_index", "submitted_at", *likert, *texts]


def survey_rows(code: str, task: str | None = None) -> list[dict]:
    p = codes_store.get(code)
    rows = []
    for tk, s in _sessions(code, task).items():
        sv = s.get("survey")
        if not sv:
            continue
        row = {"code": code, "task": tk, "condition": _condition(tk), "order_index": _order_index(p, tk), "submitted_at": sv.get("submitted_at")}
        for k, v in (sv.get("likert") or {}).items():
            row[f"likert_{k}"] = v
        for k, v in (sv.get("text") or {}).items():
            row[f"text_{k}"] = v
        rows.append(row)
    return rows


def build_csv(kind: str, code: str, task: str | None = None) -> str:
    if kind == "turns":
        return _csv(TURN_FIELDS, turns_rows(code, task))
    if kind == "events":
        return _csv(EVENT_FIELDS, events_rows(code, task))
    if kind == "annotations":
        return _csv(ANNOTATION_FIELDS, annotation_rows(code, task))
    if kind == "survey":
        return _csv(survey_fields(), survey_rows(code, task))
    raise ValueError(kind)


def all_codes_with_logs() -> list[str]:
    codes = {c["code"] for c in codes_store.list_codes()}
    logs_dir = DATA_DIR / "logs"
    if logs_dir.exists():
        codes |= {d.name for d in logs_dir.iterdir() if d.is_dir()}
    return sorted(codes)


def build_csv_all(kind: str) -> str:
    fields = {"turns": TURN_FIELDS, "events": EVENT_FIELDS, "annotations": ANNOTATION_FIELDS}.get(kind) or survey_fields()
    getter = {"turns": turns_rows, "events": events_rows, "annotations": annotation_rows, "survey": survey_rows}[kind]
    rows = []
    for code in all_codes_with_logs():
        rows.extend(getter(code))
    return _csv(fields, rows)


def build_zip(code: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for kind in KINDS:
            z.writestr(f"{code}_{kind}.csv", "﻿" + build_csv(kind, code))
        pdir = DATA_DIR / "logs" / code
        if pdir.exists():
            for f in sorted(pdir.iterdir()):
                if f.is_file() and f.suffix in (".json", ".jsonl"):
                    z.write(f, arcname=f"raw/{f.name}")
        rdir = DATA_DIR / "recordings" / code
        if rdir.exists():
            for f in sorted(rdir.rglob("*")):
                if f.is_file():
                    z.write(f, arcname=f"recordings/{f.relative_to(rdir).as_posix()}")
    return buf.getvalue()
