import base64
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest

spec = importlib.util.spec_from_file_location('admin', Path(__file__).resolve().parents[1] / 'server/admin.py')
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'config.json'
        self.initial = {'schemaVersion': 2, 'emergencyQQ': '123456789'}
        admin.write_config(self.path, self.initial)
        self.auth = 'Basic ' + base64.b64encode(b'admin:test-password-only').decode()
        self.server = admin.create_server(('127.0.0.1', 0), self.path, '<html>Settings</html>',
                                          'https://example.com', hashlib.sha256(b'admin:test-password-only').digest())
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path='/_gb-settings/api', method='GET', data=None, **headers):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.request(method, path, body=json.dumps(data) if data is not None else None,
                           headers={'X-Forwarded-Proto': 'https', 'Authorization': self.auth,
                                    'Origin': 'https://example.com', 'X-GB-Request': 'settings',
                                    'Content-Type': 'application/json', **headers})
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def test_auth_and_https(self):
        for path in ('/_gb-settings', '/_gb-settings/', '/_gb-settings/api'):
            self.assertEqual(self.request(path, Authorization='')[0], 401)
            self.assertEqual(self.request(path, Authorization='Basic invalid')[0], 401)
            self.assertEqual(self.request(path, **{'X-Forwarded-Proto': 'http'})[0], 403)
        self.assertEqual(self.request('/_gb-settings/')[0], 200)

    def test_persistence_and_public_config(self):
        value = {'schemaVersion': 2, 'emergencyQQ': '987654321'}
        self.assertEqual(self.request(method='PUT', data=value)[0], 200)
        self.assertEqual(json.loads(self.path.read_text()), value)
        status, body, headers = self.request('/config.js', Authorization='')
        self.assertEqual(status, 200)
        self.assertIn(b'987654321', body)
        self.assertIn(b'/booking/', body)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.request(method='PUT', data={'schemaVersion': 2, 'emergencyQQ': ''})[0], 200)

    def test_invalid_stale_and_cross_site_writes(self):
        for value in ({'schemaVersion': 2, 'emergencyQQ': '01234'},
                      {'emergencyQQ': '123456789', 'bookingUrl': '', 'feedbackUrl': ''},
                      {'schemaVersion': 2, 'emergencyQQ': '', 'apiBaseUrl': 'https://evil.example'}, []):
            self.assertEqual(self.request(method='PUT', data=value)[0], 400)
        self.assertEqual(self.request(method='PUT', data=self.initial, Origin='https://evil.example')[0], 403)
        self.assertEqual(json.loads(self.path.read_text()), self.initial)

    def test_legacy_public_projection(self):
        admin.write_config(self.path, {'emergencyQQ': '123456789', 'bookingUrl': 'https://www.wjx.top/old', 'privateNote': 'private-marker'})
        status, body, _ = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['feedbackUrl'], '/feedback/')
        self.assertNotIn(b'private-marker', self.request('/config.js')[1])
        self.assertNotIn(b'wjx.top', self.request('/config.js')[1])

    def test_errors_and_methods(self):
        self.assertEqual(self.request(method='PUT', data={'emergencyQQ': 'x' * 17000})[0], 413)
        self.assertEqual(self.request(method='POST')[0], 405)
        self.assertEqual(self.request('/config.js', method='PUT', data=self.initial)[0], 405)
        self.assertEqual(self.request('/_gb-settings/private')[0], 404)
        self.assertEqual(self.request('/config.js', method='HEAD')[1], b'')
        self.path.write_text('invalid')
        self.assertEqual(self.request('/config.js')[0], 503)


if __name__ == '__main__':
    unittest.main()
