from __future__ import annotations

import json
import os
import time
import uuid
import random
import math
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

app = FastAPI(title="AutoXing Mock API")

_DATA_PATH = os.getenv("SIM_DATA_PATH", os.path.join(os.path.dirname(__file__), "data.json"))
_UI_PATH = os.path.join(os.path.dirname(__file__), "ui.html")
_TOKEN_TTL_SECONDS = int(os.getenv("SIM_TOKEN_TTL_SECONDS", "3600"))
_TASK_DONE_SECONDS = float(os.getenv("SIM_TASK_DONE_SECONDS", "3"))
_TASK_NEVER_DONE = os.getenv("SIM_TASK_NEVER_DONE", "0").strip() not in ("", "0", "false", "False")
_FAIL_TOKEN = os.getenv("SIM_FAIL_TOKEN", "0").strip() not in ("", "0", "false", "False")
_FAIL_STATE = os.getenv("SIM_FAIL_STATE", "0").strip() not in ("", "0", "false", "False")
_FAIL_POI = os.getenv("SIM_FAIL_POI", "0").strip() not in ("", "0", "false", "False")
_SIM_RANDOM_MAP = os.getenv("SIM_RANDOM_MAP", "0").strip() not in ("", "0", "false", "False")
_SIM_MAP_SEED = os.getenv("SIM_MAP_SEED", "42")
_SIM_MOVE = os.getenv("SIM_MOVE", "1").strip() not in ("", "0", "false", "False")
_SIM_SPEED = float(os.getenv("SIM_SPEED", "0.6"))
_SIM_TARGET_RADIUS = float(os.getenv("SIM_TARGET_RADIUS", "0.4"))
_SIM_BATTERY_DRAIN = float(os.getenv("SIM_BATTERY_DRAIN", "0.3"))
_SIM_BATTERY_CHARGE = float(os.getenv("SIM_BATTERY_CHARGE", "2.5"))
_SIM_BATTERY_MIN = float(os.getenv("SIM_BATTERY_MIN", "5.0"))
_SIM_BATTERY_LOW = float(os.getenv("SIM_BATTERY_LOW", "10.0"))
_SIM_BATTERY_GOOD = float(os.getenv("SIM_BATTERY_GOOD", "35.0"))
_SIM_IDLE_DRAIN = float(os.getenv("SIM_IDLE_DRAIN", "0.1"))
_SIM_WAIT_MIN = float(os.getenv("SIM_WAIT_MIN", "2.0"))
_SIM_WAIT_MAX = float(os.getenv("SIM_WAIT_MAX", "6.0"))
_SIM_APP_BASE_URL = os.getenv("SIM_APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
_SIM_API_KEY = os.getenv("SIM_API_KEY", "dev-admin-key")
_SIM_RESTART_TABLES = int(os.getenv("SIM_RESTART_TABLES", "12"))
_SIM_RESTART_ARRIVAL_GAP = float(os.getenv("SIM_RESTART_ARRIVAL_GAP", "12"))
_SIM_RESTART_DELIVERY_GAP = float(os.getenv("SIM_RESTART_DELIVERY_GAP", "120"))
_SIM_RESTART_CLEANUP_GAP = float(os.getenv("SIM_RESTART_CLEANUP_GAP", "180"))
_SIM_RESTART_TITLE_PREFIX = os.getenv("SIM_RESTART_TITLE_PREFIX", "SimTask")
_SIM_RESTART_INITIAL_READY = int(os.getenv("SIM_RESTART_INITIAL_READY", "12"))
_SIM_RESTART_MODE = os.getenv("SIM_RESTART_MODE", "restaurant").strip().lower()
_SIM_TRACE = os.getenv("SIM_TRACE", "0").strip() not in ("", "0", "false", "False")
_SIM_TRACE_INTERVAL_S = float(os.getenv("SIM_TRACE_INTERVAL_S", "5.0"))
_SIM_TRACE_PATH = os.getenv(
    "SIM_TRACE_PATH",
    os.path.join(os.path.dirname(__file__), "..", "logs", "sim_trace.log"),
)

TOKENS: Dict[str, float] = {}
TASKS: Dict[str, Dict[str, Any]] = {}
ROBOT_TARGETS: Dict[str, Tuple[float, float]] = {}
LAST_TICK: float = time.time()
TRACE_LAST: Dict[str, float] = {}
TRACE_LAST_FETCH: float = 0.0
TRACE_CACHE: Dict[str, Dict[str, Any]] = {}


def _load_data() -> Dict[str, Any]:
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"robots": {}, "pois": {}}


