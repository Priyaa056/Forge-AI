"""Dashboard analytics for one user: build totals, success rate, build time, tests and a daily series.

Computed from the stored runs (``run.json``) of the user's projects; nothing new is stored.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.services.project_store import ProjectNotFound, ProjectStore

STAGES = ["pm", "ui", "backend", "db", "auth", "qa", "deploy"]


def _day(iso: Optional[str]) -> Optional[date]:
    if not iso:
        return None
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).date()


def _pct(part: int, whole: int) -> Optional[float]:
    return round(100.0 * part / whole, 1) if whole else None


def _change(now: float, before: float) -> Optional[float]:
    """Percentage change; None when there is nothing to compare with (no builds the week before)."""
    if before == 0:
        return None
    return round(100.0 * (now - before) / before, 1)


def user_stats(store: ProjectStore, owner_id: str, days: int = 14, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    daily = {start + timedelta(days=i): {"builds": 0, "succeeded": 0, "failed": 0, "durations": [], "tests_passed": 0}
             for i in range(days)}
    projects = store.list_projects(owner_id=owner_id)
    totals = {"builds": 0, "succeeded": 0, "failed": 0, "running": 0, "refinements": 0, "tests_passed": 0, "tests_run": 0}
    durations: List[float] = []
    agent_times: Dict[str, List[float]] = {s: [] for s in STAGES}
    last7 = {"builds": 0, "succeeded": 0, "finished": 0}
    prev7 = {"builds": 0, "succeeded": 0, "finished": 0}
    for project in projects:
        try:
            data = store.load_project(project["project_id"])
        except ProjectNotFound:
            continue
        for run_id in data.get("runs", []):
            try:
                run = store.load_run(project["project_id"], run_id)
            except (ProjectNotFound, OSError, ValueError):
                continue
            status = run.get("execution_status")
            summary = run.get("summary") or {}
            totals["builds"] += 1
            if (run.get("options") or {}).get("mode") == "refine":
                totals["refinements"] += 1
            qa = summary.get("qa_summary") or {}
            if status == "COMPLETED":
                totals["succeeded"] += 1
                if summary.get("total_duration_ms"):
                    durations.append(float(summary["total_duration_ms"]))
                totals["tests_passed"] += int(qa.get("tests_passed") or 0)
                totals["tests_run"] += int(qa.get("tests_run") or 0)
                for stage, info in (summary.get("agents") or {}).items():
                    if stage in agent_times and (info or {}).get("duration_ms") and (info or {}).get("generation_mode") != "reused":
                        agent_times[stage].append(float(info["duration_ms"]))
            elif status == "FAILED":
                totals["failed"] += 1
            elif status in ("RUNNING", "PENDING"):
                totals["running"] += 1
            day = _day(run.get("created_at"))
            if day in daily:
                bucket = daily[day]
                bucket["builds"] += 1
                if status == "COMPLETED":
                    bucket["succeeded"] += 1
                    bucket["tests_passed"] += int(qa.get("tests_passed") or 0)
                    if summary.get("total_duration_ms"):
                        bucket["durations"].append(float(summary["total_duration_ms"]))
                elif status == "FAILED":
                    bucket["failed"] += 1
            if day is not None:
                window = last7 if day > today - timedelta(days=7) else (prev7 if day > today - timedelta(days=14) else None)
                if window is not None:
                    window["builds"] += 1
                    if status in ("COMPLETED", "FAILED"):
                        window["finished"] += 1
                        window["succeeded"] += 1 if status == "COMPLETED" else 0

    finished = totals["succeeded"] + totals["failed"]
    series = []
    for day, bucket in daily.items():
        done = bucket["succeeded"] + bucket["failed"]
        series.append({
            "date": day.isoformat(), "builds": bucket["builds"], "succeeded": bucket["succeeded"], "failed": bucket["failed"],
            "success_rate": _pct(bucket["succeeded"], done),
            "avg_build_ms": round(sum(bucket["durations"]) / len(bucket["durations"]), 1) if bucket["durations"] else None,
            "tests_passed": bucket["tests_passed"],
        })
    return {
        "days": days,
        "projects": len(projects),
        "live_apps": sum(1 for p in projects if p.get("current_version")),
        "builds": totals["builds"],
        "succeeded": totals["succeeded"],
        "failed": totals["failed"],
        "running": totals["running"],
        "refinements": totals["refinements"],
        "success_rate": _pct(totals["succeeded"], finished),
        "avg_build_ms": round(sum(durations) / len(durations), 1) if durations else None,
        "tests_passed": totals["tests_passed"],
        "tests_run": totals["tests_run"],
        "agent_avg_ms": {s: round(sum(v) / len(v), 1) if v else None for s, v in agent_times.items()},
        "builds_change_pct": _change(last7["builds"], prev7["builds"]),
        "success_rate_change": (round((_pct(last7["succeeded"], last7["finished"]) or 0) - (_pct(prev7["succeeded"], prev7["finished"]) or 0), 1)
                                if last7["finished"] and prev7["finished"] else None),
        "daily": series,
    }
