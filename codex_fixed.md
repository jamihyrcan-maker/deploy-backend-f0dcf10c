# Codex Fix Log (Detailed)

This document records every error encountered so far and the exact fixes applied. It is a chronological + categorized audit so you can trace how the system stabilized.

---

## 1) Errors Encountered (Detailed)

### A) API / Runtime errors

1) AttributeError: missing get_robot_state
- Symptom: `AttributeError: 'RetryingRobotAPIService' object has no attribute 'get_robot_state'`
- Location: `app/robot_api/router.py` calling `svc.get_robot_state`.
- Root cause: `RetryingRobotAPIService` only exposed `get_state`, not `get_robot_state`, and called a non-existent `inner.get_state`.

2) Vendor connectivity error
- Symptom: `httpx.ConnectError` (stack from `AutoXingClient._fetch_token`)
- Root cause: network/proxy/base URL or credentials at time of test.
- Impact: `/robot-api/robots/{id}/state` and `/pois` failed with 500.

3) Missing X-API-Key
- Symptom: 401 on many endpoints: `{"detail":"Missing or invalid X-API-Key"}`
- Root cause: auth required, header absent.
- Fix: use default dev key `dev-admin-key`.

4) 422 Unprocessable Entity (task-manager create/update)
- Symptom: `release_at` parsing error when using auto-generated body.
- Root cause: `release_at` is a query parameter in FastAPI signature, not JSON body.

5) 500 on `/queue-manager/queue`
- Symptom: Internal Server Error.
- Root cause: timezone mismatch in `aging_bonus_minutes`: SQLite returns naive datetime but code subtracts from aware UTC datetime.

6) 500 on `/dashboard/overview`
- Symptom: Internal Server Error.
- Root cause: same underlying queue-manager failure (used in dashboard aggregation).

7) Manual confirm endpoint returned 400
- Symptom: `{"detail":"Current step is not MANUAL_CONFIRM"}`
- Root cause: workflow step type was NAVIGATE; expected/valid behavior.

8) Assignment failed: no robots configured
- Symptom: `assigned:false, "No robots configured. Set ROBOT_IDS env var or secrets.ROBOT_IDS."`
- Root cause: `ROBOT_IDS` not set.

9) Vendor cancel placeholder returned ok:false
- Symptom: `/controls/vendor-task/{id}/cancel` returned ok:false
- Root cause: vendor cancel was not implemented; placeholder response.

10) Mock tests initially hit real vendor
- Symptom: preflight showed base_url = `https://apiglobal.autoxing.com` during mock test.
- Root cause: `AutoXingConfig` prioritized `app/secrets.py` over env vars.

11) SAFE_MODE validation failed in early mock runs
- Symptom: SAFE_MODE tests didn?t show correct env or blocked behavior.
- Root cause: environment not applied to spawned process, and old uvicorn still running on port.

12) Robot movement during unsafe tests
- Symptom: robot started moving when full smoke tests were run.
- Root cause: `/workflow-engine/runs` creates vendor tasks; ?unsafe? endpoints were called.

### B) Local tooling / environment errors (not app defects)

- PowerShell ConstrainedLanguage error: `Cannot set property. Property setting is supported only on core types in this language mode.`
  - Source: shell output encoding logic from the tool environment.
  - No app code impact.

- SQLite write attempt failed in a direct Python test: `sqlite3.OperationalError: attempt to write a readonly database`
  - Source: local script attempt in restricted sandbox.
  - No app code impact.

---

## 2) Fixes and Changes Applied

### A) Robot API and resilience

1) Added `get_robot_state` to RetryingRobotAPIService and alias
- File: `app/common/vendor_resilience.py`
- Change: Added `get_robot_state`, made `get_state` call it.

2) Added backward-compatible `get_state` to RobotAPIService
- File: `app/robot_api/service.py`
- Change: `get_state` now calls `get_robot_state`.

### B) Queue manager 500 fix (timezone)

