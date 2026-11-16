"""Admin 대시보드: data/ 의 로그 파일을 읽어 조건(User Trigger / AI Decision / Delayed)별로 집계한다."""
from statistics import mean, pstdev

from ..config import TASK_KEYS, annotation_config, survey_config, tasks_config
from ..storage import codes_store, session_store


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
        elif sessions or state.get("task_index", 0) > 0 or state.get("step") not in ("overview", "intro"):
            key = "progress"
        else:
            key = "new"
        counts[key] += 1
        if key == "new" or (only_finished and key != "done"):
            continue
        chosen.append({**c, "sessions": sessions})
    return chosen, counts


def _mode_switches(session: dict) -> tuple[int, int]:
    """세션 안에서 피드백 방식을 바꾼 횟수: (간단 → 자세한, 자세한 → 간단)."""
    modes = [m.get("mode") for m in session.get("mode_history") or [] if m.get("mode")]
    to_detailed = sum(1 for a, b in zip(modes, modes[1:]) if a == "simple" and b == "detailed")
    to_simple = sum(1 for a, b in zip(modes, modes[1:]) if a == "detailed" and b == "simple")
    return to_detailed, to_simple


def _seconds_between(a: str | None, b: str | None) -> float | None:
    from datetime import datetime
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except (TypeError, ValueError):
        return None


def _condition_stats(task: str, sessions: list[tuple[dict, dict]]) -> dict:
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
        "avg_switch_to_detailed": _avg([_mode_switches(s)[0] for _, s in sessions]),
        "avg_switch_to_simple": _avg([_mode_switches(s)[1] for _, s in sessions]),
    }
    if task == "user":
        requested = [t for _, t in users if t.get("requested") or t.get("shown_via") == "request"]
        out["requested_turns"] = len(requested)
        out["request_rate"] = _rate(len(requested), len(users))
        out["avg_requests_per_session"] = _avg([
            sum(1 for t in s.get("turns", []) if t.get("requested") or t.get("shown_via") == "request") for _, s in sessions])
        out["requested_with_issue_rate"] = _rate(sum(1 for t in requested if (t.get("feedback") or {}).get("has_issue")), len(requested))
        # 발화가 화면에 나온 뒤 피드백 보기를 누르기까지 걸린 시간
        out["avg_request_delay_s"] = _avg([_seconds_between(t.get("ts"), t.get("requested_at")) for t in requested if t.get("requested_at")])
        unrequested = [t for _, t in users if not (t.get("requested") or t.get("shown_via") == "request") and t.get("feedback")]
        out["unrequested_with_issue_rate"] = _rate(sum(1 for t in unrequested if t["feedback"].get("has_issue")), len(unrequested))
        out["unrequested_turns"] = len(unrequested)
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
            n = max((q["n"] for q in qs), default=0)
            # AI Decision 의 '못 봤음'은 세션이 끝난 뒤 피드백이 늦게 만들어진 경우에만 생겨서, 응답이 있을 때만 보여준다
            if task == "ai" and state == "unseen" and not n:
                continue
            label = conf["labels"].get(state, conf["states"].get(state, state))
            groups.append({"state": state, "state_label": label.get(task, "") if isinstance(label, dict) else label, "questions": qs, "n": n})
        out[task] = groups
    return out


SCORE_GROUPS = {
    "user": [("requested", "피드백 보기를 누른 발화"), ("not_requested", "누르지 않은 발화 (세션 후 생성)")],
    "ai": [("shown", "피드백이 제시된 발화"), ("not_shown", "제시되지 않은 발화")],
    "delayed": [("all", "전체 발화")],
}


def score_group(task: str, t: dict) -> str:
    """점수 분포를 나눠 볼 때 이 발화가 속하는 묶음."""
    if task == "user":
        return "requested" if (t.get("requested") or t.get("shown_via") == "request") else "not_requested"
    if task == "ai":
        return "shown" if t.get("shown") else "not_shown"
    return "all"


