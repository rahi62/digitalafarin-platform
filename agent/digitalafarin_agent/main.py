import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI

from . import __version__
from .config import get_settings
from .control_plane import AgentControlPlaneClient
from .heartbeat import HeartbeatRunner
from .identity import AgentIdentityStore
from .operation_journal import OperationJournal
from .metrics import collect_metrics
from .security import require_agent_token
from .systemd import list_services


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    task = None
    client = None
    if settings.platform_control_url:
        client = AgentControlPlaneClient(settings.platform_control_url)
        runner = HeartbeatRunner(
            client=client,
            identity_store=AgentIdentityStore(settings.agent_token_path),
            enrollment_token=settings.platform_enrollment_token,
            agent_name=settings.agent_name,
            interval_seconds=settings.agent_heartbeat_interval_seconds,
            operation_journal=OperationJournal(settings.agent_token_path.parent / 'operation.json'),
        )
        task = asyncio.create_task(runner.run_forever())
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if client:
            await client.close()


app = FastAPI(
    title="DigitalAfarin Host Agent",
    version=__version__,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "digitalafarin-host-agent",
        "version": __version__,
    }


@app.get("/v1/metrics", dependencies=[Depends(require_agent_token)])
def metrics() -> dict:
    return collect_metrics()


@app.get("/v1/services", dependencies=[Depends(require_agent_token)])
def services() -> dict:
    return {"items": list_services()}
