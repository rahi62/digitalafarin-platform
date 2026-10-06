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