def _map_pois(map_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    pois: List[Dict[str, Any]] = []
    if not isinstance(map_obj, dict):
        return pois
    charging = map_obj.get("charging")
    if isinstance(charging, dict):
        pois.append(dict(charging))
    rows = map_obj.get("pois") or []
    if isinstance(rows, list):
        pois.extend([dict(p) for p in rows])
    return pois


def _table_refs_from_pois(pois: List[Dict[str, Any]]) -> List[str]:
    refs: List[str] = []
    for p in pois:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or p.get("id") or "")
        kind = str(p.get("kind") or "").upper()
        if kind != "TABLE" and "table" not in name.lower():
            continue
        m = re.search(r"(\d+)", name)
        if m:
            refs.append(m.group(1))
    if not refs:
        return []
    return sorted(refs, key=lambda x: int(re.sub(r"\D", "", x) or 0))


def _generate_map() -> Dict[str, Any]:
    seed = None
    try:
        seed = int(_SIM_MAP_SEED)
    except Exception:
        seed = None
    rnd = random.Random(seed)

    width = 20
    height = 12
    area_id = "sim-area-1"

    def rxy():
        return [round(rnd.uniform(1.0, width - 1.0), 2), round(rnd.uniform(1.0, height - 1.0), 2)]

    charging = {
        "id": "sim-charge-1",
        "name": "Charging Station",
        "areaId": area_id,
        "coordinate": rxy(),
        "yaw": 0,
        "kind": "CHARGING",
    }

    kitchen = {
        "id": "sim-kitchen-1",
        "name": "Kitchen",
        "areaId": area_id,
        "coordinate": rxy(),
        "yaw": 90,
        "kind": "KITCHEN",
    }

    operator = {
        "id": "sim-operator-1",
        "name": "Operator",
        "areaId": area_id,
        "coordinate": rxy(),
        "yaw": 180,
        "kind": "OPERATOR",
    }

    spots = []
    for i in range(1, 13):
        spots.append(
            {
                "id": f"sim-spot-{i}",
                "name": f"Table {i}",
                "areaId": area_id,
                "coordinate": rxy(),
                "yaw": int(rnd.uniform(0, 359)),
                "kind": "TABLE",
            }
        )

    map_obj = {
        "areaId": area_id,
        "width": width,
        "height": height,
        "charging": charging,
        "pois": [kitchen, operator] + spots,
    }

    robots = {
        "SIM-ROBOT-1": {
            "areaId": area_id,
            "battery": 80,
            "isOnline": True,
            "isCharging": False,
            "isEmergencyStop": False,
            "isManualMode": False,
            "moveState": "idle",
            "businessId": "mock-business",
            "buildingId": "mock-building",
            "x": charging["coordinate"][0] + 1.0,
            "y": charging["coordinate"][1] + 1.0,
        },
        "SIM-ROBOT-2": {
            "areaId": area_id,
            "battery": 65,
            "isOnline": True,
            "isCharging": False,
            "isEmergencyStop": False,
            "isManualMode": False,
            "moveState": "idle",
            "businessId": "mock-business",
            "buildingId": "mock-building",
            "x": charging["coordinate"][0] + 2.0,
            "y": charging["coordinate"][1] + 2.0,
        },
    }

    pois_list = _map_pois(map_obj)
    return {
        "map": map_obj,
        "robots": robots,
        "pois": {
            "SIM-ROBOT-1": pois_list,
            "SIM-ROBOT-2": pois_list,
        },
    }


def _normalize_data(data: Dict[str, Any]) -> Dict[str, Any]:
    if "map" not in data or not isinstance(data.get("map"), dict):
        data["map"] = {"areaId": "sim-area-1", "width": 20, "height": 12, "pois": []}

    map_obj = data["map"]
    pois_list = _map_pois(map_obj)

    robots = data.get("robots", {})
    if not isinstance(robots, dict):
        robots = {}
    data["robots"] = robots

    pois = data.get("pois", {})
    if not isinstance(pois, dict):
        pois = {}

    for rid in robots.keys():
        if rid not in pois:
            pois[rid] = pois_list
    data["pois"] = pois
    return data


DATA = _normalize_data(_generate_map() if _SIM_RANDOM_MAP else _load_data())


def _ok(data: Any) -> Dict[str, Any]:
    return {"status": 200, "data": data}


def _err(status: int, msg: str) -> Dict[str, Any]:
    return {"status": status, "msg": msg, "data": None}