def _score_dist(task_sessions: dict[str, list]) -> dict:
    """발화별 L1(의미 미전달) · L2(부자연스러움) · 시급성 점수 분포 (1~10, 높을수록 피드백이 필요한 쪽). 기록만 하고 피드백 결정에는 쓰지 않는다.
    전체 분포 + 조건별로 묶음을 나눈 분포 (User Trigger: 누름/안 누름, AI Decision: 제시/미제시, Delayed: 전체)."""
    keys = ("l1", "l2", "urgency")
    by_condition, groups = {}, {}
    for task, sessions in task_sessions.items():
        dist = {k: [0] * 10 for k in keys}
        gdist = {g: {k: [0] * 10 for k in keys} for g, _ in SCORE_GROUPS[task]}
        for _, s in sessions:
            for t in s.get("turns", []):
                if t.get("role") != "user":
                    continue
                sc = (t.get("feedback") or {}).get("scores") or {}
                g = score_group(task, t)
                for k in keys:
                    v = sc.get(k)
                    if isinstance(v, int) and 1 <= v <= 10:
                        dist[k][v - 1] += 1
                        gdist[g][k][v - 1] += 1
        by_condition[task] = dist
        groups[task] = [{"key": g, "label": label, "dist": gdist[g]} for g, label in SCORE_GROUPS[task]]
    total = {k: [sum(by_condition[t][k][i] for t in by_condition) for i in range(10)] for k in keys}
    return {"by_condition": by_condition, "groups": groups, "all": total}


def _agreement(task_sessions: dict[str, list]) -> dict:
    """AI Decision: AI가 보여줄지 정한 판단 vs 학습자가 Annotation 에서 답한 필요성.
    보여준 발화 → '이 시점에 피드백이 필요했다/필요 없었다', 안 보여준 발화 → '이 발화에 피드백이 있어야 했다/없어도 괜찮았다'."""
    m = {"shown": [0, 0], "not_shown": [0, 0]}
    for _, s in task_sessions.get("ai", []):
        for a in (s.get("annotation") or {}).get("answers", []):
            v = a.get("value")
            if not isinstance(v, int) or v not in (0, 1):
                continue
            if a.get("feedback_state") == "seen" and a.get("key") == "need":
                m["shown"][v] += 1
            elif a.get("feedback_state") == "no_feedback" and a.get("key") == "should_have":
                m["not_shown"][v] += 1
    total = sum(m["shown"]) + sum(m["not_shown"])
    agree = m["shown"][0] + m["not_shown"][1]
    return {"matrix": m, "n": total, "agree": agree, "agree_rate": _rate(agree, total)}


def build(only_finished: bool = False) -> dict:
    participants, counts = _participants(only_finished)
    task_sessions: dict[str, list] = {k: [] for k in TASK_KEYS}
    order_pos: dict[str, list[int]] = {k: [] for k in TASK_KEYS}
    for p in participants:
        for task, s in p["sessions"].items():
            task_sessions[task].append((p, s))
            if task in p.get("order", []):
                order_pos[task].append(p["order"].index(task) + 1)

    tasks = tasks_config()
    return {
        "only_finished": only_finished,
        "participants": counts,
        "included": len(participants),
        "conditions": [
            {"key": k, "name": tasks[k]["name"], "summary": tasks[k]["summary"],
             "order_counts": [order_pos[k].count(i) for i in (1, 2, 3)],
             **_condition_stats(k, task_sessions[k])}
            for k in TASK_KEYS
        ],
        "likert": _likert(task_sessions),
        "annotation": _annotation(task_sessions),
        "scores": _score_dist(task_sessions),
        "agreement": _agreement(task_sessions),
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
    for task, groups in data["scores"]["groups"].items():
        for g in groups:
            for crit in ("l1", "l2", "urgency"):
                for i, n in enumerate(g["dist"][crit]):
                    rows.append({"section": "score_distribution_group", "condition": tasks[task]["name"], "metric": f"{g['key']}.{crit}={i + 1}", "value": n})
    ag = data["agreement"]
    for k, (a, b) in ag["matrix"].items():
        rows.append({"section": "ai_agreement", "condition": tasks["ai"]["name"], "metric": f"{k}.learner_needed", "value": a})
        rows.append({"section": "ai_agreement", "condition": tasks["ai"]["name"], "metric": f"{k}.learner_not_needed", "value": b})
    rows.append({"section": "ai_agreement", "condition": tasks["ai"]["name"], "metric": "agree_rate", "value": ag["agree_rate"]})
    for task, groups in data["annotation"].items():
        for g in groups:
            for q in g["questions"]:
                for label, cnt in zip(q["options"], q["counts"]):
                    rows.append({"section": "annotation", "condition": tasks[task]["name"], "metric": f"{g['state']}.{q['key']}.{label}", "value": cnt})
    return rows
