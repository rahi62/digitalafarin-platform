import uuid
from pathlib import Path

import pytest


def configuration():
    return dict(service_id=str(uuid.uuid4()), deployment_id=str(uuid.uuid4()), project_slug='demo', service_name='web',
                repository='https://github.com/example/demo.git', requested_ref='main', exact_commit='', runtime='node-nextjs',
                root_directory='.', install_configuration={'package_manager': 'npm', 'lockfile': 'package-lock.json'},
                build_configuration={'build_script': 'build'}, service_port=3000, health_path='/', environment={}, volumes=[])


def test_fixed_template_derives_exact_identity_and_unprivileged_runtime(tmp_path):
    from digitalafarin_agent.provisioning_helper import validate_configuration, render_unit
    data = validate_configuration(configuration())
    unit = render_unit(data, tmp_path / 'apps/demo/web')
    assert 'User=digitalafarin-app\n' in unit
    assert 'Group=digitalafarin-app\n' in unit
    assert '--hostname 127.0.0.1 --port 3000' in unit
    assert 'NoNewPrivileges=true' in unit
    assert '/current/node_modules/next/dist/bin/next' in unit


def test_typed_provisioning_dispatch_uses_helper_without_paths(monkeypatch):
    from digitalafarin_agent.operations import execute_operation
    from digitalafarin_agent.takeover_helper_client import TakeoverHelperClient
    data = configuration()
    def provision(self, params):
        assert params == data
        return {'final_state': 'succeeded', 'exact_commit': 'a' * 40}
    monkeypatch.setattr(TakeoverHelperClient, 'provision_service', provision)
    payload = {**data, 'unit_name': f"digitalafarin-app-{uuid.UUID(data['service_id']).hex}.service",
               'platform_managed': True, 'health_check': {'url': 'http://127.0.0.1:3000/'}}
    assert execute_operation('service.provision', payload)['final_state'] == 'succeeded'


@pytest.mark.parametrize('patch', [
    {'root_directory': '../etc'}, {'project_slug': '..'}, {'unit_name': 'ssh.service'},
    {'repository': 'https://user:secret@github.com/a/b'}, {'repository': 'https://127.0.0.1/a/b'},
    {'service_port': 22}, {'runtime': 'python-django'}, {'health_path': '//evil.test'},
    {'environment': {'SECRET': 'value'}}, {'volumes': ['/etc']}, {'user': 'root'},
])
def test_privileged_boundary_rejects_unsafe_configuration(patch):
    from digitalafarin_agent.provisioning_helper import validate_configuration
    from digitalafarin_agent.takeover_helper import TakeoverHelperDomainError
    with pytest.raises(TakeoverHelperDomainError):
        validate_configuration({**configuration(), **patch})


def test_success_is_idempotent_and_health_failure_removes_first_unit(tmp_path, monkeypatch):
    from digitalafarin_agent import provisioning_helper as helper
    from digitalafarin_agent import takeover_helper as old
    import os
    if os.geteuid() != 0:
        pytest.skip('root-owned helper fixture requires disposable Linux environment')
    from types import SimpleNamespace
    monkeypatch.setattr(old, '_account', lambda _: SimpleNamespace(pw_uid=65534, pw_gid=65534))
    monkeypatch.setattr(old, '_group_id', lambda *_: 65534)
    monkeypatch.setattr(helper, 'resolve_commit', lambda *_: 'a' * 40)
    monkeypatch.setattr(helper, 'assert_port_available', lambda _: None)
    commands = []
    monkeypatch.setattr(helper, 'systemctl', lambda *args: commands.append(args))
    def build(root, *_args):
        release = root / 'releases/20260930-120000-aaaaaaa'
        (release / '.next').mkdir(parents=True)
        return {'release_name': release.name, 'release_path': str(release), 'resolved_commit': 'a' * 40}
    monkeypatch.setattr(old, '_build_node_release', build)
    monkeypatch.setattr(helper, 'check_http_health', lambda _: None)
    apps, units = tmp_path / 'apps', tmp_path / 'units'
    units.mkdir()
    config = configuration()
    result = helper.provision_service(config, apps_root=apps, systemd_root=units)
    assert result['final_state'] == 'succeeded'
    unit = units / f"digitalafarin-app-{uuid.UUID(config['service_id']).hex}.service"
    assert unit.is_file()
    assert helper.provision_service(config, apps_root=apps, systemd_root=units) == result
    assert commands.count(('enable', '--now', unit.name)) == 1
    assert (apps / 'demo/web/current').is_symlink()

    config2 = {**configuration(), 'service_name': 'broken', 'service_port': 3001}
    def bad_health(_):
        raise RuntimeError('unhealthy')
    monkeypatch.setattr(helper, 'check_http_health', bad_health)
    with pytest.raises(old.TakeoverHelperDomainError):
        helper.provision_service(config2, apps_root=apps, systemd_root=units)
    assert not (apps / 'demo/broken/current').exists()
    assert len(list(units.glob('*.service'))) == 1