def _issue_token() -> str:
    token = uuid.uuid4().hex
    TOKENS[token] = time.time() + _TOKEN_TTL_SECONDS
    return token


def _valid_token(request: Request) -> bool:
    token = request.headers.get("X-Token", "")
    exp = TOKENS.get(token)
    if not exp:
        return False
    if exp < time.time():
        return False
    return True


def _robot_state(robot_id: str) -> Optional[Dict[str, Any]]:
    robots = DATA.get("robots", {})
    state = robots.get(robot_id)
    if not isinstance(state, dict):
        return None
    out = dict(state)
    out["robotId"] = robot_id
    return out


def _robot_pois(robot_id: str) -> List[Dict[str, Any]]:
    pois = DATA.get("pois", {})
    rows = pois.get(robot_id)
    if isinstance(rows, list):
        return [dict(p) for p in rows]
    map_obj = DATA.get("map", {})
    return _map_pois(map_obj)


def _pick_target() -> Tuple[float, float]:
    map_obj = DATA.get("map", {})
    width = float(map_obj.get("width", 20))
    height = float(map_obj.get("height", 12))
    pois = _map_pois(map_obj)
    if pois:
        p = random.choice(pois)
        coord = p.get("coordinate") or [width / 2.0, height / 2.0]
        return float(coord[0]), float(coord[1])
    return random.uniform(1.0, width - 1.0), random.uniform(1.0, height - 1.0)


def _task_done(task: Dict[str, Any]) -> bool:
    if task.get("canceled"):
        return True
    if task.get("done"):
        return True
    return False


def _robot_target_distance(robot_id: Optional[str], target: Any) -> Optional[float]:
    if not robot_id:
        return None
    if not isinstance(target, (list, tuple)) or len(target) < 2:
        return None
    try:
        tx, ty = float(target[0]), float(target[1])
    except Exception:
        return None
    robot = (DATA.get("robots", {}) or {}).get(robot_id)
    if not isinstance(robot, dict):
        return None
    try:
        x = float(robot.get("x", 0.0))
        y = float(robot.get("y", 0.0))
    except Exception:
        return None
    return math.hypot(tx - x, ty - y)


def _task_active(task: Dict[str, Any]) -> bool:
    return not task.get("canceled") and not _task_done(task)


def _task_needs_move(task: Dict[str, Any], x: float, y: float) -> bool:
    target = task.get("target")
    if not isinstance(target, (list, tuple)) or len(target) < 2:
        return False
    try:
        tx, ty = float(target[0]), float(target[1])
    except Exception:
        return False
    return math.hypot(tx - x, ty - y) > _SIM_TARGET_RADIUS


def _active_task_for_robot(robot_id: str, x: float, y: float) -> Optional[Dict[str, Any]]:
    active: List[Tuple[Dict[str, Any], bool]] = []
    for t in TASKS.values():
        if t.get("robot_id") != robot_id:
            continue
        if t.get("canceled") or t.get("done"):
            continue
        needs_move = _task_needs_move(t, x, y)
        active.append((t, needs_move))
    if not active:
        return None
    # Prefer newest task for this robot to avoid bouncing between stale targets.
    active.sort(key=lambda item: (-float(item[0].get("created_at", 0.0)), 0 if item[1] else 1))
    return active[0][0]


