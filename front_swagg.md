# Frontend Swagger Guide (Front‑Facing Endpoints)

This file lists the **Swagger endpoints your frontend should use**, in a clean order, with what they do and how to call them safely.

Swagger UI: `http://127.0.0.1:8000/docs`

## Auth (required)
Most endpoints require `X-API-Key`. **Do not expose `dev-admin-key` in the browser.**
Use a proxy or a limited key for frontend.

## WebSocket (live updates)
**Connect:** `ws://127.0.0.1:8000/ws?api_key=YOUR_KEY`

Events to listen for:
- `system.updated` — system state changed
- `task.created`, `task.status_changed` — task lifecycle updates
- `workflow.needs_confirm`, `workflow.confirmed` — manual confirm flow
- `poi.cache_updated` — cached POIs updated
- `robot.state_updated` / `robot.state_error` — live robot telemetry

When you receive a WS event, re‑fetch the REST endpoint below for latest data.

---

# 1) Dashboard / Aggregated

### GET `/dashboard/overview`
**Use:** main overview for UI (tasks + running workflows + robots)
**Why:** single call to populate dashboard
**Notes:** refresh on `system.updated`

---

# 2) Tasks

### GET `/task-manager/tasks`
**Use:** list tasks (queue, history, audit)
**Important params:** `limit`, `offset`
**Notes:** frontend read‑only unless you build operator UI

### GET `/task-manager/tasks/{task_id}`
**Use:** task detail page

---

# 3) Queue

### GET `/queue-manager/queue`
**Use:** live ready queue list (what will be assigned next)

### GET `/queue-manager/stats`
**Use:** show counts by status (PENDING/READY/ASSIGNED/DONE/CANCELED)

---

# 4) Workflow

### GET `/workflow-engine/runs`
**Use:** list active workflow runs

### GET `/workflow-engine/runs/{run_id}`
**Use:** run steps / current step / confirm status

### POST `/workflow-engine/runs/{run_id}/confirm`
**Use:** operator confirm button
**Body:** `{ "decision": "CONFIRM", "payload": {} }`

---

# 5) Robot State

### GET `/robot-monitor/states`
**Use:** recent robot state snapshots

### GET `/assignment/robots`
**Use:** robot availability + eligibility
**Params:** `include_state=true` for full state

---

# 6) POI Cache (maps for UI)

### GET `/poi-cache/pois`
**Use:** cached POIs for map rendering
**Optional:** `robot_id=SIM-ROBOT-1`
**Notes:** updated automatically every 2 hours; also via `poi.cache_updated` WS event

---

# 7) Optional Operator Controls (only if you build admin UI)

### POST `/task-manager/tasks`
**Use:** create a task (operator UI)
**Method:** query parameters (not JSON body)

### POST `/orchestrator/tick`
**Use:** run assignment/queue/workflow tick
**Only for admin / simulation**

---

# Cautions

- Never expose admin keys in frontend code.
- Prefer `GET` endpoints for frontend displays.
- Use WebSocket for real‑time updates, REST for data payloads.

