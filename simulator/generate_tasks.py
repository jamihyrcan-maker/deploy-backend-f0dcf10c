from __future__ import annotations

import argparse
import json
import random
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta


def request(method: str, url: str, api_key: str, body: dict | None = None):
    headers = {"X-API-Key": api_key}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", "ignore")
        return resp.status, raw


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate random tasks for queue testing.")
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="App base URL")
    ap.add_argument("--api-key", default="dev-admin-key", help="X-API-Key")
    ap.add_argument("--robot-id", default="SIM-ROBOT-1", help="Robot id for POI lookup")
    ap.add_argument("--count", type=int, default=10, help="Number of tasks (or tables when --sequence)")
    ap.add_argument("--title-prefix", default="SimTask", help="Title prefix")
    ap.add_argument("--task-type", default="", help="Task type (legacy single type)")
    ap.add_argument(
        "--task-types",
        default="NAVIGATE,ORDERING,DELIVERY,CLEANUP",
        help="Comma-separated list of task types to mix",
    )
    ap.add_argument(
        "--sequence",
        action="store_true",
        help="Create ordered workflow per table: ORDERING -> DELIVERY -> CLEANUP with release_at times",
    )
    ap.add_argument("--sequence-gap", type=float, default=15.0, help="Seconds between sequential tasks")
    ap.add_argument(
        "--restaurant",
        action="store_true",
        help="Restaurant mode: staged ordering then delivery then cleanup per table",
    )
    ap.add_argument("--arrival-gap", type=float, default=10.0, help="Seconds between new table orders")
    ap.add_argument("--delivery-gap", type=float, default=120.0, help="Seconds after order before delivery")
    ap.add_argument("--cleanup-gap", type=float, default=180.0, help="Seconds after delivery before cleanup")
    ap.add_argument("--target-kind", default="POI", help="Target kind")
    args = ap.parse_args()

    # fetch POIs
    status, raw = request(
        "GET",
        f"{args.base}/robot-api/robots/{args.robot_id}/pois",
        args.api_key,
    )
    if status != 200:
        print("Failed to fetch POIs:", status, raw)
        return 1
    pois = json.loads(raw)
    if not isinstance(pois, list) or not pois:
        print("No POIs available")
        return 1

    poi_ids = [p.get("id") for p in pois if isinstance(p, dict) and p.get("id")]
    if not poi_ids:
        print("No POI ids found")
        return 1
    table_refs = []
    for p in pois:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or p.get("id") or "")
        kind = str(p.get("kind") or "")
        if kind.upper() == "TABLE" or "table" in name.lower():
            m = re.search(r"(\d+)", name)
            if m:
                table_refs.append(m.group(1))
    if not table_refs:
        table_refs = ["1"]
    table_refs = sorted(table_refs, key=lambda x: int(re.sub(r"\\D", "", x) or 0))

    if args.restaurant:
        max_tables = args.count if args.count > 0 else len(table_refs)
        table_refs = table_refs[:max_tables]
        now = datetime.now(timezone.utc)
        for i, tref in enumerate(table_refs):
            order_time = now + timedelta(seconds=i * args.arrival_gap)
            delivery_time = order_time + timedelta(seconds=args.delivery_gap)
            cleanup_time = delivery_time + timedelta(seconds=args.cleanup_gap)

            for task_type, when in (
                ("ORDERING", order_time),
                ("DELIVERY", delivery_time),
                ("CLEANUP", cleanup_time),
            ):
                params = {
                    "title": f"{args.title_prefix}-T{tref}-{task_type}",
                    "task_type": task_type,
                    "target_kind": "TABLE",
                    "target_ref": tref,
                    "release_at": when.isoformat(),
                }
                url = f"{args.base}/task-manager/tasks?" + urllib.parse.urlencode(params)
                status, raw = request("POST", url, args.api_key)
                print(status, raw)
        return 0

    if args.sequence:
        max_tables = args.count if args.count > 0 else len(table_refs)
        table_refs = table_refs[:max_tables]
        now = datetime.now(timezone.utc)
        offset = 0.0
        for tref in table_refs:
            for task_type in ("ORDERING", "DELIVERY", "CLEANUP"):
                release_at = (now + timedelta(seconds=offset)).isoformat()
                offset += args.sequence_gap
                params = {
                    "title": f"{args.title_prefix}-T{tref}-{task_type}",
                    "task_type": task_type,
                    "target_kind": "TABLE",
                    "target_ref": tref,
                    "release_at": release_at,
                }
                url = f"{args.base}/task-manager/tasks?" + urllib.parse.urlencode(params)
                status, raw = request("POST", url, args.api_key)
                print(status, raw)
        return 0

    types = [t.strip().upper() for t in args.task_types.split(",") if t.strip()]
    if args.task_type and args.task_type.strip():
        types = [args.task_type.strip().upper()]

    for i in range(args.count):
        task_type = random.choice(types) if types else "NAVIGATE"
        if task_type in ("ORDERING", "DELIVERY", "CLEANUP"):
            target_kind = "TABLE"
            target_ref = random.choice(table_refs)
        else:
            target_kind = args.target_kind
            target_ref = random.choice(poi_ids)
        title = f"{args.title_prefix}-{i+1}"
        params = {
            "title": title,
            "task_type": task_type,
            "target_kind": target_kind,
            "target_ref": target_ref,
        }
        url = f"{args.base}/task-manager/tasks?" + urllib.parse.urlencode(params)
        status, raw = request("POST", url, args.api_key)
        print(status, raw)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