def _tick_robots() -> None:
    global LAST_TICK
    if not _SIM_MOVE:
        return
    now = time.time()
    dt = max(0.05, min(now - LAST_TICK, 0.5))
    LAST_TICK = now

    map_obj = DATA.get("map", {})
    width = float(map_obj.get("width", 20))
    height = float(map_obj.get("height", 12))
    charging = map_obj.get("charging", {})
    ccoord = charging.get("coordinate") or [0.0, 0.0]
    cx, cy = float(ccoord[0]), float(ccoord[1])

    robots = DATA.get("robots", {})
    trace_steps = _trace_steps(now) if _SIM_TRACE else {}
    for rid, r in robots.items():
        if not isinstance(r, dict):
            continue

        if r.get("isOnline") is False:
            r["moveState"] = "offline"
            r["isCharging"] = False
            r["_wait_until"] = 0.0
            ROBOT_TARGETS.pop(rid, None)
            continue

        x = float(r.get("x", 1.0))
        y = float(r.get("y", 1.0))
        task = _active_task_for_robot(rid, x, y)
        if not task:
            r["moveState"] = "idle"
            r["isCharging"] = False
            r["_wait_until"] = 0.0
            ROBOT_TARGETS.pop(rid, None)
            continue

        wait_until = float(r.get("_wait_until", 0.0))

        # Low battery -> go charge.
        batt = float(r.get("battery", 50))
        if batt <= _SIM_BATTERY_LOW:
            ROBOT_TARGETS[rid] = (cx, cy)
            r["_wait_until"] = 0.0
        elif r.get("isCharging") and batt < _SIM_BATTERY_GOOD:
            ROBOT_TARGETS[rid] = (cx, cy)

        target = task.get("target")
        if isinstance(target, (list, tuple)) and len(target) >= 2:
            tx, ty = float(target[0]), float(target[1])
        else:
            tx, ty = ROBOT_TARGETS.get(rid, _pick_target())
        ROBOT_TARGETS[rid] = (tx, ty)

        dx = tx - x
        dy = ty - y
        dist = math.hypot(dx, dy)
        if wait_until > now:
            r["moveState"] = "waiting"
        elif dist <= _SIM_TARGET_RADIUS:
            # Snap to target and wait until vendor task completes.
            x = tx
            y = ty
            r["_wait_until"] = 0.0
            r["moveState"] = "waiting"
        else:
            step = min(dist, _SIM_SPEED * dt)
            x += (dx / dist) * step
            y += (dy / dist) * step
            r["moveState"] = "moving"

        # Clamp inside map
        x = max(0.5, min(width - 0.5, x))
        y = max(0.5, min(height - 0.5, y))
        r["x"] = round(x, 2)
        r["y"] = round(y, 2)

        # Charging + battery logic
        cdist = math.hypot(cx - x, cy - y)
        charging_now = cdist <= 0.6
        r["isCharging"] = charging_now
        batt = float(r.get("battery", 50))
        if charging_now:
            batt = min(100.0, batt + (_SIM_BATTERY_CHARGE * dt))
        elif r.get("moveState") == "moving":
            batt = max(_SIM_BATTERY_MIN, batt - (_SIM_BATTERY_DRAIN * dt))
        r["battery"] = round(batt, 1)

        _trace_robot(now, rid, r, task, tx, ty, trace_steps.get(rid, {}))


def _app_request(method: str, path: str, body: Optional[dict] = None) -> Tuple[int, str]:
    import urllib.request
    import urllib.error

    url = _SIM_APP_BASE_URL + path
    headers = {"X-API-Key": _SIM_API_KEY}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        return e.code, raw
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def _app_request_json(method: str, path: str, body: Optional[dict] = None) -> Tuple[int, Any]:
    status, raw = _app_request(method, path, body)
    if status == 0:
        return status, raw
    try:
        return status, json.loads(raw)
    except Exception:
        return status, raw


def _default_decision(step_code: Optional[str]) -> str:
    code = (step_code or "").upper()
    if code == "ORDER_DECISION":
        return "COMPLETED"
    if code == "CLEANUP_HAS_DISHES":
        return "NO"
    if code == "CLEANUP_MORE_DISHES":
        return "NO"
    if code.startswith("DELIVERY_"):
        return "CONFIRM"
    if code.startswith("BILLING_"):
        return "CONFIRM"
    return "CONFIRM"


def _trace_steps(now: float) -> Dict[str, Dict[str, Any]]:
    global TRACE_LAST_FETCH, TRACE_CACHE
    if not _SIM_TRACE:
        return {}
    if (now - TRACE_LAST_FETCH) < _SIM_TRACE_INTERVAL_S:
        return TRACE_CACHE
    TRACE_LAST_FETCH = now
    status, payload = _app_request_json("GET", "/dashboard/overview?limit=0&offset=0")
    if status != 200 or not isinstance(payload, dict):
        return TRACE_CACHE
    runs = payload.get("running_workflows") or []
    cache: Dict[str, Dict[str, Any]] = {}
    for r in runs:
        if not isinstance(r, dict):
            continue
        robot_id = r.get("robot_id")
        if not robot_id:
            continue
        cache[str(robot_id)] = {
            "run_id": r.get("run_id"),
            "task_id": r.get("task_id"),
            "step_type": (r.get("current_step") or {}).get("step_type"),
            "step_code": (r.get("current_step") or {}).get("step_code"),
            "label": (r.get("current_step") or {}).get("label"),
        }
    TRACE_CACHE = cache
    return cache


