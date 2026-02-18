from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple


BASE = os.getenv("SIM_TEST_BASE", "http://127.0.0.1:8000").rstrip("/")
ROBOT_ID = os.getenv("SIM_TEST_ROBOT_ID", "SIM-ROBOT-1")
API_KEY = os.getenv("SIM_TEST_API_KEY", "dev-admin-key")
OUT_JSON = os.getenv("SIM_TEST_OUT_JSON", "simulator/mock_test_report.json")
OUT_HTML = os.getenv("SIM_TEST_OUT_HTML", "simulator/mock_test_report.html")


def req(method: str, path: str, params: Dict[str, Any] | None = None, body: Dict[str, Any] | None = None) -> Tuple[int, str]:
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode({k: str(v) for k, v in params.items() if v is not None})
    headers = {"X-API-Key": API_KEY}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        return e.code, raw
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def add(results: List[Dict[str, Any]], name: str, status: int, raw: str) -> None:
    preview = raw.replace("\n", " ")
    if len(preview) > 300:
        preview = preview[:300] + "..."
    results.append({"name": name, "status": status, "preview": preview})


def main() -> int:
    results: List[Dict[str, Any]] = []

    # Preflight
    s, r = req("GET", "/preflight/check", {"verify_vendor": "true"})
    add(results, "GET /preflight/check", s, r)

    # Cleanup running workflows to avoid concurrency conflicts
    s, r = req("GET", "/workflow-engine/runs")
    if s == 200:
        try:
            runs = json.loads(r)
            for run in runs:
                if isinstance(run, dict) and run.get("status") == "RUNNING":
                    req("POST", f"/controls/runs/{run.get('id')}/cancel", params={"reason": "mock-cleanup"})
        except Exception:
            pass

    # Robot state/POIs
    s, r = req("GET", f"/robot-api/robots/{ROBOT_ID}/state")
    add(results, "GET /robot-api/robots/{robot_id}/state", s, r)
    s, r = req("GET", f"/robot-api/robots/{ROBOT_ID}/pois")
    add(results, "GET /robot-api/robots/{robot_id}/pois", s, r)

    poi_id = None
    try:
        pois = json.loads(r)
        if isinstance(pois, list) and pois:
            poi_id = pois[0].get("id")
    except Exception:
        pass

    # POI mapping
    s, r = req("POST", "/poi-mapping/auto-map", body={"robot_id": ROBOT_ID, "table_count": 5, "ref_prefix": ""})
    add(results, "POST /poi-mapping/auto-map", s, r)
    s, r = req("GET", "/poi-mapping/mappings")
    add(results, "GET /poi-mapping/mappings", s, r)

    if poi_id:
        s, r = req(
            "POST",
            "/poi-mapping/mappings",
            body={"kind": "TABLE", "ref": "SMOKE1", "poi_id": poi_id, "area_id": None, "label": "Smoke Table"},
        )
        add(results, "POST /poi-mapping/mappings", s, r)
        s, r = req("DELETE", "/poi-mapping/mappings/TABLE/SMOKE1")
        add(results, "DELETE /poi-mapping/mappings/{kind}/{ref}", s, r)

    # Task manager CRUD
    s, r = req(
        "POST",
        "/task-manager/tasks",
        params={
            "title": "SimDemo",
            "task_type": "NAVIGATE",
            "target_kind": "POI",
            "target_ref": poi_id or "",
        },
    )
    add(results, "POST /task-manager/tasks", s, r)
    task_id = None
    if s in (200, 201):
        try:
            task_id = json.loads(r).get("id")
        except Exception:
            task_id = None

    s, r = req("GET", "/task-manager/tasks")
    add(results, "GET /task-manager/tasks", s, r)

    if task_id:
        s, r = req("PATCH", f"/task-manager/tasks/{task_id}", params={"title": "SimDemo Updated"})
        add(results, "PATCH /task-manager/tasks/{task_id}", s, r)

    # Queue / priority
    s, r = req("POST", "/queue-manager/tick")
    add(results, "POST /queue-manager/tick", s, r)
    s, r = req("GET", "/queue-manager/queue")
    add(results, "GET /queue-manager/queue", s, r)
    s, r = req("GET", "/queue-manager/stats")
    add(results, "GET /queue-manager/stats", s, r)

    # Assignment + orchestrator (mock only)
    s, r = req("POST", "/assignment/assign-next", params={"preferred_robot_id": ROBOT_ID})
    add(results, "POST /assignment/assign-next", s, r)
    s, r = req("POST", "/orchestrator/tick", params={"preferred_robot_id": ROBOT_ID, "max_assignments": 1})
    add(results, "POST /orchestrator/tick", s, r)

    # Workflow
    s, r = req("GET", "/workflow-engine/runs")
    add(results, "GET /workflow-engine/runs", s, r)
    s, r = req("POST", "/workflow-engine/tick")
    add(results, "POST /workflow-engine/tick", s, r)

    # Realtime / dashboard
    s, r = req("GET", "/realtime-bus/health")
    add(results, "GET /realtime-bus/health", s, r)
    s, r = req("GET", "/dashboard/overview")
    add(results, "GET /dashboard/overview", s, r)

    # Save reports
    report = {
        "base": BASE,
        "robot_id": ROBOT_ID,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    rows = "\n".join(
        f"<tr><td>{r['name']}</td><td>{r['status']}</td><td><code>{r['preview']}</code></td></tr>"
        for r in results
    )
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Mock Test Report</title>"
        "<style>body{font-family:Arial,sans-serif;margin:20px}"
        "table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ccc;padding:8px;text-align:left}"
        "code{white-space:pre-wrap}</style></head><body>"
        f"<h2>Mock Test Report</h2><p><b>Base:</b> {BASE}<br>"
        f"<b>Robot:</b> {ROBOT_ID}<br><b>Generated:</b> {report['generated_at']}</p>"
        f"<table><tr><th>Endpoint</th><th>Status</th><th>Preview</th></tr>{rows}</table>"
        "</body></html>"
    )

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print("Saved:", OUT_JSON)
    print("Saved:", OUT_HTML)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
