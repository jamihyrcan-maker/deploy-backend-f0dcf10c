# Backend_dev_codex (Version 7)

This repo contains a FastAPI backend for task scheduling, assignment, and workflow execution, plus a simulator that mimics the AutoXing vendor API and provides a simple UI for testing without real robots.

## Overview

The system has two primary parts:
- Main backend (FastAPI): task manager, queue manager, assignment engine, workflow engine, and dashboard APIs.
- Simulator (FastAPI + UI): mock AutoXing API endpoints, a live map UI, and manual controls for testing workflows.

## Components

- `app/`: backend services (tasks, queue, assignment, workflow, dashboard, robot API).
- `simulator/`: mock vendor API + UI (`/sim/ui`), and helper scripts.
- `robot_backend.db`: SQLite database for tasks, runs, steps, mappings.
- `logs/`: runtime logs (backend and simulator).

## Requirements

- Python 3.10+
- Recommended: create/activate a virtual environment
- Dependencies are assumed installed (not managed in this README)

## Setup

1) Create a virtual environment (optional but recommended).
2) Install dependencies (use your existing method/lockfile).
3) Ensure ports 8000 (backend) and 9001 (simulator) are free.

## Run Commands

### Backend (real or mock)

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

### Simulator (mock vendor API + UI)

```powershell
python -m uvicorn simulator.main:app --reload --port 9001
```

### Run both together

Open two terminals:
1) Backend on `8000`
2) Simulator on `9001`

The simulator UI will call the backend via `SIM_APP_BASE_URL`, which defaults to `http://127.0.0.1:8000`.

## Environment Variables

### Backend (core)

These control the main backend behavior:
- `ROBOT_IDS`: comma-separated robot IDs (example: `SIM-ROBOT-1,SIM-ROBOT-2`)
- `API_KEY_MONITOR`, `API_KEY_OPERATOR`, `API_KEY_ADMIN`: required API keys for role-based access
- `ALLOW_DEFAULT_API_KEYS`: set `1` only for local/dev fallback keys (`dev-*`)
- `CORS_ALLOW_ORIGINS`: comma-separated frontend origins (example: `https://my-frontend.vercel.app,http://localhost:3000`)
- `CORS_ALLOW_CREDENTIALS`: `0` or `1`
- `SAFE_MODE`: `1` blocks vendor task creation (default is `1`; set `0` for simulator runs)
- `AUTO_TICK_ENABLED`: `1` to auto-assign on a timer
- `AUTO_TICK_URL`: e.g. `http://127.0.0.1:8000/orchestrator/tick`
- `AUTO_TICK_API_KEY`: usually `dev-admin-key`
- `AUTO_TICK_INTERVAL_S`: seconds between assignment ticks
- `AUTO_TICK_MAX_ASSIGNMENTS`: per tick assignment limit
- `AUTO_CONFIRM_ENABLED`: `1` to auto-confirm workflow steps
- `AUTO_CONFIRM_URL`: e.g. `http://127.0.0.1:8000`
- `AUTO_CONFIRM_API_KEY`: usually `dev-admin-key`
- `AUTO_CONFIRM_INTERVAL_S`: seconds between confirm checks

### Backend (vendor credentials)

For a real AutoXing server:
- `AUTOX_BASE_URL`
- `AUTOX_APP_ID`
- `AUTOX_APP_SECRET`
- `AUTOX_APP_CODE`

For simulation, set these to mock values and point `AUTOX_BASE_URL` to the simulator.

### Simulator

Common simulator settings:
- `SIM_APP_BASE_URL` (default `http://127.0.0.1:8000`)
- `SIM_API_KEY` (default `dev-admin-key`)
- `SIM_SPEED`, `SIM_TARGET_RADIUS`
- `SIM_BATTERY_DRAIN`, `SIM_BATTERY_CHARGE`, `SIM_IDLE_DRAIN`
- `SIM_TASK_DONE_SECONDS` (time robot must dwell at target before vendor task completes)

## Simulator UI