3) Fixed timezone mismatch in `aging_bonus_minutes`
- File: `app/queue_manager/service.py`
- Change: normalize naive datetime to UTC.
- Result: `/queue-manager/queue` and `/dashboard/overview` stable.

### C) Safety controls and runtime checks

4) SAFE_MODE toggle (blocks vendor task creation)
- File: `app/common/safety.py`
- File: `app/workflow_engine/service.py`
- Change: `SAFE_MODE=1` raises error before vendor task creation.

5) Per-robot concurrency lock
- File: `app/workflow_engine/service.py`
- Change: prevent new RUNNING workflow if robot already has one.

6) REQUIRE_ROBOT_IDS startup guard
- File: `app/main.py`
- Change: if `REQUIRE_ROBOT_IDS=1` and `ROBOT_IDS` empty, startup fails.

### D) Vendor cancel (best-effort)

7) Implemented vendor cancel in AutoXingTaskClient
- File: `app/workflow_engine/vendor_task_client.py`
- Change: `task_cancel_v3`, `task_cancel_v2`, and fallback `task_cancel` added.

8) Wired vendor cancel into controls endpoint
- File: `app/controls/router.py`
- Change: calls task_client.task_cancel; original placeholder kept commented.

### E) Preflight diagnostics

9) Added preflight router
- File: `app/preflight/router.py`
- Endpoint: `GET /preflight/check` (optional `verify_vendor=true`).
- Checks: DB access, config presence, safe_mode flag, robot ids, vendor connectivity (optional).

10) Registered preflight router
- File: `app/main.py`

### F) Logging / audit

11) Retry logging
- File: `app/common/retry.py`
- Change: logs retry attempt, delay, error.

12) Task audit logs
- File: `app/task_manager/router.py`
- Change: logs task creation/update/status changes.

13) Controls audit logs
- File: `app/controls/router.py`
- Change: logs task/run cancellations.

### G) Mock compatibility

14) AutoXingConfig override for env
- File: `app/robot_api/autox_client.py`
- Change: `AUTOX_FORCE_ENV=1` forces env vars even if secrets.py exists.

15) Mock switch script updated
- File: `simulator/switch_to_mock.ps1`
- Change: sets `AUTOX_FORCE_ENV=1`.

---

## 3) Tests Executed and Results (Summary)

### Safe smoke tests (no robot movement)
- PASS: OpenAPI, robot state/POIs (when vendor reachable), POI mapping, task CRUD, queue, dashboard, realtime bus, robot monitor.

### Full smoke tests (unsafe)
- PASS: workflow start, assignment, orchestrator (but robot moved). Unsafe for real robots.

### Mock tests
- PASS: all endpoints against mock once env was forced.
- SAFE_MODE=0 allows workflow run creation.
- SAFE_MODE=1 blocks workflow run creation with explicit error.

---

## 4) Known Remaining Verification (not fixed yet)

These require real-robot testing:
- Confirm vendor cancel endpoint behavior and payload.
- Manual-confirm workflows (ORDERING / DELIVERY / CLEANUP).
- Release_at scheduling end-to-end.
- WebSocket `/ws` realtime flow.

---

## 5) Files Added / Modified

Added:
- `app/common/safety.py`
- `app/preflight/router.py`
- `app/preflight/__init__.py`
- `simulator/main.py`
- `simulator/data.json`
- `simulator/switch_to_mock.ps1`
- `simulator/__init__.py`
- `codex_readme.md`

Modified:
- `app/common/vendor_resilience.py`
- `app/robot_api/service.py`
- `app/queue_manager/service.py`
- `app/workflow_engine/service.py`
- `app/workflow_engine/vendor_task_client.py`
- `app/controls/router.py`
- `app/main.py`
- `app/common/retry.py`
- `app/task_manager/router.py`
- `app/robot_api/autox_client.py`

---

## 6) Quick Notes

- If robot moves unexpectedly, check SAFE_MODE and ensure app points to mock (`AUTOX_BASE_URL`), and stop any old uvicorn processes.
- Use `GET /preflight/check?verify_vendor=true` before real tests to validate config.

