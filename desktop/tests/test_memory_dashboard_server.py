from aiohttp.test_utils import AioHTTPTestCase

from desktop.memory_dashboard.server import build_app


class MemoryDashboardTest(AioHTTPTestCase):
    async def get_application(self):
        # Point at a guaranteed-unreachable port — proxy attempts return 502
        # but route resolution itself still works.
        return build_app(memory_retriever_url="http://127.0.0.1:65535")

    async def test_root_serves_html_or_fallback(self):
        async with self.client.get("/") as r:
            assert r.status == 200

    async def test_api_theme_returns_a_theme(self):
        async with self.client.get("/api/theme") as r:
            assert r.status == 200
            body = await r.json()
            assert "theme" in body
            assert isinstance(body["theme"], str)
