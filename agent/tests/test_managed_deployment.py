import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from digitalafarin_agent import deployment, operations, releases
from digitalafarin_agent.executors.systemd import SystemdExecutor
from digitalafarin_agent import takeover_helper as h
from digitalafarin_agent.health import HealthCheckError
from digitalafarin_agent.takeover_helper_client import TakeoverHelperError


def test_managed_deployment_uses_helper_only(monkeypatch):
    calls = []
    class Helper:
        def prepare_managed_node_nextjs_release(self, params):
            calls.append(('prepare', params))
            return {'release_name': '20260923-120000-aaaaaaa', 'resolved_commit': 'a' * 40}
        def activate_managed_release(self, params):
            calls.append(('activate', params))
            return {'previous_release_name': '20260922-120000-bbbbbbb'}
        def prune_managed_releases(self, params):
            calls.append(('prune', params))
            return {'removed': []}
    monkeypatch.setattr(deployment, 'check_http_health', lambda config: None)
    monkeypatch.setattr(releases, 'prepare_release', lambda *a, **k: (_ for _ in ()).throw(AssertionError('agent filesystem write')))
    result = deployment.deploy_managed_release({
        'deployment_id': '1', 'project_slug': 'project', 'service_name': 'web',
        'unit_name': 'web.service', 'repository': 'https://example.com/repo.git',
        'exact_commit': 'a' * 40, 'runtime': 'node-nextjs', 'health_check': {},
    }, helper=Helper())
    assert result['final_state'] == 'succeeded'
    assert [e['state'] for e in result['events']] == ['preparing', 'cloning', 'building', 'releasing', 'health_check', 'activating', 'verifying', 'succeeded']
    assert [c[0] for c in calls] == ['prepare', 'activate', 'prune']
    assert 'source_id' not in calls[0][1]



@pytest.fixture
def managed(tmp_path, monkeypatch):
    monkeypatch.setenv('DIGITALAFARIN_MANAGED_REPOSITORIES', 'project|web|web.service|https://example.com/repo.git')
    monkeypatch.setattr(h, 'inspect_service', lambda unit: {'unit_name': unit, 'user': 'nobody', 'group': 'nogroup'})
    apps = tmp_path / 'apps'
    root = apps / 'project' / 'web'
    releases = root / 'releases'
    releases.mkdir(parents=True)
    releases.chmod(0o755)
    def release(name, commit):
        target = releases / name
        (target / '.git').mkdir(parents=True)
        (target / '.git/HEAD').write_text(commit + '\n')
        (target / '.next/cache').mkdir(parents=True)
        (target / 'package.json').write_text('{}')
        (target / 'package-lock.json').write_text('{}')
        h._seal_release(target, root, runtime_gid=os.getgid(), writable_paths=(target / '.next/cache',))
        return target
    if os.geteuid() != 0:
        pytest.skip('Run as root in disposable Linux test environment for real ownership checks')
    old = release('20260922-120000-bbbbbbb', 'b' * 40)
    new = release('20260923-120000-aaaaaaa', 'a' * 40)
    (root / 'current').symlink_to(old)
    systemd = tmp_path / 'systemd'
    dropin = h.write_managed_dropin('web.service', root / 'current', systemd_root=systemd, apps_root=apps)
    restarts = []
    monkeypatch.setattr(h, 'restart_takeover_unit', lambda unit: restarts.append(unit))
    options = dict(allowed_bindings={('project', 'web', 'web.service')}, apps_root=apps, systemd_root=systemd)
    params = dict(project_slug='project', service_name='web', unit_name='web.service', root_directory='.')
    yield SimpleNamespace(**locals())
    for path in releases.rglob('*'):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else 0o644)


def activate(m):
    return h.activate_managed_release({**m.params, 'release_name': m.new.name, 'exact_commit': 'a' * 40}, **m.options)


