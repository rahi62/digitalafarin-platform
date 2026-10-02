"""First service provisioning through fixed systemd policy, never caller commands."""
import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import socket
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from . import takeover_helper as legacy
from .health import check_http_health
from .releases import atomic_activate
from .takeover_worker import run_takeover_worker

RUNTIME_USER = 'digitalafarin-app'
KEYS = {'service_id', 'deployment_id', 'project_slug', 'service_name', 'repository', 'requested_ref',
        'exact_commit', 'runtime', 'root_directory', 'install_configuration', 'build_configuration',
        'service_port', 'health_path', 'environment', 'volumes'}


def fail(code, message):
    raise legacy.TakeoverHelperDomainError(code, message)


def validate_configuration(params):
    if not isinstance(params, dict) or set(params) != KEYS:
        fail('invalid_payload', 'Unsupported provisioning fields.')
    data = dict(params)
    try:
        for key in ('service_id', 'deployment_id'):
            data[key] = str(uuid.UUID(data[key]))
        legacy._validate_identity(data['project_slug'], data['service_name'])
        legacy._validate_root_directory(data['root_directory'])
        repo = urlsplit(legacy._validate_repository(data['repository']))
        if (repo.hostname not in {'github.com', 'gitlab.com', 'bitbucket.org'} or repo.port
                or not re.fullmatch(r'/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+', repo.path)
                or any(part in {'.', '..'} for part in repo.path.split('/'))):
            raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,254}', data['requested_ref']) or any(
                x in data['requested_ref'] for x in ('..', '//')) or data['requested_ref'].endswith(('/', '.', '.lock')):
            raise ValueError()
        if data['exact_commit'] and not re.fullmatch(r'[a-f0-9]{40}', data['exact_commit']):
            raise ValueError()
        if type(data['service_port']) is not int or not 1024 <= data['service_port'] <= 65535:
            raise ValueError()
        if not re.fullmatch(r'/(?:[A-Za-z0-9_.~-]+/?)*', data['health_path']):
            raise ValueError()
        if data['runtime'] != 'node-nextjs' or data['environment'] != {} or data['volumes'] != []:
            raise ValueError()
        if data['install_configuration'] != {'package_manager': 'npm', 'lockfile': 'package-lock.json'}:
            raise ValueError()
        if set(data['build_configuration']) != {'build_script'} or not re.fullmatch(r'[A-Za-z0-9:_-]+', data['build_configuration']['build_script']):
            raise ValueError()
    except (ValueError, TypeError, AttributeError, KeyError):
        fail('invalid_configuration', 'Invalid provisioning configuration.')
    return data


def render_unit(data, root):
    workdir = root / 'current' / data['root_directory']
    return (
        f"# DigitalAfarin service={data['service_id']}\n"
        '[Unit]\nDescription=DigitalAfarin managed application\nAfter=network.target\n\n'
        f'[Service]\nType=simple\nUser={RUNTIME_USER}\nGroup={RUNTIME_USER}\n'
        f'WorkingDirectory={workdir}\n'
        f'ExecStart=/usr/bin/node {workdir}/node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port {data["service_port"]}\n'
        'Environment=NODE_ENV=production\nRestart=on-failure\nRestartSec=5\n'
        'NoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nProtectHome=true\n'
        'ProtectKernelTunables=true\nProtectKernelModules=true\nProtectControlGroups=true\n'
        'RestrictSUIDSGID=true\nCapabilityBoundingSet=\nUMask=0027\n'
        f'ReadWritePaths={workdir}/.next/cache\n'
        'MemoryMax=1G\nTasksMax=256\n\n[Install]\nWantedBy=multi-user.target\n'
    )


