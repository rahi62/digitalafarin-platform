# Architecture decision record — MVP 0.1

## Goal

Replace recurring SSH-only operational work with a safe internal control plane while preserving a strong security boundary.

## Components

### Next.js Admin
Presentation layer only. It never stores the host-agent token in browser JavaScript. Mutating browser requests go to Next.js route handlers, which call Django server-side.

### Django Control Plane
System of record for servers, service snapshots, deployments, domains, backups and audit events. In MVP 0.1 only server inventory sync is implemented.

### Python Host Agent
Small loopback-only process. It exposes typed endpoints and does not expose an arbitrary command endpoint. MVP 0.1 reads metrics and systemd inventory only.

## Security rules

1. No `shell=True`.
2. No free-form command strings from the API or browser.
3. Agent binds to loopback in the single-server MVP.
4. Service discovery is prefix allow-listed.
5. Browser never receives agent credentials.
6. Privileged actions are not implemented until RBAC + audit + approved helper boundary exist.
7. Nginx and deploy writes must use validate-before-switch semantics.
8. Rollback must be modeled as a first-class deployment operation, not an ad-hoc script.

## Future executor interface

```python
class ServiceExecutor(Protocol):
    def status(self, service_id: str): ...
    def restart(self, service_id: str): ...
    def stop(self, service_id: str): ...
    def start(self, service_id: str): ...

class DeploymentExecutor(Protocol):
    def build_release(self, deployment_id: str): ...
    def activate_release(self, release_id: str): ...
    def rollback(self, release_id: str): ...
```

The first implementation will target systemd. Docker/Compose can be added later without changing the web product model.