Open:
```
http://127.0.0.1:9001/sim/ui
```

Features:
- Live map with robots and POIs (tables, kitchen, operator, charging).
- Queue view and pending list.
- Manual confirm buttons (green only when a manual step is active).
- Restart button (resets tasks, batteries to 100%).
- Manual task creation with optional `release_at` scheduling.
- Auto create and auto assign toggles (separate).

### Create Task vs Create + Assign

- Create Task: only inserts a task (READY or PENDING); no assignment.
- Create + Assign: creates the task and triggers one assignment tick.

### Release At

The UI supports scheduling:
- `Release at (ISO)`: exact ISO-8601 timestamp
- `Delay (s)`: relative offset if no ISO is provided

Scheduled tasks remain `PENDING` until their `release_at` time is reached.

### Auto Create / Auto Assign

- Auto create: generates tasks on a timer (does not assign).
- Auto assign: triggers `/orchestrator/tick` on a timer (does not create).

## Main Backend Capabilities

- Task creation, update, cancel
- Queue promotion (PENDING -> READY)
- Priority-based assignment
- Workflow runs with NAVIGATE and MANUAL_CONFIRM steps
- Dashboard overview (robots, queue, workflows)
- Orchestrator tick (promote + assign + workflow progress)

## Simulator Capabilities

- Mock vendor API endpoints:
  - token issuance
  - robot state
  - POI list
  - task create / state / cancel
- Movement simulation with speed and battery
- Manual confirmation UI for workflow steps
- Auto create / auto assign tools

Limitations:
- Movement is approximate (not a physics engine).
- Vendor task completion is simulated by proximity + dwell time.

## Expected Behavior (Checklist)

Delivery task example:
1) Robot navigates to Kitchen.
2) Manual confirm appears (green).
3) After confirm, robot goes to Operator.
4) Confirm again, robot goes to target Table.
5) Final confirm marks task DONE.

Ordering task example:
1) Robot goes to Table.
2) Manual confirm (POSTPONE or COMPLETED).

Cleanup task example:
1) Robot goes to Table.
2) Manual confirm: has dishes?
3) If YES, robot goes to Washing.
4) Manual confirm: more dishes?

Queue behavior:
- `PENDING` tasks appear in the Pending list.
- `READY` tasks appear in Queue (live).
- `ASSIGNED` tasks are in running workflow.
- `DONE` tasks disappear from queue.

## Troubleshooting

- Robot does not take next task:
  - No assignment tick happened. Run `/orchestrator/tick`.
  - Robot is busy or waiting on a manual confirm.

- Task stuck in PENDING:
  - `release_at` is in the future; wait or change it.
  - Run `/queue-manager/tick` to promote due tasks.

- Confirm button appears too early:
  - This should only happen after arrival; check simulator logs.

- Robot oscillates between points:
  - Usually due to stale vendor tasks; restart simulator and clear tasks.

## Files and Logs

- DB: `robot_backend.db`
- Logs: `logs/app_8000.log`, `logs/sim_9001.err`
- Extra docs:
  - `codex_swagger.md`
  - `codex_fixed.md`
  - `codex_readme.md`

## Safety Notes

- Use `SAFE_MODE=1` when you do not want vendor tasks created.
- For local simulator, set `API_KEY_ADMIN=dev-admin-key`, `API_KEY_OPERATOR=dev-operator-key`, `API_KEY_MONITOR=dev-monitor-key`.
- For deployment, use strong random API keys and set `CORS_ALLOW_ORIGINS` to your frontend domains only.
- Be careful running against real robots. Use the simulator when possible.

## Results Template (Fill In)

- Backend startup: PASS / FAIL
- Simulator startup: PASS / FAIL
- Create Task (READY): PASS / FAIL
- Create + Assign: PASS / FAIL
- Delivery flow: PASS / FAIL
- Ordering flow: PASS / FAIL
- Cleanup flow: PASS / FAIL
- Auto create: PASS / FAIL
- Auto assign: PASS / FAIL

Record notes in `codex_fixed.md` or a separate log.
