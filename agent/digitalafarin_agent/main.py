from fastapi import Depends, FastAPI

from . import __version__
from .metrics import collect_metrics
from .security import require_agent_token
from .systemd import list_services

app = FastAPI(
    title="DigitalAfarin Host Agent",
    version=__version__,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "digitalafarin-host-agent", "version": __version__}


@app.get("/v1/metrics", dependencies=[Depends(require_agent_token)])
def metrics() -> dict:
    return collect_metrics()


@app.get("/v1/services", dependencies=[Depends(require_agent_token)])
def services() -> dict:
    return {"items": list_services()}