def systemctl(*args):
    try:
        subprocess.run(['/usr/bin/systemctl', *args], check=True, capture_output=True,
                       text=True, timeout=60, shell=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise legacy.TakeoverHelperDomainError('systemd_failed', 'Managed systemd operation failed.') from exc


def resolve_commit(data):
    if data['exact_commit']:
        return data['exact_commit']
    ref = data['requested_ref']
    if re.fullmatch('[a-f0-9]{40}', ref):
        return ref
    output = run_takeover_worker(phase='resolve_commit', user=RUNTIME_USER, group=RUNTIME_USER,
                                argv=['git', '-c', 'http.followRedirects=false', 'ls-remote', '--exit-code', '--refs',
                                      data['repository'], f'refs/heads/{ref}'], timeout=60)
    lines = output.splitlines()
    if len(lines) != 1 or not re.fullmatch('[a-f0-9]{40}', lines[0].split()[0]):
        fail('git_ref_unresolved', 'Repository branch did not resolve to one commit.')
    return lines[0].split()[0]


def assert_port_available(port):
    try:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    except OSError as exc:
        raise legacy.TakeoverHelperDomainError('port_conflict', 'Service port is already in use.') from exc


def _write(path, text, mode=0o600):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.platform-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def provision_service(params, *, apps_root=Path('/srv/digitalafarin/apps'), systemd_root=Path('/etc/systemd/system'), _mode='provision', _release_name=None):
    data = validate_configuration(params)
    root = legacy._service_root(apps_root, data['project_slug'], data['service_name'])
    for child in ('releases', 'shared', '.platform'):
        if (root / child).is_symlink():
            fail('unsafe_path', 'Managed path cannot be a symlink.')
    account = legacy._account(RUNTIME_USER)
    if account.pw_uid == 0:
        fail('unsafe_runtime', 'Application runtime must not be root.')
    root = legacy._ensure_release_directories(apps_root, data['project_slug'], data['service_name'], user=RUNTIME_USER, group=RUNTIME_USER)
    metadata = root / '.platform'
    metadata.mkdir(mode=0o700, exist_ok=True)
    info = metadata.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        fail('unsafe_path', 'Invalid managed metadata ownership.')
    fd = os.open(metadata / 'lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if _mode == 'provision':
            return _provision_locked(data, root, metadata, apps_root, systemd_root)
        return _deploy_locked(data, root, metadata, apps_root, systemd_root, _release_name)
    finally:
        os.close(fd)


def _provision_locked(data, root, metadata, apps_root, systemd_root):
    journal = metadata / f"{data['deployment_id']}.json"
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    unit_name = f"digitalafarin-app-{uuid.UUID(data['service_id']).hex}.service"
    unit = systemd_root / unit_name
    if journal.exists():
        previous = json.loads(journal.read_text())
        if previous['fingerprint'] != fingerprint:
            fail('request_changed', 'Provisioning request changed during retry.')
        if previous.get('result'):
            return previous['result']
        fail('reconciliation_required', 'Interrupted provisioning requires host inspection before retry.')
    if unit.exists() or unit.is_symlink() or (root / 'current').exists() or (root / 'current').is_symlink():
        fail('workload_exists', 'Refusing to replace an existing workload.')
    usage = shutil.disk_usage(root)
    if usage.used / usage.total >= 0.9:
        fail('disk_full', 'Disk usage blocks provisioning.')
    assert_port_available(data['service_port'])
    _write(journal, json.dumps({'fingerprint': fingerprint, 'state': 'building'}))
    created_unit = False
    release = None
    try:
        commit = resolve_commit(data)
        built = legacy._build_node_release(root, apps_root, data['project_slug'], data['service_name'],
                                           data['repository'], commit, data['root_directory'], data['install_configuration'],
                                           data['build_configuration'], RUNTIME_USER, RUNTIME_USER, {})
        release = legacy._release_path(root, built['release_name'])
        _write(journal, json.dumps({'fingerprint': fingerprint, 'state': 'prepared', 'release_name': release.name}))
        # O_EXCL prevents overwrite even if a foreign unit appears after preflight.
        unit_fd = os.open(unit, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        created_unit = True
        with os.fdopen(unit_fd, 'w', encoding='utf-8') as stream:
            stream.write(render_unit(data, root))
            stream.flush()
            os.fsync(stream.fileno())
        atomic_activate(root, release)
        systemctl('daemon-reload')
        systemctl('enable', '--now', unit_name)
        systemctl('is-active', '--quiet', unit_name)
        check_http_health({'url': f"http://127.0.0.1:{data['service_port']}{data['health_path']}", 'attempts': 12, 'timeout_seconds': 5, 'interval_seconds': 2})
        result = {'final_state': 'succeeded', 'deployment_id': data['deployment_id'], 'release_name': release.name,
                  'exact_commit': commit, 'unit_name': unit_name, 'events': [
                      {'state': stage, 'message': ''} for stage in
                      ['preparing', 'cloning', 'building', 'releasing', 'health_check', 'activating', 'verifying', 'succeeded']]}
        _write(metadata / 'service.json', json.dumps({'service_id': data['service_id'], 'configuration': data, 'release_name': release.name}))
        _write(journal, json.dumps({'fingerprint': fingerprint, 'state': 'succeeded', 'result': result}))
        return result
    except Exception as exc:
        # Cleanup only this freshly-created identity. A failed stop leaves evidence
        # and the release intact; never delete files of a potentially live process.
        if created_unit:
            try:
                systemctl('disable', '--now', unit_name)
            except Exception:
                fail('cleanup_failed', 'Could not stop new workload; inspect host before retry.')
            unit.unlink(missing_ok=True)
            systemctl('daemon-reload')
        current = root / 'current'
        if release is not None and current.is_symlink() and current.resolve() == release:
            current.unlink()
        if release is not None and release.exists() and not release.is_symlink():
            shutil.rmtree(release)
        # Known failure is retryable with a NEW operation; this attempt remains failed.
        _write(journal, json.dumps({'fingerprint': fingerprint, 'state': 'failed'}))
        if isinstance(exc, legacy.TakeoverHelperDomainError):
            raise
        raise legacy.TakeoverHelperDomainError('provisioning_failed', 'Provisioning failed; previous services were preserved.') from exc


def deploy_service(params, **options):
    return provision_service(params, _mode='deploy', **options)


def rollback_service(params, **options):
    data = dict(params)
    name = legacy._validate_release_name(data.pop('release_name', None))
    return provision_service(data, _mode='rollback', _release_name=name, **options)


def _read_metadata(path):
    if path.is_symlink() or not path.is_file():
        fail('managed_metadata_missing', 'Managed service metadata is unavailable.')
    info = path.stat()
    if info.st_uid != 0 or info.st_mode & 0o077:
        fail('unsafe_metadata', 'Managed metadata must be private and root-owned.')
    return json.loads(path.read_text())


def _deployment_result(data, release, commit, final_state):
    return {'final_state': final_state, 'deployment_id': data['deployment_id'],
            'release_name': release.name, 'exact_commit': commit,
            'events': [{'state': stage, 'message': ''} for stage in
                       ['preparing', 'cloning', 'building', 'releasing', 'health_check', 'activating', 'verifying', final_state]]}


def _deploy_locked(data, root, metadata, apps_root, systemd_root, rollback_name):
    owned = _read_metadata(metadata / 'service.json')
    original = owned['configuration']
    for key in ('service_id', 'project_slug', 'service_name', 'repository', 'runtime', 'root_directory', 'service_port'):
        if data[key] != original[key]:
            fail('managed_binding_changed', 'Managed workload identity or configuration changed.')
    unit_name = f"digitalafarin-app-{uuid.UUID(data['service_id']).hex}.service"
    unit = systemd_root / unit_name
    if unit.is_symlink() or not unit.is_file() or unit.stat().st_uid != 0 or unit.stat().st_mode & 0o022 or unit.read_text() != render_unit(original, root):
        fail('managed_unit_changed', 'Managed systemd unit was changed outside the platform.')
    journal = metadata / f"{data['deployment_id']}.json"
    fingerprint = hashlib.sha256(json.dumps({'configuration': data, 'rollback': rollback_name}, sort_keys=True).encode()).hexdigest()
    if journal.exists():
        attempt = _read_metadata(journal)
        if attempt['fingerprint'] != fingerprint:
            fail('request_changed', 'Deployment request changed during retry.')
        if attempt.get('result'):
            return attempt['result']
        fail('reconciliation_required', 'Interrupted deployment requires reconciliation.')
    previous = legacy._validate_previous_current(root)
    if previous is None:
        fail('managed_current_missing', 'Managed current release is unavailable.')
    legacy._validate_retained_release(previous, root, data['root_directory'])
    if not rollback_name:
        usage = shutil.disk_usage(root)
        if usage.used / usage.total >= .9:
            fail('disk_full', 'Disk usage blocks deployment.')
    _write(journal, json.dumps({'fingerprint': fingerprint, 'state': 'building', 'previous_release_name': previous.name}))
    release = None
    activated = False
    try:
        if rollback_name:
            release = legacy._release_path(root, rollback_name)
            legacy._validate_retained_release(release, root, data['root_directory'])
            commit = (release / '.git/HEAD').read_text().strip()
            if commit != data['exact_commit']:
                fail('commit_mismatch', 'Rollback commit does not match retained release.')
        else:
            commit = resolve_commit(data)
            built = legacy._build_node_release(root, apps_root, data['project_slug'], data['service_name'], data['repository'], commit,
                                               data['root_directory'], data['install_configuration'], data['build_configuration'], RUNTIME_USER, RUNTIME_USER, {})
            release = legacy._release_path(root, built['release_name'])
        _write(journal, json.dumps({'fingerprint': fingerprint, 'state': 'activating', 'release_name': release.name, 'previous_release_name': previous.name}))
        if legacy._validate_previous_current(root) != previous:
            fail('managed_current_changed', 'Current release changed during build.')
        atomic_activate(root, release)
        activated = True
        systemctl('restart', unit_name)
        systemctl('is-active', '--quiet', unit_name)
        check_http_health({'url': f"http://127.0.0.1:{data['service_port']}{data['health_path']}"})
        result = _deployment_result(data, release, commit, 'succeeded')
        _write(metadata / 'service.json', json.dumps({**owned, 'release_name': release.name}))
        _write(journal, json.dumps({'fingerprint': fingerprint, 'state': 'succeeded', 'result': result}))
    except Exception:
        if activated:
            atomic_activate(root, previous)
            systemctl('restart', unit_name)
            check_http_health({'url': f"http://127.0.0.1:{data['service_port']}{data['health_path']}"})
            result = _deployment_result(data, release, commit, 'rolled_back')
            _write(journal, json.dumps({'fingerprint': fingerprint, 'state': 'rolled_back', 'result': result}))
        else:
            _write(journal, json.dumps({'fingerprint': fingerprint, 'state': 'failed'}))
            raise
        if release != previous and not rollback_name:
            shutil.rmtree(release)
        return result
    # Retention is best-effort after durable success; it must not turn a healthy
    # activation into a failure. Validate every candidate before any deletion.
    try:
        candidates = []
        for item in (root / 'releases').iterdir():
            if legacy.RELEASE_NAME.fullmatch(item.name):
                try:
                    candidate = legacy._release_path(root, item.name)
                    legacy._validate_retained_release(candidate, root, data['root_directory'])
                    candidates.append(candidate)
                except (OSError, legacy.TakeoverHelperDomainError):
                    logging.warning('Skipping invalid retained release during cleanup.')
        protected = {previous, release}
        old = sorted((p for p in candidates if p not in protected), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        for item in old[max(0, 5 - len(protected)):]:
            try:
                shutil.rmtree(item)
            except OSError:
                logging.warning('Failed to remove an old managed release.')
    except (OSError, legacy.TakeoverHelperDomainError):
        logging.warning('Managed release cleanup could not complete.')
    return result