def test_activation_and_rollback_preserve_dropin(managed):
    m = managed
    original = m.dropin.read_bytes()
    result = activate(m)
    assert result['previous_release_name'] == m.old.name
    assert (m.root / 'current').resolve() == m.new
    assert m.dropin.read_bytes() == original
    h.rollback_managed_activation({**m.params, 'release_name': m.new.name, 'previous_release_name': m.old.name}, **m.options)
    assert (m.root / 'current').resolve() == m.old
    assert m.dropin.read_bytes() == original
    assert m.restarts == ['web.service', 'web.service']


def test_restart_failure_restores_current(managed, monkeypatch):
    m = managed
    def restart(unit):
        m.restarts.append(unit)
        if len(m.restarts) == 1:
            raise RuntimeError('restart failed')
    monkeypatch.setattr(h, 'restart_takeover_unit', restart)
    with pytest.raises(h.TakeoverHelperDomainError, match='previous current restored'):
        activate(m)
    assert (m.root / 'current').resolve() == m.old
    assert m.dropin.exists()


@pytest.mark.parametrize('field,value', [('unit_name', 'other.service'), ('project_slug', 'other'), ('service_name', 'other'), ('release_name', '../../outside')])
def test_managed_activation_rejects_arbitrary_binding_or_path(managed, field, value):
    m = managed
    params = {**m.params, 'release_name': m.new.name, 'exact_commit': 'a' * 40, field: value}
    with pytest.raises(h.TakeoverHelperDomainError):
        h.activate_managed_release(params, **m.options)
    assert not m.restarts


def test_cleanup_active_and_escape_rejected(managed):
    m = managed
    identity = {k: m.params[k] for k in ('project_slug', 'service_name', 'unit_name')}
    options = {k: v for k, v in m.options.items() if k != 'systemd_root'}
    for name in (m.old.name, '../../outside'):
        with pytest.raises(h.TakeoverHelperDomainError):
            h.cleanup_release({**identity, 'release_name': name}, **options)
    outside = m.tmp_path / 'outside'
    outside.mkdir()
    alias = m.releases / '20260923-120001-aaaaaaa'
    alias.symlink_to(outside)
    with pytest.raises(h.TakeoverHelperDomainError):
        h.cleanup_release({**identity, 'release_name': alias.name}, **options)
    assert outside.exists()


def test_health_failure_restores_current_through_helper(managed, monkeypatch):
    m = managed
    class Helper:
        def prepare_managed_node_nextjs_release(self, params):
            return {'release_name': m.new.name, 'resolved_commit': 'a' * 40}
        def activate_managed_release(self, params):
            return h.activate_managed_release(params, **m.options)
        def rollback_managed_activation(self, params):
            return h.rollback_managed_activation(params, **m.options)
        def cleanup_release(self, params):
            return h.cleanup_release(params, **{k: v for k, v in m.options.items() if k != 'systemd_root'})
    checks = []
    def health(config):
        checks.append(config)
        if len(checks) == 1:
            raise HealthCheckError('unhealthy')
    monkeypatch.setattr(deployment, 'check_http_health', health)
    result = deployment.deploy_managed_release({**m.params, 'deployment_id': '1', 'repository': 'https://example.com/repo.git', 'runtime': 'node-nextjs', 'exact_commit': 'a' * 40, 'health_check': {}}, helper=Helper())
    assert result['final_state'] == 'rolled_back'
    assert (m.root / 'current').resolve() == m.old
    assert m.dropin.exists()
    assert not m.new.exists()


def test_managed_prepare_allocates_under_root_owned_0755(managed, monkeypatch):
    m = managed
    commands = []
    monkeypatch.setattr(h, 'inspect_service', lambda unit: {'unit_name': unit, 'user': 'nobody', 'group': 'nogroup'})
    def worker(user, group, argv, **kwargs):
        commands.append(argv)
        dest = kwargs['writable_path']
        if argv[:2] == ['git', 'clone']:
            assert argv[4] == 'https://example.com/repo.git'
            assert dest.stat().st_uid != 0
            assert m.releases.stat().st_uid == 0
            assert stat.S_IMODE(m.releases.stat().st_mode) == 0o755
            (dest / '.git').mkdir()
            (dest / '.git/HEAD').write_text('c' * 40 + '\n')
            (dest / 'package.json').write_text('{}')
            (dest / 'package-lock.json').write_text('{}')
            (dest / '.next').mkdir()
    monkeypatch.setattr(h, '_run_as_worker', worker)
    result = h.prepare_managed_node_nextjs_release({**m.params, 'repository': 'https://example.com/repo.git', 'exact_commit': 'c' * 40, 'runtime': 'node-nextjs', 'environment': {}, 'volumes': [], 'install_configuration': {'package_manager': 'npm', 'lockfile': 'package-lock.json'}, 'build_configuration': {'build_script': 'build'}}, **m.options)
    release = Path(result['release_path'])
    assert result['resolved_commit'] == 'c' * 40
    assert release.stat().st_uid == 0
    assert stat.S_IMODE(release.stat().st_mode) == 0o550
    assert commands[1][-1] == 'c' * 40
    assert not (m.releases.stat().st_mode & 0o022)


