import re
from urllib.parse import urlsplit

from rest_framework import serializers
from control.deployment_serializers import ServiceSerializer


class ProvisionServiceSerializer(ServiceSerializer):
    executor = serializers.ChoiceField(choices=['systemd'], default='systemd')
    runtime = serializers.ChoiceField(choices=['node-nextjs'])
    service_port = serializers.IntegerField(min_value=1024, max_value=65535)
    health_path = serializers.RegexField(r'^/(?:[A-Za-z0-9_.~-]+/?)*$', default='/')

    def validate(self, attrs):
        attrs = super().validate(attrs)
        repo = urlsplit(attrs['repository'])
        if (repo.scheme != 'https' or repo.hostname not in {'github.com', 'gitlab.com', 'bitbucket.org'}
                or repo.username or repo.password or repo.port or repo.query or repo.fragment
                or not re.fullmatch(r'/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+', repo.path)
                or any(part in {'.', '..'} for part in repo.path.split('/'))):
            raise serializers.ValidationError({'repository': 'Use a public HTTPS repository on GitHub, GitLab or Bitbucket without credentials.'})
        root = attrs['root_directory']
        if root != '.' and any(part in {'.', '..', ''} for part in root.split('/')):
            raise serializers.ValidationError({'root_directory': 'Use a relative repository directory.'})
        ref = attrs['branch']
        if ref.startswith(('-', '/')) or '..' in ref or '//' in ref or ref.endswith(('/', '.lock', '.')):
            raise serializers.ValidationError({'branch': 'Invalid Git ref.'})
        install = attrs['install_configuration']
        build = attrs['build_configuration']
        if install.get('package_manager', 'npm') != 'npm' or install.get('lockfile', 'package-lock.json') != 'package-lock.json':
            raise serializers.ValidationError({'install_configuration': 'An npm package-lock.json is required.'})
        script = build.get('build_script', 'build')
        if not isinstance(script, str) or not re.fullmatch(r'[A-Za-z0-9:_-]+', script):
            raise serializers.ValidationError({'build_configuration': 'Invalid build script.'})
        attrs['install_configuration'] = {'package_manager': 'npm', 'lockfile': 'package-lock.json'}
        attrs['build_configuration'] = {'build_script': script}
        return attrs
