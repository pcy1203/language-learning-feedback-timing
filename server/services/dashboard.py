"""Admin 대시보드: data/ 의 로그 파일을 읽어 조건(User Trigger / AI Decision / Delayed)별로 집계한다."""
from statistics import mean, pstdev

from ..config import TASK_KEYS, annotation_config, survey_config, tasks_config
from ..storage import codes_store, session_store
from ..storage.event_logger import read_events


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(mean(xs), 2) if xs else None


def _rate(a, b):
    return round(a / b, 3) if b else None


def _participants(only_finished: bool) -> tuple[list[dict], dict]:
    codes = codes_store.list_codes()
    counts = {"total": len(codes), "done": 0, "progress": 0, "new": 0}
    chosen = []
    for c in codes:
        state = session_store.load_state(c["code"])
        sessions = session_store.all_sessions(c["code"])
        if state.get("finished"):
            key = "done"
        elif sessions or state.get("task_index", 0) > 0 or state.get("step") != "intro":
            key = "progress"
        else:
            key = "new"
        counts[key] += 1
        if key == "new" or (only_finished and key != "done"):
            continue
        chosen.append({**c, "sessions": sessions})
    return chosen, counts


def _condition_stats(task: str, sessions: list[tuple[dict, dict]], toggles: dict) -> dict:
    users = [(s, t) for p, s in sessions for t in s.get("turns", []) if t["role"] == "user"]
    with_fb = [(s, t) for s, t in users if t.get("feedback")]
    issues = [(s, t) for s, t in with_fb if t["feedback"].get("has_issue")]
    shown_live = [(s, t) for s, t in issues if t.get("shown") and t.get("shown_via") in ("request", "ai")]
    ended = [s for _, s in sessions if s.get("ended_at")]
    per_session_turns = [sum(1 for t in s.get("turns", []) if t["role"] == "user") for _, s in sessions]
    start_modes = [((s.get("mode_history") or [{}])[0].get("mode") or s.get("mode")) for _, s in sessions]

    out = {
        "sessions": len(sessions),
        "ended": len(ended),
        "avg_user_turns": _avg(per_session_turns),
        "avg_duration_s": _avg([t.get("duration_s") for _, t in users]),
        "avg_elapsed_s": _avg([s.get("elapsed_s") for s in ended]),
        "user_turns": len(users),
        "issue_turns": len(issues),
        "issue_rate": _rate(len(issues), len(with_fb)),
        "shown_live": len(shown_live),
        "shown_live_rate": _rate(len(shown_live), len(issues)),
        "feedback_generated": len(with_fb),
        "avg_l1": _avg([(t["feedback"].get("scores") or {}).get("l1") for _, t in with_fb]),
        "avg_l2": _avg([(t["feedback"].get("scores") or {}).get("l2") for _, t in with_fb]),
        "avg_urgency": _avg([(t["feedback"].get("scores") or {}).get("urgency") for _, t in with_fb]),
        "avg_latency_ms": _avg([t.get("feedback_latency_ms") for _, t in with_fb]),
        "detailed_start_rate": _rate(sum(1 for m in start_modes if m == "detailed"), len(start_modes)),
        "avg_mode_toggles": _avg([toggles.get((s.get("code"), task), 0) for _, s in sessions]),
    }
    if task == "user":
        requested = [t for _, t in users if t.get("requested") or t.get("shown_via") == "request"]
        out["requested_turns"] = len(requested)
        out["request_rate"] = _rate(len(requested), len(users))
        out["avg_requests_per_session"] = _avg([
            sum(1 for t in s.get("turns", []) if t.get("requested") or t.get("shown_via") == "request") for _, s in sessions])
        out["requested_with_issue_rate"] = _rate(sum(1 for t in requested if (t.get("feedback") or {}).get("has_issue")), len(requested))
    if task == "ai":
        decisions = [t["intervention"] for _, t in users if t.get("intervention")]
        out["ai_show_rate"] = _rate(sum(1 for d in decisions if d.get("show")), len(users))
    return out


def _likert(task_sessions: dict[str, list]) -> dict:
    conf = survey_config()
    scale = conf["likert"]["scale"]
    items = conf["likert"]["items"]
    by = {}
    for task, sessions in task_sessions.items():
        by[task] = {}
        for it in items:
            vals = [s["survey"]["likert"].get(it["key"]) for _, s in sessions if s.get("survey")]
            vals = [v for v in vals if isinstance(v, int)]
            dist = [sum(1 for v in vals if v == k) for k in range(1, scale + 1)]
            by[task][it["key"]] = {
                "n": len(vals),
                "mean": round(mean(vals), 2) if vals else None,
                "sd": round(pstdev(vals), 2) if len(vals) > 1 else None,
                "dist": dist,
            }
    return {"scale": scale, "low_label": conf["likert"]["low_label"], "high_label": conf["likert"]["high_label"], "items": items, "by_condition": by}