@pytest.mark.parametrize('field,value,code', [('environment', {'SECRET': 'value'}, 'managed_environment_unsupported'), ('volumes', [{'host_path': '/etc'}], 'managed_volumes_unsupported'), ('runtime', 'python', 'managed_runtime_unsupported'), ('exact_commit', 'main', 'invalid_exact_commit')])
def test_unsupported_payload_fails_explicitly(field, value, code):
    result = deployment.deploy_managed_release({'deployment_id': '1', 'project_slug': 'project', 'service_name': 'web', 'unit_name': 'web.service', 'runtime': 'node-nextjs', 'exact_commit': 'a' * 40, field: value}, helper=object())
    assert result['final_state'] == 'failed'
    assert result['error_code'] == code


def test_managed_helper_failure_keeps_bounded_diagnostic_message():
    class Helper:
        def prepare_managed_node_nextjs_release(self, params):
            raise TakeoverHelperError('release_validation_failed', 'Invalid managed releases root.')

    result = deployment.deploy_managed_release({
        'deployment_id': '1', 'project_slug': 'project', 'service_name': 'web',
        'unit_name': 'web.service', 'repository': 'https://example.com/repo.git',
        'runtime': 'node-nextjs', 'exact_commit': 'a' * 40,
    }, helper=Helper())
    assert result['error_code'] == 'release_validation_failed'
    assert result['error_message'] == 'Invalid managed releases root.'


def test_operation_routes_managed_deploy_and_preserves_failure_code(monkeypatch):
    monkeypatch.setattr(operations, 'deploy_managed_release', lambda payload: {'final_state': 'failed', 'error_code': 'managed_environment_unsupported', 'error_message': 'Managed environment updates are not supported.', 'events': [{'state': 'failed'}]})
    with pytest.raises(operations.OperationExecutionError) as exc:
        operations.execute_operation('deployment.deploy', {})
    assert exc.value.code == 'managed_environment_unsupported'
    assert str(exc.value) == 'Managed environment updates are not supported.'


def test_managed_missing_dropin_rejected(managed):
    m = managed
    m.dropin.unlink()
    with pytest.raises(h.TakeoverHelperDomainError) as exc:
        activate(m)
    assert exc.value.code == 'managed_dropin_missing'
    assert (m.root / 'current').resolve() == m.old


@pytest.mark.parametrize('change', ['writable', 'wrong_commit', 'root_directory'])
def test_managed_invalid_sealed_release_rejected(managed, change):
    m = managed
    params = {**m.params, 'release_name': m.new.name, 'exact_commit': 'a' * 40}
    if change == 'writable':
        (m.new / 'package.json').chmod(0o666)
    elif change == 'wrong_commit':
        params['exact_commit'] = 'a' * 7 + 'b' * 33
    else:
        params['root_directory'] = 'different'
    with pytest.raises(h.TakeoverHelperDomainError):
        h.activate_managed_release(params, **m.options)
    assert (m.root / 'current').resolve() == m.old
    assert not m.restarts


def test_cleanup_rejects_cross_service_alias(managed):
    m = managed
    alias = m.apps / 'project' / 'alias'
    alias.symlink_to(m.root)
    with pytest.raises(h.TakeoverHelperDomainError):
        h.cleanup_release({'project_slug': 'project', 'service_name': 'alias', 'unit_name': 'alias.service', 'release_name': m.new.name}, allowed_bindings={('project', 'alias', 'alias.service')}, apps_root=m.apps)
    assert m.new.exists()


