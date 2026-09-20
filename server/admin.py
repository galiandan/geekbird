#!/usr/bin/env python3
"""VPS settings service; bind to loopback and publish through Nginx HTTPS."""
import base64
import binascii
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

BASE = '/_gb-settings'


def validate(value, origin):
    if (not isinstance(value, dict) or value.get('schemaVersion') != 2
            or set(value) != {'schemaVersion', 'emergencyQQ'} or not isinstance(value.get('emergencyQQ'), str)):
        raise ValueError('设置页面已更新，请刷新后再保存。')
    qq = value['emergencyQQ'].strip()
    if qq and not re.fullmatch(r'[1-9][0-9]{4,14}', qq):
        raise ValueError('QQ 号应为 5–15 位数字。')
    return {'schemaVersion': 2, 'emergencyQQ': qq}


def public_config(value, origin):
    if not isinstance(value, dict) or value.get('schemaVersion', 2) != 2:
        raise ValueError('Invalid configuration')
    result = validate({'schemaVersion': 2, 'emergencyQQ': value.get('emergencyQQ')}, origin)
    root = Path(__file__).resolve().parents[1]
    source = (root / 'public/config.js' if (root / 'public').is_dir() else root / 'config.js').read_text(encoding='utf-8')
    for key in ('apiBaseUrl', 'dataAdminUrl'):
        match = re.search(rf'{key}\s*:\s*("(?:[^"\\]|\\.)*")', source)
        if not match:
            raise ValueError('Missing source default')
        result[key] = json.loads(match[1])
    return {**result, 'bookingUrl': '/booking/', 'feedbackUrl': '/feedback/'}


def write_config(path, value):
    # Atomic replace: a failed write must not truncate the previous configuration.
    descriptor, temporary = tempfile.mkstemp(prefix='.config-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body=None, content_type='application/json; charset=utf-8', extra=None):
        if body is None:
            body = '{}'
        data = body.encode('utf-8')
        self.send_response(status)
        for key, value in {
            'Content-Type': content_type, 'Content-Length': str(len(data)),
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY', 'X-Robots-Tag': 'noindex, nofollow, noarchive',
            'Referrer-Policy': 'no-referrer', **(extra or {}),
        }.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def authenticated(self):
        try:
            scheme, encoded = self.headers.get('Authorization', '').split(' ', 1)
            if scheme != 'Basic':
                return False
            supplied = base64.b64decode(encoded, validate=True)
            return hmac.compare_digest(hashlib.sha256(supplied).digest(), self.server.credential_digest)
        except (ValueError, binascii.Error):
            return False

    def handle_request(self):
        path = urlsplit(self.path).path
        if path != '/config.js' and path != BASE and not path.startswith(BASE + '/'):
            return self.reply(404)
        if path != '/config.js':
            # Nginx overwrites this header. The service only listens on loopback.
            if self.headers.get('X-Forwarded-Proto') != 'https':
                return self.reply(403)
            if not self.authenticated():
                return self.reply(401, extra={'WWW-Authenticate': 'Basic realm="Private", charset="UTF-8"'})
        if path in (BASE, BASE + '/'):
            if self.command not in ('GET', 'HEAD'):
                return self.reply(405, extra={'Allow': 'GET, HEAD'})
            return self.reply(200, self.server.admin_html, 'text/html; charset=utf-8')
        if path not in ('/config.js', BASE + '/api'):
            return self.reply(404)
        if self.command in ('GET', 'HEAD'):
            config = json.loads(self.server.config_path.read_text(encoding='utf-8'))
            config = public_config(config, self.server.origin)
            body = json.dumps(config, ensure_ascii=False)
            if path == '/config.js':
                return self.reply(200, 'window.GEEKBIRD_CONFIG = Object.freeze(' + body + ');\n', 'application/javascript; charset=utf-8')
            return self.reply(200, body)
        if self.command != 'PUT' or path != BASE + '/api':
            return self.reply(405, extra={'Allow': 'GET, HEAD' if path == '/config.js' else 'GET, HEAD, PUT'})
        if self.headers.get('Origin') != self.server.origin or self.headers.get('X-GB-Request') != 'settings':
            return self.reply(403)
        if self.headers.get_content_type() != 'application/json':
            return self.reply(415)
        if self.headers.get('Transfer-Encoding'):
            return self.reply(400)
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            return self.reply(400)
        if size < 0 or size > 16384:
            return self.reply(413)
        try:
            value = validate(json.loads(self.rfile.read(size)), self.server.origin)
        except (ValueError, UnicodeError):
            return self.reply(400, json.dumps({'error': '请刷新设置页面，并检查 QQ 号是否正确。'}, ensure_ascii=False))
        write_config(self.server.config_path, value)
        return self.reply(200, json.dumps(public_config(value, self.server.origin), ensure_ascii=False))

    def do_GET(self):
        self.connection.settimeout(15)
        try:
            self.handle_request()
        except (OSError, ValueError):
            self.reply(503, json.dumps({'error': '配置暂时无法读取或保存，请稍后重试。'}, ensure_ascii=False))

    do_HEAD = do_GET
    do_PUT = do_GET
    do_POST = do_GET
    do_DELETE = do_GET
    do_OPTIONS = do_GET


def create_server(address, config_path, admin_html, origin, credential_digest):
    server = ThreadingHTTPServer(address, Handler)
    server.config_path = Path(config_path)
    server.admin_html = admin_html
    server.origin = origin
    server.credential_digest = credential_digest
    return server


if __name__ == '__main__':
    state = Path(os.environ.get('STATE_DIRECTORY', '/var/lib/geekbird'))
    credential = bytes.fromhex((state / 'credential.sha256').read_text().strip())
    if len(credential) != 32:
        raise ValueError('Invalid credential digest')
    html = (Path(__file__).parent / 'admin.html').read_text(encoding='utf-8')
    html = html.replace('各地区同步通常需要约 1 分钟，部分地区可能更久；稍后刷新网站即可查看。', '刷新网站即可查看。')
    create_server(('127.0.0.1', 8765), state / 'config.json', html,
                  os.environ['ADMIN_ORIGIN'], credential).serve_forever()