def _trace_robot(now: float, rid: str, r: Dict[str, Any], task: Optional[Dict[str, Any]], tx: float, ty: float, step_info: Dict[str, Any]) -> None:
    if not _SIM_TRACE:
        return
    last = TRACE_LAST.get(rid, 0.0)
    if (now - last) < _SIM_TRACE_INTERVAL_S:
        return
    TRACE_LAST[rid] = now
    try:
        os.makedirs(os.path.dirname(_SIM_TRACE_PATH), exist_ok=True)
        line = (
            f"{datetime.now(timezone.utc).isoformat()} "
            f"robot={rid} x={r.get('x')} y={r.get('y')} state={r.get('moveState')} batt={r.get('battery')} "
            f"target=({round(tx,2)},{round(ty,2)}) "
            f"task_id={None if not task else task.get('task_id')} task_done={None if not task else task.get('done')} "
            f"run_id={step_info.get('run_id')} wf_task_id={step_info.get('task_id')} "
            f"step_type={step_info.get('step_type')} step_code={step_info.get('step_code')} label={step_info.get('label')}\n"
        )
        with open(_SIM_TRACE_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _status_is(value: Any, status: str) -> bool:
    if value is None:
        return False
    s = str(value).upper()
    return s == status.upper() or s.endswith(f".{status.upper()}")


@app.get("/sim/queue")
def sim_queue():
    status, raw = _app_request("GET", "/queue-manager/queue")
    if status != 200:
        return {"ok": False, "status": status, "error": raw, "queue": []}
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}

    queue = payload.get("queue", []) if isinstance(payload, dict) else []
    stats_status, stats_raw = _app_request("GET", "/queue-manager/stats")
    stats = None
    if stats_status == 200:
        try:
            stats = json.loads(stats_raw)
        except Exception:
            stats = None

    # also include pending tasks (scheduled)
    pending_items: List[Dict[str, Any]] = []
    t_status, t_raw = _app_request("GET", "/task-manager/tasks?limit=200&offset=0")
    if t_status == 200:
        try:
            tasks = json.loads(t_raw)
            if isinstance(tasks, list):
                for t in tasks:
                    if not isinstance(t, dict):
                        continue
                    if _status_is(t.get("status"), "PENDING"):
                        pending_items.append(
                            {
                                "task_id": t.get("id"),
                                "task_type": t.get("task_type"),
                                "status": t.get("status"),
                                "title": t.get("title"),
                                "target_kind": t.get("target_kind"),
                                "target_ref": t.get("target_ref"),
                                "release_at": t.get("release_at"),
                                "created_at": t.get("created_at"),
                            }
                        )
        except Exception:
            pass

    return {
        "ok": True,
        "queue": queue,
        "pending": pending_items,
        "pending_count": len(pending_items),
        "stats": stats,
    }


@app.get("/sim/tasks")
def sim_tasks(limit: int = 200, offset: int = 0):
    status, payload = _app_request_json("GET", f"/dashboard/overview?limit={int(limit)}&offset={int(offset)}")
    if status != 200 or not isinstance(payload, dict):
        return {"ok": False, "status": status, "error": payload, "tasks": []}
    tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
    return {"ok": True, "tasks": tasks}


@app.post("/sim/robot/online")
def sim_robot_online(robot_id: str, online: bool = True):
    robots = DATA.get("robots", {})
    r = robots.get(robot_id)
    if not isinstance(r, dict):
        return {"ok": False, "error": "Robot not found"}
    r["isOnline"] = bool(online)
    if not online:
        r["moveState"] = "offline"
        r["isCharging"] = False
        r["_wait_until"] = 0.0
    elif r.get("moveState") == "offline":
        r["moveState"] = "idle"
    return {"ok": True, "robot_id": robot_id, "isOnline": r["isOnline"]}