def test_unprivileged_process_cannot_mutate_managed_files(managed):
    m = managed
    # A real unprivileged child demonstrates DAC denial; no fake chmod/chown.
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        os.chdir(m.root)
        dropin_fd = os.open(m.dropin.parent, os.O_RDONLY | os.O_DIRECTORY)
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)
        denied = 0
        actions = [
            lambda: Path('releases/unauthorized').mkdir(),
            lambda: Path('current').unlink(),
            lambda: os.open(m.dropin.name, os.O_WRONLY, dir_fd=dropin_fd),
            lambda: (Path('releases') / m.new.name / 'package.json').write_text('changed'),
        ]
        for action in actions:
            try:
                action()
            except PermissionError:
                denied += 1
        os.write(write_fd, str(denied).encode())
        os._exit(0)
    os.close(write_fd)
    assert os.read(read_fd, 20) == b'4'
    os.close(read_fd)
    assert os.waitpid(pid, 0)[1] == 0

@pytest.mark.parametrize('operation', [
    'prepare_managed_node_nextjs_release', 'activate_managed_release', 'rollback_managed_activation',
])
def test_managed_dispatch_enforces_binding(operation):
    params = {'project_slug': 'project', 'service_name': 'web', 'unit_name': 'other.service', 'root_directory': '.'}
    if operation.startswith('prepare'):
        params.update(repository='https://example.com/repo.git', exact_commit='a' * 40,
                      runtime='node-nextjs', environment={}, volumes=[],
                      install_configuration={}, build_configuration={})
    elif operation.startswith('activate'):
        params.update(release_name='20260923-120000-aaaaaaa', exact_commit='a' * 40)
    else:
        params.update(release_name='20260923-120000-aaaaaaa', previous_release_name='20260922-120000-bbbbbbb')
    with pytest.raises(h.TakeoverHelperDomainError) as exc:
        h.dispatch_helper_operation(operation, params, allowed_bindings={('project', 'web', 'web.service')})
    assert exc.value.code == 'helper_identity_not_allowed'


def test_rollback_refuses_to_overwrite_a_newer_activation(managed):
    m = managed
    with pytest.raises(h.TakeoverHelperDomainError) as exc:
        h.rollback_managed_activation({**m.params, 'release_name': m.new.name, 'previous_release_name': m.old.name}, **m.options)
    assert exc.value.code == 'managed_current_changed'
    assert not m.restarts
    assert (m.root / 'current').resolve() == m.old


def test_activation_detects_changed_current(managed, monkeypatch):
    m = managed
    real_activate = h.atomic_activate
    raced = m.release('20260921-120000-ccccccc', 'c' * 40)
    def concurrent_activate(root, release):
        if release == m.new:
            real_activate(root, raced)
        return real_activate(root, release)
    monkeypatch.setattr(h, 'atomic_activate', concurrent_activate)
    with pytest.raises(h.TakeoverHelperDomainError) as exc:
        activate(m)
    assert exc.value.code == 'managed_current_changed'
    assert (m.root / 'current').resolve() == raced
    assert m.dropin.exists()


def test_repository_must_match_trusted_binding(managed, monkeypatch):
    m = managed
    monkeypatch.setenv('DIGITALAFARIN_MANAGED_REPOSITORIES', 'project|web|web.service|https://example.com/trusted.git')
    params = {**m.params, 'repository': 'https://example.com/attacker.git', 'exact_commit': 'a' * 40, 'runtime': 'node-nextjs', 'environment': {}, 'volumes': [], 'install_configuration': {}, 'build_configuration': {}}
    with pytest.raises(h.TakeoverHelperDomainError) as exc:
        h.prepare_managed_node_nextjs_release(params, **m.options)
    assert exc.value.code == 'managed_repository_not_allowed'