def test_redeploy_keeps_exact_unit_and_rolls_back_failed_health(tmp_path, monkeypatch):
    from digitalafarin_agent import provisioning_helper as helper, takeover_helper as old
    from types import SimpleNamespace
    import os
    if os.geteuid() != 0:
        pytest.skip('Linux ownership fixture')
    monkeypatch.setattr(old, '_account', lambda _: SimpleNamespace(pw_uid=65534, pw_gid=65534))
    monkeypatch.setattr(old, '_group_id', lambda *_: 65534)
    monkeypatch.setattr(helper, 'resolve_commit', lambda data: data['exact_commit'] or 'a' * 40)
    monkeypatch.setattr(helper, 'assert_port_available', lambda _: None)
    commands = []
    monkeypatch.setattr(helper, 'systemctl', lambda *args: commands.append(args))
    def build(root, _apps, _project, _service, _repo, commit, *_args):
        release = root / 'releases' / f'20260930-120000-{commit[:7]}'
        (release / '.next/cache').mkdir(parents=True)
        (release / '.git').mkdir()
        (release / '.git/HEAD').write_text(commit)
        (release / 'package.json').write_text('{}')
        (release / 'package-lock.json').write_text('{}')
        old._seal_release(release, root, runtime_gid=65534, writable_paths=(release / '.next/cache',))
        return {'release_name': release.name, 'release_path': str(release), 'resolved_commit': commit}
    monkeypatch.setattr(old, '_build_node_release', build)
    monkeypatch.setattr(helper, 'check_http_health', lambda _: None)
    apps, units = tmp_path / 'apps', tmp_path / 'units'
    units.mkdir()
    config = configuration()
    first = helper.provision_service(config, apps_root=apps, systemd_root=units)
    unit_before = next(units.glob('*.service')).read_bytes()
    second_config = {**config, 'deployment_id': str(uuid.uuid4()), 'exact_commit': 'b' * 40}
    second = helper.deploy_service(second_config, apps_root=apps, systemd_root=units)
    assert second['final_state'] == 'succeeded'
    assert (apps / 'demo/web/current').resolve().name == second['release_name']
    assert next(units.glob('*.service')).read_bytes() == unit_before
    failures = iter([False, True])
    def health(_):
        if not next(failures):
            raise RuntimeError('bad new version')
    monkeypatch.setattr(helper, 'check_http_health', health)
    failed = helper.deploy_service({**config, 'deployment_id': str(uuid.uuid4()), 'exact_commit': 'c' * 40}, apps_root=apps, systemd_root=units)
    assert failed['final_state'] == 'rolled_back'
    assert (apps / 'demo/web/current').resolve().name == second['release_name']
    assert (apps / 'demo/web/releases' / first['release_name']).exists()


def test_fresh_project_is_traversable_with_helper_umask(tmp_path, monkeypatch):
    import os
    import stat
    from types import SimpleNamespace
    from digitalafarin_agent import takeover_helper as helper
    if os.geteuid() != 0:
        pytest.skip('Linux ownership fixture')
    monkeypatch.setattr(helper, '_account', lambda _: SimpleNamespace(pw_uid=65534, pw_gid=65534))
    monkeypatch.setattr(helper, '_group_id', lambda *_: 65534)
    apps = tmp_path / 'apps'
    apps.mkdir()
    previous = os.umask(0o077)
    try:
        root = helper._ensure_release_directories(apps, 'brandnew', 'web', user='digitalafarin-app', group='digitalafarin-app')
    finally:
        os.umask(previous)
    assert stat.S_IMODE(root.parent.stat().st_mode) & 0o001


def test_successful_deploy_survives_retention_failure(tmp_path, monkeypatch):
    from digitalafarin_agent import provisioning_helper as helper
    from digitalafarin_agent import takeover_helper as old
    from types import SimpleNamespace
    import os
    if os.geteuid() != 0:
        pytest.skip('Linux ownership fixture')
    monkeypatch.setattr(old, '_account', lambda _: SimpleNamespace(pw_uid=65534, pw_gid=65534))
    monkeypatch.setattr(old, '_group_id', lambda *_: 65534)
    monkeypatch.setattr(helper, 'resolve_commit', lambda data: data['exact_commit'] or 'a' * 40)
    monkeypatch.setattr(helper, 'assert_port_available', lambda _: None)
    monkeypatch.setattr(helper, 'systemctl', lambda *_: None)
    monkeypatch.setattr(helper, 'check_http_health', lambda _: None)
    def build(root, _apps, _project, _service, _repo, commit, *_args):
        release = root / 'releases' / f'20260930-120000-{commit[:7]}'
        (release / '.next/cache').mkdir(parents=True)
        (release / '.git').mkdir()
        (release / '.git/HEAD').write_text(commit)
        (release / 'package.json').write_text('{}')
        (release / 'package-lock.json').write_text('{}')
        old._seal_release(release, root, runtime_gid=65534, writable_paths=(release / '.next/cache',))
        return {'release_name': release.name, 'release_path': str(release), 'resolved_commit': commit}
    monkeypatch.setattr(old, '_build_node_release', build)
    apps, units = tmp_path / 'apps', tmp_path / 'units'
    units.mkdir()
    config = configuration()
    helper.provision_service(config, apps_root=apps, systemd_root=units)
    (apps / 'demo/web/releases/20260901-120000-ccccccc').mkdir()
    result = helper.deploy_service({**config, 'deployment_id': str(uuid.uuid4()), 'exact_commit': 'b' * 40},
                                   apps_root=apps, systemd_root=units)
    assert result['final_state'] == 'succeeded'
    assert (apps / 'demo/web/current').resolve().name == result['release_name']