@app.post("/sim/restart")
def sim_restart(manual: bool = True):
    # Reset app data first
    reset_status, reset_raw = _app_request("POST", "/controls/reset")
    if reset_status != 200:
        return {"ok": False, "step": "reset", "status": reset_status, "error": reset_raw}

    # Clear local simulator task cache/targets
    TASKS.clear()
    ROBOT_TARGETS.clear()
    for r in (DATA.get("robots", {}) or {}).values():
        if isinstance(r, dict):
            r["_wait_until"] = 0.0
            r["moveState"] = "idle"
            r["isCharging"] = False
            r["battery"] = 100.0

    if manual:
        return {
            "ok": True,
            "mode": "manual",
            "reset": {"status": reset_status, "raw": reset_raw},
            "created": 0,
            "failed": 0,
            "last_error": None,
            "tables": 0,
        }

    # Seed restaurant-style tasks (ORDERING -> DELIVERY -> CLEANUP)
    pois = _map_pois(DATA.get("map", {}))
    table_refs = _table_refs_from_pois(pois)
    if _SIM_RESTART_TABLES > 0:
        table_refs = table_refs[:_SIM_RESTART_TABLES]
    if not table_refs:
        table_refs = ["1"]

    now = datetime.now(timezone.utc)
    created = 0
    failed = 0
    last_error = None

    for i, tref in enumerate(table_refs):
        order_time = now + timedelta(seconds=i * _SIM_RESTART_ARRIVAL_GAP)
        delivery_time = order_time + timedelta(seconds=_SIM_RESTART_DELIVERY_GAP)
        cleanup_time = delivery_time + timedelta(seconds=_SIM_RESTART_CLEANUP_GAP)

        if _SIM_RESTART_MODE == "ordering_only":
            task_plan = (("ORDERING", order_time),)
        else:
            task_plan = (
                ("ORDERING", order_time),
                ("DELIVERY", delivery_time),
                ("CLEANUP", cleanup_time),
            )

        for task_type, when in task_plan:
            release_at = None
            if task_type == "ORDERING":
                if i >= _SIM_RESTART_INITIAL_READY:
                    release_at = when
            else:
                release_at = when

            params = {
                "title": f"{_SIM_RESTART_TITLE_PREFIX}-T{tref}-{task_type}",
                "task_type": task_type,
                "target_kind": "TABLE",
                "target_ref": tref,
            }
            if release_at is not None:
                params["release_at"] = release_at.isoformat()
            path = "/task-manager/tasks?" + urllib.parse.urlencode(params)
            status, raw = _app_request("POST", path)
            if status == 200:
                created += 1
            else:
                failed += 1
                last_error = raw

    return {
        "ok": failed == 0,
        "reset": {"status": reset_status, "raw": reset_raw},
        "created": created,
        "failed": failed,
        "last_error": last_error,
        "tables": len(table_refs),
    }


@app.get("/sim/runs")
def sim_runs():
    status, runs = _app_request_json("GET", "/workflow-engine/runs?limit=50&offset=0")
    if status != 200 or not isinstance(runs, list):
        return {"ok": False, "status": status, "error": runs, "runs": []}

    out: List[Dict[str, Any]] = []
    for r in runs:
        if not isinstance(r, dict):
            continue
        if str(r.get("status", "")).upper() not in ("RUNNING", "WORKFLOWRUNSTATUS.RUNNING"):
            continue
        run_id = r.get("id")
        if not run_id:
            continue
        d_status, detail = _app_request_json("GET", f"/workflow-engine/runs/{run_id}")
        if d_status != 200 or not isinstance(detail, dict):
            out.append({
                "run_id": run_id,
                "robot_id": r.get("robot_id"),
                "task_id": r.get("task_id"),
                "status": r.get("status"),
                "error": detail,
            })
            continue
        steps = (detail.get("steps") or [])
        cur_idx = (detail.get("run") or {}).get("current_step_index")
        cur = None
        for s in steps:
            if isinstance(s, dict) and s.get("step_index") == cur_idx:
                cur = s
                break
        out.append({
            "run_id": run_id,
            "robot_id": r.get("robot_id"),
            "task_id": r.get("task_id"),
            "status": r.get("status"),
            "current_step_index": cur_idx,
            "step_code": None if not cur else cur.get("step_code"),
            "step_type": None if not cur else cur.get("step_type"),
            "label": None if not cur else cur.get("label"),
        })

    return {"ok": True, "runs": out}


