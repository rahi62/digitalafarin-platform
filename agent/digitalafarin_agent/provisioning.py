from urllib.parse import urlsplit

from .progress import report
from .takeover_helper_client import TakeoverHelperClient, TakeoverHelperError


def provision_service(payload, *, helper=None, action='provision_service'):
    keys = ('service_id', 'deployment_id', 'project_slug', 'service_name', 'repository', 'requested_ref',
            'exact_commit', 'runtime', 'root_directory', 'install_configuration', 'build_configuration',
            'service_port', 'environment', 'volumes')
    allowed = set(keys) | {'health_path', 'unit_name', 'platform_managed', 'health_check', 'release_name'}
    if set(payload) - allowed or not payload.get('platform_managed'):
        raise TakeoverHelperError('invalid_payload', 'Invalid provisioning context.')
    data = {key: payload[key] for key in keys}
    data['health_path'] = payload.get('health_path') or urlsplit(payload['health_check']['url']).path or '/'
    report('building')
    if action == 'rollback_service':
        data['release_name'] = payload['release_name']
    return getattr(helper or TakeoverHelperClient(), action)(data, on_progress=report)