def test_successful_retention_keeps_five_and_old_rollback_target(managed):
    m = managed
    for day in range(10, 20):
        m.release(f'202609{day}-120000-ccccccc', 'c' * 40)
    result = h.prune_managed_releases({**m.params, 'release_name': m.old.name, 'previous_release_name': m.new.name}, **m.options)
    assert len(list(m.releases.iterdir())) == 5
    assert m.old.exists() and m.new.exists()
    assert len(result['removed']) == 7


def test_manual_rollback_helper_preserves_dropin(managed):
    m = managed
    original = m.dropin.read_bytes()
    params = {k: v for k, v in m.params.items() if k != 'root_directory'}
    result = h.rollback_managed_release({**params, 'release_name': m.new.name, 'exact_commit': 'a' * 40}, **m.options)
    assert (m.root / 'current').resolve() == m.new
    assert result['previous_release_name'] == m.old.name
    assert m.dropin.read_bytes() == original
    assert m.restarts == ['web.service']


def test_manual_rollback_operation_routes_privileged_orchestrator(monkeypatch):
    monkeypatch.setattr(releases, 'rollback', lambda *a: pytest.fail('agent symlink mutation'))
    monkeypatch.setattr(operations, 'rollback_managed_release', lambda payload: {'final_state': 'succeeded'}, raising=False)
    assert operations.execute_operation('deployment.rollback', {}) == {'final_state': 'succeeded'}


@pytest.mark.parametrize('health_fails', [False, True])
def test_manual_rollback_orchestrator_checks_health_and_recovers(managed, monkeypatch, health_fails):
    m = managed
    original = m.dropin.read_bytes()
    checks = []
    class Helper:
        def rollback_managed_release(self, params):
            return h.rollback_managed_release(params, **m.options)
        def rollback_managed_activation(self, params):
            return h.rollback_managed_activation(params, **m.options)
        def prune_managed_releases(self, params):
            return h.prune_managed_releases(params, **m.options)
    def health(spec):
        checks.append(spec)
        if health_fails and len(checks) == 1:
            raise HealthCheckError('bad rollback target')
    monkeypatch.setattr(deployment, 'check_http_health', health)
    monkeypatch.setattr(releases, 'rollback', lambda *a: pytest.fail('agent mutation'))
    monkeypatch.setattr(SystemdExecutor, 'restart_managed', lambda *a: pytest.fail('agent restart'))
    base = '/srv/digitalafarin/apps/project/web'
    result = deployment.rollback_managed_release({
        'deployment_id': 'rollback-1', 'service_root': base,
        'release_path': base + '/releases/' + m.new.name, 'exact_commit': 'a' * 40,
        'unit_name': 'web.service', 'health_check': {'url': 'http://127.0.0.1'},
    }, helper=Helper())
    assert result['final_state'] == ('rolled_back' if health_fails else 'succeeded')
    assert len(checks) == (2 if health_fails else 1)
    assert (m.root / 'current').resolve() == (m.old if health_fails else m.new)
    assert m.dropin.read_bytes() == original
    assert m.old.exists() and m.new.exists()


@pytest.mark.parametrize('field,value', [
    ('release_name', '../../other/release'), ('release_name', '20260101-000000-ddddddd'),
    ('unit_name', 'arbitrary.service'), ('project_slug', 'other'), ('service_name', 'other'),
    ('exact_commit', 'b' * 40),
])
def test_manual_rollback_rejects_invalid_target_or_binding(managed, field, value):
    m = managed
    params = {k: v for k, v in m.params.items() if k != 'root_directory'}
    params.update(release_name=m.new.name, exact_commit='a' * 40)
    params[field] = value
    with pytest.raises((h.TakeoverHelperDomainError, FileNotFoundError)):
        h.rollback_managed_release(params, **m.options)
    assert (m.root / 'current').resolve() == m.old
    assert not m.restarts


@pytest.mark.parametrize('service_root,release_path', [
    ('/srv/digitalafarin/apps/project/web', '/srv/digitalafarin/apps/other/web/releases/r'),
    ('/tmp/project/web', '/tmp/project/web/releases/r'),
    ('/srv/digitalafarin/apps/project/web', '/srv/digitalafarin/apps/project/web/releases/../../r'),
])
def test_manual_rollback_payload_paths_rejected_without_helper(service_root, release_path):
    result = deployment.rollback_managed_release({
        'deployment_id': '1', 'exact_commit': 'a' * 40, 'service_root': service_root,
        'release_path': release_path, 'unit_name': 'web.service', 'health_check': {},
    }, helper=object())
    assert result['final_state'] == 'failed'