@app.post("/sim/confirm")
def sim_confirm(run_id: int, decision: Optional[str] = None, minutes: Optional[int] = None, auto: bool = False):
    loops = 0
    last_status = None
    last_raw = None

    def _confirm_once(decision_value: str) -> Tuple[int, str]:
        payload: Dict[str, Any] = {}
        if decision_value == "POSTPONE":
            payload["minutes"] = int(minutes or 10)
        return _app_request("POST", f"/workflow-engine/runs/{run_id}/confirm", {"decision": decision_value, "payload": payload})

    if not auto:
        dec = (decision or "").strip().upper() or "CONFIRM"
        last_status, last_raw = _confirm_once(dec)
        if last_status == 200:
            _app_request("POST", "/workflow-engine/tick")
        return {"ok": last_status == 200, "status": last_status, "raw": last_raw, "loops": loops}

    # Auto-confirm only consecutive manual steps, then stop so nav steps can play out.
    start = time.time()
    while loops < 25 and (time.time() - start) < 8.0:
        loops += 1
        d_status, detail = _app_request_json("GET", f"/workflow-engine/runs/{run_id}")
        if d_status != 200 or not isinstance(detail, dict):
            break
        run = detail.get("run") or {}
        if str(run.get("status", "")).upper() not in ("RUNNING", "WORKFLOWRUNSTATUS.RUNNING"):
            break
        cur_idx = run.get("current_step_index")
        steps = detail.get("steps") or []
        cur = None
        for s in steps:
            if isinstance(s, dict) and s.get("step_index") == cur_idx:
                cur = s
                break
        if not cur:
            break
        step_type = str(cur.get("step_type", "")).upper()
        if step_type == "MANUAL_CONFIRM":
            dec = _default_decision(cur.get("step_code"))
            last_status, last_raw = _confirm_once(dec)
            if last_status != 200:
                break
            _app_request("POST", "/workflow-engine/tick")
            time.sleep(0.2)
            # Re-check; if next step isn't manual, stop so the robot can move.
            d2_status, detail2 = _app_request_json("GET", f"/workflow-engine/runs/{run_id}")
            if d2_status != 200 or not isinstance(detail2, dict):
                break
            run2 = detail2.get("run") or {}
            if str(run2.get("status", "")).upper() not in ("RUNNING", "WORKFLOWRUNSTATUS.RUNNING"):
                break
            next_idx = run2.get("current_step_index")
            steps2 = detail2.get("steps") or []
            next_step = None
            for s2 in steps2:
                if isinstance(s2, dict) and s2.get("step_index") == next_idx:
                    next_step = s2
                    break
            next_type = str((next_step or {}).get("step_type", "")).upper()
            if next_type != "MANUAL_CONFIRM":
                break
            continue

        break

    ok = last_status == 200 if last_status is not None else False
    return {"ok": ok, "status": last_status, "raw": last_raw, "loops": loops, "auto": True}


@app.post("/sim/workflow-tick")
def sim_workflow_tick():
    status, raw = _app_request("POST", "/workflow-engine/tick")
    return {"ok": status == 200, "status": status, "raw": raw}


@app.post("/sim/orchestrator-tick")
def sim_orchestrator_tick(max_assignments: int = 2, preferred_robot_id: Optional[str] = None):
    params = {"max_assignments": max(0, int(max_assignments))}
    if preferred_robot_id:
        params["preferred_robot_id"] = preferred_robot_id
    path = "/orchestrator/tick?" + urllib.parse.urlencode(params)
    status, payload = _app_request_json("POST", path)
    return {"ok": status == 200, "status": status, "data": payload}


@app.post("/sim/create-task")
def sim_create_task(table_ref: str, task_type: str, tick: bool = True, release_at: Optional[str] = None):
    tref = (table_ref or "").strip()
    ttype = (task_type or "").strip().upper()
    if not tref:
        return {"ok": False, "error": "table_ref is required"}
    if ttype not in ("ORDERING", "DELIVERY", "CLEANUP", "BILLING", "NAVIGATE", "CHARGING"):
        return {"ok": False, "error": f"invalid task_type: {task_type}"}

    params = {
        "title": f"Manual-{ttype}-T{tref}",
        "task_type": ttype,
        "target_kind": "TABLE",
        "target_ref": tref,
    }
    if release_at:
        params["release_at"] = release_at
    path = "/task-manager/tasks?" + urllib.parse.urlencode(params)
    status, raw = _app_request("POST", path)
    if status != 200:
        return {"ok": False, "status": status, "error": raw}

    tick_status = None
    tick_raw = None
    if tick:
        tick_status, tick_raw = _app_request("POST", "/orchestrator/tick?max_assignments=1")

    return {
        "ok": True,
        "task_create": {"status": status, "raw": raw},
        "tick": {"status": tick_status, "raw": tick_raw},
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "tokens": len(TOKENS),
        "tasks": len(TASKS),
        "robots": len(DATA.get("robots", {})),
        "app_base_url": _SIM_APP_BASE_URL,
        "flags": {
            "SIM_FAIL_TOKEN": _FAIL_TOKEN,
            "SIM_FAIL_STATE": _FAIL_STATE,
            "SIM_FAIL_POI": _FAIL_POI,
            "SIM_TASK_NEVER_DONE": _TASK_NEVER_DONE,
            "SIM_RANDOM_MAP": _SIM_RANDOM_MAP,
            "SIM_MOVE": _SIM_MOVE,
        },
    }