def _annotation(task_sessions: dict[str, list]) -> dict:
    conf = annotation_config()
    out = {}
    for task, sessions in task_sessions.items():
        counts: dict[tuple[str, str], list[int]] = {}
        for _, s in sessions:
            for a in (s.get("annotation") or {}).get("answers", []):
                key = (a.get("feedback_state") or "unknown", a.get("key"))
                q = conf["questions"].get(a.get("key"))
                if not q:
                    continue
                counts.setdefault(key, [0] * len(q["options"]))
                v = a.get("value")
                if isinstance(v, int) and 0 <= v < len(q["options"]):
                    counts[key][v] += 1
        groups = []
        for state, keys in conf["rules"].get(task, {}).items():
            qs = []
            for k in keys:
                q = conf["questions"][k]
                c = counts.get((state, k), [0] * len(q["options"]))
                qs.append({"key": k, "label": q["label"], "options": q["options"], "counts": c, "n": sum(c)})
            groups.append({"state": state, "state_label": conf["states"].get(state, state), "questions": qs, "n": max((q["n"] for q in qs), default=0)})
        out[task] = groups
    return out


def _score_dist(task_sessions: dict[str, list]) -> dict:
    """발화별 L1(의미) · L2(자연스러움) · 시급성 점수 분포 (1~10). 기록만 하고 피드백 결정에는 쓰지 않는다."""
    keys = ("l1", "l2", "urgency")
    out = {}
    for task, sessions in task_sessions.items():
        dist = {k: [0] * 10 for k in keys}
        for _, s in sessions:
            for t in s.get("turns", []):
                sc = (t.get("feedback") or {}).get("scores") or {}
                for k in keys:
                    v = sc.get(k)
                    if isinstance(v, int) and 1 <= v <= 10:
                        dist[k][v - 1] += 1
        out[task] = dist
    total = {k: [sum(out[t][k][i] for t in out) for i in range(10)] for k in keys}
    return {"by_condition": out, "all": total}


def build(only_finished: bool = False) -> dict:
    participants, counts = _participants(only_finished)
    task_sessions: dict[str, list] = {k: [] for k in TASK_KEYS}
    toggles: dict[tuple[str, str], int] = {}
    order_pos: dict[str, list[int]] = {k: [] for k in TASK_KEYS}
    for p in participants:
        for task, s in p["sessions"].items():
            task_sessions[task].append((p, s))
            if task in p.get("order", []):
                order_pos[task].append(p["order"].index(task) + 1)
        for e in read_events(p["code"]):
            if e.get("event") == "mode_toggle" and e.get("task"):
                key = (p["code"], e["task"])
                toggles[key] = toggles.get(key, 0) + 1

    tasks = tasks_config()
    return {
        "only_finished": only_finished,
        "participants": counts,
        "included": len(participants),
        "conditions": [
            {"key": k, "name": tasks[k]["name"], "summary": tasks[k]["summary"],
             "order_counts": [order_pos[k].count(i) for i in (1, 2, 3)],
             **_condition_stats(k, task_sessions[k], toggles)}
            for k in TASK_KEYS
        ],
        "likert": _likert(task_sessions),
        "annotation": _annotation(task_sessions),
        "scores": _score_dist(task_sessions),
    }


def summary_rows(data: dict) -> list[dict]:
    """대시보드 수치를 CSV 한 줄씩으로 (section, condition, metric, value)."""
    rows = []
    for c in data["conditions"]:
        for k, v in c.items():
            if k in ("key", "name", "summary"):
                continue
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    rows.append({"section": "condition", "condition": c["name"], "metric": f"{k}.{k2}", "value": v2 if not isinstance(v2, dict) else str(v2)})
            else:
                rows.append({"section": "condition", "condition": c["name"], "metric": k, "value": v if not isinstance(v, list) else str(v)})
    tasks = tasks_config()
    for task, items in data["likert"]["by_condition"].items():
        for key, st in items.items():
            for m in ("n", "mean", "sd"):
                rows.append({"section": "likert", "condition": tasks[task]["name"], "metric": f"{key}.{m}", "value": st[m]})
            rows.append({"section": "likert", "condition": tasks[task]["name"], "metric": f"{key}.dist", "value": str(st["dist"])})
    for task, dist in data["scores"]["by_condition"].items():
        for crit in ("l1", "l2", "urgency"):
            for i, n in enumerate(dist[crit]):
                rows.append({"section": "score_distribution", "condition": tasks[task]["name"], "metric": f"{crit}={i + 1}", "value": n})
    for task, groups in data["annotation"].items():
        for g in groups:
            for q in g["questions"]:
                for label, cnt in zip(q["options"], q["counts"]):
                    rows.append({"section": "annotation", "condition": tasks[task]["name"], "metric": f"{g['state']}.{q['key']}.{label}", "value": cnt})
    return rows
