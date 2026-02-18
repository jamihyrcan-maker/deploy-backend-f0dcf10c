# Codex Readme

This document explains what was added, how to run the system safely, and the tests that were executed so far. It is written for quick handoff and real-world readiness.

## 1) What the system does (high level)

- FastAPI backend that manages tasks, queues, priorities, workflow runs, robot state polling, and realtime events.
- Vendor integration is AutoXing (token auth, robot state, POI list, task create, task state).
- Optional mock AutoXing server for safe local testing.

## 2) Key safety controls added

- SAFE_MODE: blocks vendor task creation (robot movement).
- REQUIRE_ROBOT_IDS: fails startup if ROBOT_IDS is missing.
- Per-robot concurrency: prevents multiple RUNNING workflows for the same robot.
- Preflight endpoint: validates DB, config, and optional vendor connectivity.
- Vendor cancel: best-effort cancel endpoints wired in (needs real vendor verification).

## 3) Environment variables (important)

Core vendor config:
- AUTOX_BASE_URL
- AUTOX_APP_ID
- AUTOX_APP_SECRET
- AUTOX_APP_CODE
- AUTOX_TOKEN_TTL_SECONDS (optional)

Safety:
- SAFE_MODE=1  -> blocks vendor task creation
- REQUIRE_ROBOT_IDS=1 -> fail startup if ROBOT_IDS is empty
- ROBOT_IDS="id1,id2" -> used by assignment engine and monitor

Mock forcing:
- AUTOX_FORCE_ENV=1 -> force env vars even if app/secrets.py exists

API auth (defaults exist):
- API_KEY_MONITOR / API_KEY_OPERATOR / API_KEY_ADMIN
- Defaults include: dev-admin-key, dev-operator-key, dev-monitor-key

## 4) New endpoints

Preflight:
- GET /preflight/check
- GET /preflight/check?verify_vendor=true

Vendor cancel (admin):
- POST /controls/vendor-task/{vendor_task_id}/cancel

## 5) Mock AutoXing server

Location:
- simulator/main.py
- simulator/data.json

Run mock server:
```
uvicorn simulator.main:app --reload --port 9001
```

Switch current shell to mock:
```
. .\simulator\switch_to_mock.ps1
```

This sets:
- AUTOX_BASE_URL=http://127.0.0.1:9001
- AUTOX_APP_ID=mock
- AUTOX_APP_SECRET=mock
- AUTOX_APP_CODE=mock
- AUTOX_FORCE_ENV=1
- ROBOT_IDS=8982507c06180BG

## 6) Test suites executed so far

A) Safe smoke tests (no robot movement)
- OpenAPI
- Robot state and POIs (read-only)
- POI mapping auto-map and CRUD
- Task manager CRUD
- Priority override
- Queue manager endpoints
- Workflow engine list + tick (no run start)
- Assignment list
- Realtime bus health + publish
- Dashboard overview
- Robot monitor states
- Controls task cancel

Status: PASS

B) Full smoke suite with real vendor (earlier)
- Full run including workflow start, assignment, orchestrator
- Robot moved (unsafe in real environment)

Status: PASS but unsafe for real robots

C) Full smoke suite with mock + SAFE_MODE validation
- SAFE_MODE=0: workflow run created then canceled
- SAFE_MODE=1: workflow run blocked with explicit error

Status: PASS

Important: The SAFE_MODE and AUTOX_FORCE_ENV tests confirmed the app can be pointed to mock reliably.

## 7) Known limitations / remaining verification (real robots)

These are best verified next week with real robots:
- Vendor cancel: implemented but must confirm vendor endpoints and behavior.
- Manual-confirm workflows: ORDERING / DELIVERY / CLEANUP flows not verified.
- Scheduling: PENDING tasks with release_at promotion.
- WebSocket /ws connect and event propagation.

## 8) Recommended real-robot test plan (next week)

Minimal, safe order:
1) Preflight check with verify_vendor=true
2) Single NAVIGATE task to short safe POI
3) Vendor cancel mid-run
4) Manual-confirm flow (ORDERING or DELIVERY)
5) Two-robot parallel test (staggered starts)

## 9) How to run locally (safe)

1) Set SAFE_MODE=1
2) Start app
3) Use Swagger or curl to exercise safe endpoints

Example:
```
$env:SAFE_MODE = "1"
uvicorn app.main:app --reload --port 8000
```

## 10) Troubleshooting

Robot moved when mock was intended:
- Ensure app process has AUTOX_BASE_URL set to 127.0.0.1:9001
- Ensure AUTOX_FORCE_ENV=1 if secrets.py exists
- Stop all previous uvicorn processes before starting new ones

500 from queue-manager/queue:
- Fixed by making timezone-safe math in queue manager (already patched)

Preflight shows real AutoXing base URL:
- Env not applied to the app process
- Start app in the same shell or use explicit env vars

## 11) Files added/changed (summary)

New:
- app/common/safety.py
- app/preflight/router.py
- app/preflight/__init__.py
- simulator/main.py
- simulator/data.json
- simulator/switch_to_mock.ps1
- simulator/__init__.py

Changed:
- app/workflow_engine/service.py (SAFE_MODE + per-robot concurrency + logs)
- app/workflow_engine/vendor_task_client.py (cancel methods)
- app/controls/router.py (vendor cancel wiring + audit logs)
- app/task_manager/router.py (audit logs)
- app/common/retry.py (retry logging)
- app/main.py (preflight router + REQUIRE_ROBOT_IDS)
- app/robot_api/autox_client.py (AUTOX_FORCE_ENV)

## 12) TODOs (only what matters)

- Confirm correct vendor cancel endpoint and payload.
- Validate manual-confirm workflows with real robots.
- Validate scheduling (release_at) end-to-end.
- Exercise WebSocket /ws for realtime events.