@app.get("/sim/ui", response_class=HTMLResponse)
def sim_ui():
    try:
        with open(_UI_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "<h3>simulator/ui.html not found</h3>"


@app.get("/sim/state")
def sim_state():
    _tick_robots()
    map_obj = DATA.get("map", {})
    robots = []
    for rid, r in (DATA.get("robots", {}) or {}).items():
        if isinstance(r, dict):
            out = dict(r)
            out["robotId"] = rid
            robots.append(out)
    return {"map": map_obj, "robots": robots, "pois": _map_pois(map_obj)}


@app.post("/auth/v1.1/token")
async def auth_token(_: Request):
    if _FAIL_TOKEN:
        return _err(500, "Simulated auth failure")
    token = _issue_token()
    return _ok({"token": token})


@app.get("/robot/v2.0/{robot_id}/state")
async def robot_state(robot_id: str, request: Request):
    if not _valid_token(request):
        return _err(401, "Invalid token")
    if _FAIL_STATE:
        return _err(500, "Simulated robot state failure")
    _tick_robots()
    state = _robot_state(robot_id)
    if not state:
        return _err(404, "Robot not found")
    return _ok(state)


@app.post("/map/v1.1/poi/list")
async def poi_list(request: Request):
    if not _valid_token(request):
        return _err(401, "Invalid token")
    if _FAIL_POI:
        return _err(500, "Simulated POI list failure")
    body = await request.json()
    robot_id = body.get("robotId")
    if not robot_id:
        return _err(400, "Missing robotId")
    rows = _robot_pois(robot_id)
    return _ok({"list": rows, "total": len(rows), "pageNum": 1, "pageSize": body.get("pageSize", 0)})


@app.post("/task/v3/create")
async def task_create(request: Request):
    if not _valid_token(request):
        return _err(401, "Invalid token")
    body = await request.json()
    task_id = str(uuid.uuid4())
    robot_id = body.get("robotId")
    target = None
    pts = body.get("taskPts") or []
    if isinstance(pts, list) and pts:
        pt = pts[0] if isinstance(pts[0], dict) else None
        if pt:
            target = [pt.get("x"), pt.get("y")]
    TASKS[task_id] = {
        "created_at": time.time(),
        "body": body,
        "task_id": task_id,
        "canceled": False,
        "robot_id": robot_id,
        "target": target,
    }
    if robot_id and isinstance(target, list) and len(target) >= 2:
        try:
            ROBOT_TARGETS[robot_id] = (float(target[0]), float(target[1]))
        except Exception:
            pass
    return _ok({"taskId": task_id})


@app.get("/task/v2.0/{task_id}/state")
async def task_state(task_id: str, request: Request):
    if not _valid_token(request):
        return _err(401, "Invalid token")
    _tick_robots()
    task = TASKS.get(task_id)
    if not task:
        return _err(404, "Task not found")

    if task.get("canceled"):
        act_type = 1002
    else:
        done = False
        if not _TASK_NEVER_DONE:
            dist = _robot_target_distance(task.get("robot_id"), task.get("target"))
            if dist is not None:
                if dist <= _SIM_TARGET_RADIUS:
                    if not task.get("arrived_at"):
                        task["arrived_at"] = time.time()
                    dwell = time.time() - float(task.get("arrived_at"))
                    done = dwell >= _TASK_DONE_SECONDS
                else:
                    task.pop("arrived_at", None)
                    done = False
            else:
                elapsed = time.time() - float(task.get("created_at", time.time()))
                done = elapsed >= _TASK_DONE_SECONDS
        act_type = 1001 if done else 1000
        if done:
            task["done"] = True

    return _ok({"taskId": task_id, "actType": act_type})


@app.post("/task/v3/cancel")
async def task_cancel_v3(request: Request):
    if not _valid_token(request):
        return _err(401, "Invalid token")
    body = await request.json()
    task_id = body.get("taskId")
    if not task_id:
        return _err(400, "Missing taskId")
    task = TASKS.get(task_id)
    if not task:
        return _err(404, "Task not found")
    task["canceled"] = True
    return _ok({"taskId": task_id, "canceled": True})


@app.post("/task/v2.0/{task_id}/cancel")
async def task_cancel_v2(task_id: str, request: Request):
    if not _valid_token(request):
        return _err(401, "Invalid token")
    task = TASKS.get(task_id)
    if not task:
        return _err(404, "Task not found")
    task["canceled"] = True
    return _ok({"taskId": task_id, "canceled": True})