def test_retention_protects_old_previous_and_does_not_follow_aliases(managed):
    m = managed
    oldest = m.release('20260101-000000-ccccccc', 'c' * 40)
    for day in range(10, 20):
        m.release(f'202609{day}-120000-ddddddd', 'd' * 40)
    params = {**m.params, 'release_name': m.old.name, 'previous_release_name': oldest.name}
    outside = m.tmp_path / 'another-service'
    outside.mkdir()
    (outside / 'keep').write_text('important')
    alias = m.releases / '20260102-000000-eeeeeee'
    alias.symlink_to(outside)
    with pytest.raises(h.TakeoverHelperDomainError):
        h.prune_managed_releases(params, **m.options)
    assert (outside / 'keep').read_text() == 'important'
    assert len(list(m.releases.iterdir())) == 14
    alias.unlink()
    h.prune_managed_releases(params, **m.options)
    assert len(list(m.releases.iterdir())) == 5
    assert oldest.exists() and m.old.exists() and m.new.exists()


def test_retention_rejects_stale_current_without_deletion(managed):
    m = managed
    with pytest.raises(h.TakeoverHelperDomainError) as exc:
        h.prune_managed_releases({**m.params, 'release_name': m.new.name, 'previous_release_name': m.old.name}, **m.options)
    assert exc.value.code == 'managed_current_changed'
    assert m.old.exists() and m.new.exists()


def test_missing_managed_repository_fails_closed(managed, monkeypatch):
    m = managed
    monkeypatch.delenv('DIGITALAFARIN_MANAGED_REPOSITORIES')
    with pytest.raises(h.TakeoverHelperDomainError) as exc:
        h.prepare_managed_node_nextjs_release({**m.params, 'repository': 'https://example.com/repo.git', 'exact_commit': 'a' * 40, 'runtime': 'node-nextjs', 'environment': {}, 'volumes': [], 'install_configuration': {}, 'build_configuration': {}}, **m.options)
    assert exc.value.code == 'managed_repository_not_configured'
    assert len(list(m.releases.iterdir())) == 2


@pytest.mark.parametrize('raw', [
    'project|web|web.service',
    'project|web|web.service|https://example.com/repo.git,project|web|web.service|https://example.com/other.git',
    'project|web|web.service|file:///tmp/repo',
    'project|web|web.service|https://user:password@example.com/repo.git',
])
def test_managed_repository_configuration_rejects_unsafe_entries(monkeypatch, raw):
    monkeypatch.setenv('DIGITALAFARIN_MANAGED_REPOSITORIES', raw)
    with pytest.raises(h.TakeoverHelperDomainError):
        h.managed_repositories_from_env()


def test_legacy_deploy_entrypoint_delegates_to_privileged_flow(monkeypatch):
    seen = []
    monkeypatch.setattr(deployment, 'deploy_managed_release', lambda payload, *, helper=None: seen.append((payload, helper)) or {'final_state': 'succeeded'})
    helper = object()
    assert deployment.deploy_release({'deployment_id': '1'}, helper=helper)['final_state'] == 'succeeded'
    assert seen == [({'deployment_id': '1'}, helper)]


def test_activation_race_with_unsealed_target_restores_safe_previous(managed, monkeypatch):
    m = managed
    unsafe = m.releases / '20260101-000000-ccccccc'
    unsafe.mkdir()
    real_activate = h.atomic_activate
    def raced_activate(root, release):
        if release == m.new:
            real_activate(root, unsafe)
        return real_activate(root, release)
    monkeypatch.setattr(h, 'atomic_activate', raced_activate)
    with pytest.raises(h.TakeoverHelperDomainError) as exc:
        activate(m)
    assert exc.value.code == 'managed_current_changed'
    assert (m.root / 'current').resolve() == m.old
