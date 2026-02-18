# Codex Swagger Guide 

If you follow this **exact order**, you will not break anything.

---

## 0) One?time setup (30 seconds)

1) Open Swagger: `http://127.0.0.1:8000/docs`
2) Click **Authorize** (top right)
3) Enter:
   - **X-API-Key** = `dev-admin-key`
4) Click **Authorize** and close the dialog.

If you skip this, many calls return 401.

---

## 1) SAFE DEMO FLOW (NO ROBOT MOVEMENT)

Do these in order. Copy?paste values exactly.

### 1.1 GET /preflight/check
- Click **Try it out** ? **Execute**
- Optional param: `verify_vendor` = `true`
- You should see `"ok": true` or config details.

### 1.2 GET /robot-api/robots/{robot_id}/state
- robot_id = `8982507c06180BG`
- Click **Execute**

### 1.3 GET /robot-api/robots/{robot_id}/pois
- robot_id = `8982507c06180BG`
- Click **Execute**
- Copy a `poi_id` from the response (you will use it below).

### 1.3b GET /poi-cache/pois
- Use this to read the cached POIs (from the 2-hour poller).
- Optional: `robot_id` = `8982507c06180BG`
- Click **Execute**

### 1.4 POST /poi-mapping/auto-map
Body (JSON):
```
{
  "robot_id": "8982507c06180BG",
  "table_count": 5,
  "ref_prefix": ""
}
```

### 1.5 GET /poi-mapping/mappings
- Just Execute

### 1.6 POST /poi-mapping/mappings
Body (JSON) (use the poi_id you copied):
```
{
  "kind": "TABLE",
  "ref": "SMOKE1",
  "poi_id": "<PASTE_POI_ID>",
  "area_id": null,
  "label": "Smoke Table"
}
```

### 1.7 GET /poi-mapping/mappings/{kind}/{ref}
- kind = `TABLE`
- ref = `SMOKE1`

### 1.8 DELETE /poi-mapping/mappings/{kind}/{ref}
- kind = `TABLE`
- ref = `SMOKE1`

### 1.9 POST /task-manager/tasks  ? IMPORTANT
This one uses **QUERY PARAMETERS**, not JSON body.

Fill these query params:
- title = `DemoTask`
- task_type = `NAVIGATE`
- target_kind = `POI`
- target_ref = `<PASTE_POI_ID>`

Then Execute. Copy the `id` from the response.

### 1.10 GET /task-manager/tasks
- Execute

### 1.11 GET /task-manager/tasks/{task_id}
- task_id = `<PASTE_TASK_ID>`

### 1.12 PATCH /task-manager/tasks/{task_id}
Query params:
- title = `DemoTask Updated`

### 1.13 PATCH /task-manager/tasks/{task_id}/status
Query params:
- status = `READY`

### 1.14 POST /priority/override
Body (JSON):
```
{
  "task_id": <PASTE_TASK_ID>,
  "override": 5,
  "reason": "demo"
}
```

### 1.15 DELETE /priority/override/{task_id}
- task_id = `<PASTE_TASK_ID>`

### 1.16 POST /queue-manager/tick
- Execute

### 1.17 GET /queue-manager/queue
- Execute

### 1.18 GET /queue-manager/stats
- Execute

### 1.19 GET /workflow-engine/runs
- Execute

### 1.20 POST /workflow-engine/tick
- Execute

### 1.21 GET /assignment/robots
- include_state = `true`

### 1.22 GET /assignment/assignments
- Execute

### 1.23 GET /realtime-bus/health
- Execute

### 1.24 POST /realtime-bus/publish
Body (JSON):
```
{
  "type": "demo.hello",
  "data": {"ok": true},
  "source": "swagger"
}
```

### 1.24b WebSocket for live POI updates (not in Swagger UI)
- Connect: `ws://127.0.0.1:8000/ws?api_key=dev-admin-key`
- You will receive events like:
  - `poi.cache_updated` (payload includes robot_id, created/updated/deleted counts)
- When you receive that event, call **GET /poi-cache/pois** to refresh the list.

### 1.25 GET /dashboard/overview
- Execute

### 1.26 GET /robot-monitor/states
- Execute

### 1.27 POST /controls/tasks/{task_id}/cancel
- task_id = `<PASTE_TASK_ID>`
- reason (optional) = `demo done`

---

## 2) DO NOT RUN (ROBOT MOVEMENT)

**Do not click these unless you are ready to move a robot**

- POST /workflow-engine/runs
- POST /assignment/assign-next
- POST /orchestrator/tick
- POST /controls/vendor-task/{vendor_task_id}/cancel

---

## 3) Common mistakes and fixes

- **401 Unauthorized** ? you forgot Authorize (X-API-Key)
- **422 error** on task create/update ? you used JSON body instead of query params
- **Robot moves** ? you ran unsafe endpoints or SAFE_MODE=0 in real environment

---

## 4) Safety mode (optional)

If you want to guarantee no movement, set:
```
SAFE_MODE=1
```
Then unsafe endpoints will return an error instead of moving robots.
