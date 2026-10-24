"""The owner action UI must not be framed by an unrelated origin."""
import unittest
import httpx
from app.main import app


class SecurityHeadersTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_action_document_forbids_framing_preserves_replay(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            for path in ('/', '/static/index.html', '/static//index.html', '/static/index.html/'):
                with self.subTest(path=path):
                    response=await c.get(path)
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(response.headers['x-frame-options'],'DENY')
                    self.assertEqual(response.headers['content-security-policy'],"frame-ancestors 'none'")
                    self.assertEqual(response.headers['x-content-type-options'],'nosniff')
                    self.assertIn('id="active43-panel"',response.text)
                    self.assertNotIn('id="paper-title"',response.text)
                    self.assertIn('id="chart-title"',response.text)
            script=await c.get('/static/intelligence.js')
            self.assertEqual(script.status_code,200)
            self.assertIn(script.headers['content-type'].split(';',1)[0],
                          {'application/javascript','text/javascript'})



if __name__=='__main__':unittest.main()
