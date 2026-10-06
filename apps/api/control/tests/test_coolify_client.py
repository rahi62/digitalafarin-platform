import httpx
from django.test import SimpleTestCase

from control.coolify_client import CoolifyClient


class CoolifyClientTests(SimpleTestCase):
    def test_version_accepts_plain_text_response(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, text="4.3.23", request=request)
        )
        http = httpx.Client(transport=transport)
        client = CoolifyClient("https://coolify.example.com", "test-token", http=http)

        self.assertEqual(client.version(), "4.3.23")

    def test_bearer_token_is_sent_server_side(self):
        def handler(request):
            self.assertEqual(request.headers["Authorization"], "Bearer test-token")
            return httpx.Response(200, json=[], request=request)

        http = httpx.Client(transport=httpx.MockTransport(handler))
        client = CoolifyClient("https://coolify.example.com", "test-token", http=http)

        self.assertEqual(client.list_projects(), [])

    def test_management_http_contracts_and_safe_cleanup_flags(self):
        import json
        seen = []

        def handler(request):
            seen.append((request.method, request.url.path, dict(request.url.params), json.loads(request.content) if request.content else None))
            return httpx.Response(200, json={"uuid": "app-1"})

        client = CoolifyClient("https://coolify.example.com", "secret", http=httpx.Client(transport=httpx.MockTransport(handler)))
        client.list_environments("project-1")
        client.create_application({"name": "demo"})
        client.get_application("app-1")
        client.update_application("app-1", {"ports_exposes": "3000"})
        client.list_environment_variables("app-1")
        client.create_environment_variable("app-1", {"key": "DATABASE_URL", "value": "secret"})
        client.update_environment_variable("app-1", {"key": "DATABASE_URL", "value": "changed"})
        client.deploy_application("app-1")
        client.deploy_application("app-1", force=True)
        client.start_application("app-1")
        client.stop_application("app-1")
        client.restart_application("app-1")
        client.get_deployment("deployment-1")
        client.list_application_deployments("app-1")
        client.delete_application("app-1")
        self.assertEqual([(method, path) for method, path, _, _ in seen], [
            ("GET", "/api/v1/projects/project-1/environments"), ("POST", "/api/v1/applications/public"),
            ("GET", "/api/v1/applications/app-1"), ("PATCH", "/api/v1/applications/app-1"),
            ("GET", "/api/v1/applications/app-1/envs"), ("POST", "/api/v1/applications/app-1/envs"),
            ("PATCH", "/api/v1/applications/app-1/envs"), ("POST", "/api/v1/applications/app-1/start"),
            ("POST", "/api/v1/applications/app-1/start"), ("POST", "/api/v1/applications/app-1/start"),
            ("POST", "/api/v1/applications/app-1/stop"), ("POST", "/api/v1/applications/app-1/restart"),
            ("GET", "/api/v1/deployments/deployment-1"), ("GET", "/api/v1/deployments/applications/app-1"),
            ("DELETE", "/api/v1/applications/app-1"),
        ])
        self.assertEqual(seen[7][3], {"force": False, "instant_deploy": False})
        self.assertEqual(seen[8][3], {"force": True, "instant_deploy": False})
        self.assertEqual(seen[10][3], {"docker_cleanup": False})
        self.assertEqual(seen[13][2], {"skip": "0", "take": "20"})
        self.assertEqual(seen[14][2], {"delete_volumes": "false", "delete_connected_networks": "false", "delete_configurations": "false", "docker_cleanup": "false"})

    def test_errors_redirects_invalid_json_and_oversized_responses_never_echo_upstream(self):
        from control.coolify_client import CoolifyUpstreamError
        for code, content in [(301, b"SECRET"), (401, b"SECRET"), (403, b"SECRET"), (422, b"SECRET"), (500, b"SECRET"), (200, b"not-json-SECRET"), (200, b"x" * (CoolifyClient.MAX_RESPONSE_BYTES + 1))]:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(code, content=content, headers={"Location": "https://evil.example"})
            client = CoolifyClient("https://coolify.example.com", "SECRET", http=httpx.Client(transport=httpx.MockTransport(handler)))
            with self.subTest(code=code, length=len(content)):
                with self.assertRaises(CoolifyUpstreamError) as error:
                    client.create_application({"name": "demo"})
                self.assertNotIn("SECRET", str(error.exception))
                self.assertEqual(len(calls), 1)

    def test_transport_failure_is_sanitized_and_not_retried(self):
        from control.coolify_client import CoolifyUpstreamError
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("SECRET", request=request)
        client = CoolifyClient("https://coolify.example.com", "SECRET", http=httpx.Client(transport=httpx.MockTransport(handler)))
        with self.assertRaises(CoolifyUpstreamError) as error:
            client.deploy_application("app-1")
        self.assertNotIn("SECRET", str(error.exception))
        self.assertEqual(len(calls), 1)

    def test_identifiers_cannot_select_arbitrary_paths(self):
        client = CoolifyClient("https://coolify.example.com", "secret", http=httpx.Client(transport=httpx.MockTransport(lambda request: self.fail("unexpected HTTP request"))))
        for invalid in ["../servers", "app?force=true", "app/stop", "a" * 81, "app\n"]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                client.delete_application(invalid)

    def test_private_github_application_uses_fixed_api_route(self):
        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/api/v1/applications/private-github-app")
            return httpx.Response(201, json={"uuid": "app-1"})
        client = CoolifyClient("https://coolify.example.com", "secret", http=httpx.Client(transport=httpx.MockTransport(handler)))
        self.assertEqual(client.create_github_application({"github_app_uuid": "github-app-1"}), {"uuid": "app-1"})

    def test_placement_reads_use_exact_project_environment_and_server(self):
        paths = []
        def handler(request):
            paths.append(request.url.path)
            return httpx.Response(200, json=[])
        client = CoolifyClient("https://coolify.example.com", "secret", http=httpx.Client(transport=httpx.MockTransport(handler)))
        client.get_environment("project-1", "env-1")
        client.list_server_resources("server-1")
        self.assertEqual(paths, ["/api/v1/projects/project-1/env-1", "/api/v1/servers/server-1/resources"])
