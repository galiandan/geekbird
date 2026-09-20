#!/usr/bin/env python3
"""Launch isolated local services, run the browser smoke test, then remove test data."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from api import db
from api.manage import credential


def main():
    with tempfile.TemporaryDirectory(prefix='geekbird-browser-') as temporary:
        folder = Path(temporary)
        public = folder / 'public'
        shutil.copytree(ROOT / 'dist/cloudflare', public)
        config = {'schemaVersion': 2, 'emergencyQQ': '12345678', 'bookingUrl': '/booking/', 'feedbackUrl': '/feedback/',
                  'apiBaseUrl': 'http://127.0.0.1:8790/api/v1', 'dataAdminUrl': 'http://127.0.0.1:8790/_gb-data/', 'isPreview': True}
        (public / 'config.js').write_text('window.GEEKBIRD_CONFIG = Object.freeze(' + json.dumps(config) + ');')
        (folder / 'credential.json').write_text(json.dumps(credential('local-browser-password-only')))
        database = folder / 'browser.sqlite3'
        db.migrate(database)
        with db.connect(database) as connection:
            connection.execute('UPDATE service_settings SET acceptingBookings=1,acceptingFeedback=1')
        env = {**os.environ, 'GB_DATABASE': str(database), 'GB_CREDENTIAL': str(folder / 'credential.json'),
               'GB_ADMIN_ORIGIN': 'http://127.0.0.1:8790', 'GB_ALLOWED_ORIGINS': 'http://127.0.0.1:8800',
               'GB_BROWSER_BASE': 'http://127.0.0.1:8800', 'GB_BROWSER_API': 'http://127.0.0.1:8790', 'GB_BROWSER_PREFIX': ''}
        backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'api.app:create_app', '--factory', '--app-dir', str(ROOT / 'server'), '--host', '127.0.0.1', '--port', '8790', '--no-access-log'], env=env)
        server = None
        try:
            handler = functools.partial(SimpleHTTPRequestHandler, directory=str(public))
            server = ThreadingHTTPServer(('127.0.0.1', 8800), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            for attempt in range(50):
                if backend.poll() is not None:
                    raise RuntimeError('Local API exited before the browser test')
                try:
                    with urlopen('http://127.0.0.1:8790/api/v1/health', timeout=1): break
                except OSError:
                    if attempt == 49: raise
                    time.sleep(.1)
            subprocess.run([os.environ.get('GEEKBIRD_NODE', 'node'), str(ROOT / 'tests/browser-smoke.mjs')], env=env, check=True)
        finally:
            backend.terminate(); backend.wait(timeout=10)
            if server:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    main()
