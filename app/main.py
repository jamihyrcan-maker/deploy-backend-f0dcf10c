from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .assignment_engine.robots import get_robot_ids
from .auto_confirm.runner import AutoConfirmRunner
from .auto_tick.runner import AutoTickRunner
from .common.logging import configure_logging
from .common.middleware import RequestIdMiddleware
from .common.vendor_resilience import RetryingRobotAPIService, RetryingTaskClient
from .controls.router import router as controls_router
from .dashboard.router import router as dashboard_router
from .persistence.db import init_db
from .poi_cache.poller import PoiCachePoller
from .poi_cache.router import router as poi_cache_router
from .poi_mapping.router import router as poi_mapping_router
from .preflight.router import router as preflight_router
from .priority_manager.router import router as priority_router
from .queue_manager.router import router as queue_manager_router
from .realtime_bus.router import router as realtime_bus_router
from .robot_api.autox_client import AutoXingClient, AutoXingConfig
from .robot_api.router import get_robot_api_service, router as robot_api_router
from .robot_api.service import RobotAPIService
from .robot_monitor.poller import RobotStatePoller
from .robot_monitor.router import router as robot_monitor_router
from .task_manager.router import router as task_manager_router
from .workflow_engine.router import get_task_client, router as workflow_engine_router
from .workflow_engine.vendor_task_client import AutoXingTaskClient

# Optional routers (won't crash if module doesn't exist yet)
try:
    from .assignment_engine.router import router as assignment_router
except Exception:
    assignment_router = None

try:
    from .orchestrator.router import router as orchestrator_router
except Exception:
    orchestrator_router = None


def _cors_origins_from_env() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*")
    origins = [x.strip() for x in raw.split(",") if x.strip()]
    return origins or ["*"]


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Backend - Robot API + Tasks/Queue/Priority + Workflow + WS + Dashboard + Monitor + Controls",
    )

    # Request correlation
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins_from_env(),
        allow_credentials=os.getenv("CORS_ALLOW_CREDENTIALS", "0") == "1",
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Init DB tables (SQLite)
    init_db()

    # Shared vendor config
    cfg = AutoXingConfig()

    # Vendor clients (wrapped with retry/timeout)
    vendor_read = AutoXingClient(cfg)
    robot_svc = RetryingRobotAPIService(RobotAPIService(vendor_read))
    app.dependency_overrides[get_robot_api_service] = lambda: robot_svc

    vendor_tasks = RetryingTaskClient(AutoXingTaskClient(cfg))
    app.dependency_overrides[get_task_client] = lambda: vendor_tasks

    # Routers
    app.include_router(robot_api_router)

    app.include_router(task_manager_router)
    app.include_router(priority_router)
    app.include_router(queue_manager_router)

    app.include_router(poi_mapping_router)
    app.include_router(workflow_engine_router)

    if assignment_router:
        app.include_router(assignment_router)
    if orchestrator_router:
        app.include_router(orchestrator_router)

    app.include_router(realtime_bus_router)
    app.include_router(dashboard_router)

    app.include_router(robot_monitor_router)
    app.include_router(controls_router)
    app.include_router(poi_cache_router)
    app.include_router(preflight_router)

    # ---- Background services ----
    interval_s = float(os.getenv("ROBOT_POLL_INTERVAL", "5"))
    poi_interval_s = float(os.getenv("POI_CACHE_INTERVAL_S", "7200"))
    poi_enabled = os.getenv("POI_CACHE_ENABLED", "1") == "1"

    @app.on_event("startup")
    async def _startup():
        # Robot monitor poller
        ids = get_robot_ids()
        poller = RobotStatePoller(robot_svc, ids, interval_s=interval_s)
        app.state.robot_state_poller = poller
        await poller.start()

        # POI cache poller
        if poi_enabled:
            poi_poller = PoiCachePoller(robot_svc, ids, interval_s=poi_interval_s)
            app.state.poi_cache_poller = poi_poller
            await poi_poller.start()

        # Optional AutoTick runner
        runner = AutoTickRunner()
        app.state.auto_tick_runner = runner
        await runner.start()

        # Optional AutoConfirm runner
        confirm_runner = AutoConfirmRunner()
        app.state.auto_confirm_runner = confirm_runner
        await confirm_runner.start()

    @app.on_event("shutdown")
    async def _shutdown():
        poller = getattr(app.state, "robot_state_poller", None)
        if poller:
            await poller.stop()

        poi_poller = getattr(app.state, "poi_cache_poller", None)
        if poi_poller:
            await poi_poller.stop()

        runner = getattr(app.state, "auto_tick_runner", None)
        if runner:
            await runner.stop()

        confirm_runner = getattr(app.state, "auto_confirm_runner", None)
        if confirm_runner:
            await confirm_runner.stop()

    return app


app = create_app()
