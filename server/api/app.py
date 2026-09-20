"""Run with: uvicorn api.app:create_app --factory --host 127.0.0.1 --port 8766."""
import base64
import binascii
import csv
from datetime import date
import hashlib
import hmac
import io
import json
import logging
import os
from pathlib import Path
import sqlite3
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from . import db
from .models import Booking, CONSENT_VERSION, Feedback, ServiceSettings, UpdateRecord

PUBLIC = '/api/v1'
PRIVATE = '/_gb-data'
MAX_BODY = 32768
log = logging.getLogger('geekbird.api')


def error(status, code, message, **extra):
    return JSONResponse({'error': {'code': code, 'message': message, **extra}}, status_code=status)


def check_auth(header, credential):
    try:
        scheme, token = header.split(' ', 1)
        if scheme.lower() != 'basic':
            return False
        name, password = base64.b64decode(token, validate=True).decode('utf-8').split(':', 1)
        if name != 'admin' or len(password) > 1024:
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(credential['salt']), n=16384, r=8, p=1)
        return hmac.compare_digest(actual.hex(), credential['digest'])
    except (ValueError, KeyError, binascii.Error, UnicodeError):
        return False


class Boundary:
    """Authenticate all private paths and bound bodies before parsing JSON."""
    def __init__(self, app, credential, admin_origin, origins):
        self.app, self.credential, self.admin_origin, self.origins = app, credential, admin_origin, origins

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        path, method = scope['path'], scope['method']
        private = path == PRIVATE or path.startswith(PRIVATE + '/')
        public = path.startswith(PUBLIC + '/')
        origin = headers.get('origin')
        cors = public and origin in self.origins
        started = False

        async def send_headers(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
                values = list(message.get('headers', []))
                values += [(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                           (b'x-frame-options', b'DENY'), (b'referrer-policy', b'no-referrer'),
                           (b'x-robots-tag', b'noindex, nofollow, noarchive')]
                if public:
                    values.append((b'vary', b'Origin'))
                if cors:
                    values += [(b'access-control-allow-origin', origin.encode()),
                               (b'access-control-allow-methods', b'GET, POST, OPTIONS'),
                               (b'access-control-allow-headers', b'Content-Type, Idempotency-Key')]
                message['headers'] = values
            await send(message)

        async def reject(status, code, message):
            await error(status, code, message)(scope, receive, send_headers)

        async def dispatch(body_receive):
            # Keep unexpected failures private and preserve public CORS headers.
            try:
                await self.app(scope, body_receive, send_headers)
            except Exception as exc:
                log.error('Request failed: %s', type(exc).__name__)
                if started:
                    raise
                await reject(503, 'UNAVAILABLE', '服务暂时不可用，请保留内容稍后重试。')

        if private:
            if scope['scheme'] != urlsplit(self.admin_origin).scheme or headers.get('host') != urlsplit(self.admin_origin).netloc:
                return await reject(403, 'FORBIDDEN', '请使用配置的管理地址。')
            if not await run_in_threadpool(check_auth, headers.get('authorization', ''), self.credential):
                response = error(401, 'AUTH_REQUIRED', '需要管理员身份验证。')
                response.headers['WWW-Authenticate'] = 'Basic realm="GeekBird records", charset="UTF-8"'
                return await response(scope, receive, send_headers)
            if method not in ('GET', 'HEAD') and (origin != self.admin_origin or headers.get('x-gb-request') != 'records'):
                return await reject(403, 'FORBIDDEN', '管理操作来源不正确。')
        if public and origin and not cors:
            return await reject(403, 'ORIGIN_DENIED', '这个网页尚未获准连接提交接口。')
        if public and method == 'OPTIONS':
            requested = {h.strip().lower() for h in headers.get('access-control-request-headers', '').split(',') if h.strip()}
            if not cors or headers.get('access-control-request-method') not in ('GET', 'POST') or not requested <= {'content-type', 'idempotency-key'}:
                return await reject(403, 'ORIGIN_DENIED', '不允许的跨域请求。')
            return await Response(status_code=204)(scope, receive, send_headers)
        if method in ('POST', 'PATCH', 'PUT'):
            if headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                return await reject(415, 'JSON_REQUIRED', '请使用 JSON 提交。')
            size, chunks = 0, []
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                size += len(message.get('body', b''))
                if size > MAX_BODY:
                    return await reject(413, 'BODY_TOO_LARGE', '提交内容过长，请缩短后重试。')
                chunks.append(message.get('body', b''))
                if not message.get('more_body'):
                    break
            delivered = False

            async def buffered():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            return await dispatch(buffered)
        return await dispatch(receive)


def create_app(database=None, credential=None, admin_origin=None, origins=None):
    database = Path(database or os.environ.get('GB_DATABASE', '/var/lib/geekbird-api/geekbird.sqlite3'))
    if credential is None:
        credential = json.loads(Path(os.environ.get('GB_CREDENTIAL', '/etc/geekbird-api/credential.json')).read_text())
    if len(bytes.fromhex(credential['salt'])) != 16 or len(bytes.fromhex(credential['digest'])) != 64:
        raise ValueError('Invalid administrator credential')
    admin_origin = admin_origin or os.environ.get('GB_ADMIN_ORIGIN', 'https://47.120.64.37')
    origins = origins if origins is not None else os.environ.get('GB_ALLOWED_ORIGINS', 'https://geekbird.org,https://47.120.64.37').split(',')
    for origin in [admin_origin, *origins]:
        parsed = urlsplit(origin)
        if (parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment
                or parsed.username or parsed.password or '*' in origin or (parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', 'testserver'))):
            raise ValueError('Origins must be exact HTTPS origins (HTTP only for local tests).')
    db.migrate(database)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(Boundary, credential=credential, admin_origin=admin_origin, origins=set(origins))

    @app.exception_handler(db.Problem)
    async def business_error(request, exc):
        return error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        fields = []
        for item in exc.errors():
            fields.append('.'.join(str(v) for v in item['loc'] if v != 'body'))
        return error(422, 'VALIDATION_ERROR', '请检查必填项、联系方式、日期和数值范围。', fields=fields)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, exc):
        log.error('Database operation failed: %s', type(exc).__name__)
        return error(503, 'UNAVAILABLE', '服务暂时无法保存或读取，请保留内容稍后重试。')

    @app.get(PUBLIC + '/health')
    def health():
        with db.connect(database) as connection:
            connection.execute('SELECT version FROM schema_migrations').fetchone()
        return {'status': 'ok'}

    @app.get(PUBLIC + '/meta')
    def meta():
        with db.connect(database) as connection:
            current = db.settings(connection)
        return {**current, 'consentVersion': CONSENT_VERSION}

    def accept(kind, value, request):
        try:
            raw = request.headers.get('idempotency-key', '')
            parsed = UUID(raw)
            if parsed.version != 4:
                raise ValueError
            key = str(parsed)
        except ValueError:
            raise db.Problem(422, 'IDEMPOTENCY_REQUIRED', '缺少有效的提交编号，请刷新页面。')
        status, result = db.submit(database, kind, value, key)
        return JSONResponse(result, status_code=status)

    @app.post(PUBLIC + '/bookings')
    def booking(value: Booking, request: Request):
        return accept('bookings', value, request)

    @app.post(PUBLIC + '/feedback')
    def feedback(value: Feedback, request: Request):
        return accept('feedback', value, request)

    @app.get(PRIVATE + '/', response_class=HTMLResponse)
    def admin_page():
        return (Path(__file__).parent / 'admin.html').read_text()

    @app.get(PRIVATE + '/admin.js')
    def admin_script():
        return Response((Path(__file__).parent / 'admin.js').read_text(), media_type='application/javascript')

    @app.get(PRIVATE + '/api/settings')
    def read_settings():
        with db.connect(database) as connection:
            return db.settings(connection)

    @app.patch(PRIVATE + '/api/settings')
    def write_settings(value: ServiceSettings):
        with db.connect(database) as connection:
            connection.execute('BEGIN IMMEDIATE')
            old = db.settings(connection)
            if value.version != old['version']:
                raise db.Problem(409, 'VERSION_CONFLICT', '接收设置已更新，请重新读取。')
            connection.execute('UPDATE service_settings SET acceptingBookings=?,acceptingFeedback=?,closedMessage=?,version=version+1 WHERE id=1',
                               (value.acceptingBookings, value.acceptingFeedback, value.closedMessage))
            db.event(connection, 'settings', '1', 'update', value.model_dump())
            return db.settings(connection)

    @app.get(PRIVATE + '/api/export/{kind}')
    def export(kind: str, status: str | None = None, start: date | None = None, end: date | None = None):
        where, values = db.filters(kind, status, start, end)
        with db.connect(database) as connection:
            rows = connection.execute(f'SELECT * FROM {kind} WHERE {where} ORDER BY createdAt,id LIMIT 10001', values).fetchall()
            if len(rows) > 10000:
                raise db.Problem(422, 'EXPORT_TOO_LARGE', '请缩小日期范围，每次最多导出一万条。')
            db.event(connection, kind, '', 'export', {'status': status, 'start': str(start or ''), 'end': str(end or ''), 'count': len(rows)})
        output = io.StringIO(newline='')
        writer = csv.writer(output)

        def safe(value):
            if value is None:
                return ''
            text = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value)
            if text and (text.lstrip().startswith(('=', '+', '-', '@')) or any(ord(c) < 32 for c in text)):
                text = "'" + text
            return text

        if rows:
            writer.writerow(db.serialize(rows[0]).keys())
            for row in rows:
                writer.writerow(safe(v) for v in db.serialize(row).values())
        else:
            writer.writerow(['reference', 'createdAt'])
        return Response('\ufeff' + output.getvalue(), media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename="geekbird-{kind}.csv"'})

    @app.get(PRIVATE + '/api/{kind}')
    def records(kind: str, status: str | None = None, start: date | None = None, end: date | None = None,
                page: Annotated[int, Query(ge=1, le=100000)] = 1, limit: Annotated[int, Query(ge=1, le=100)] = 30):
        where, values = db.filters(kind, status, start, end)
        with db.connect(database) as connection:
            total = connection.execute(f'SELECT count(*) FROM {kind} WHERE {where}', values).fetchone()[0]
            rows = connection.execute(f'SELECT * FROM {kind} WHERE {where} ORDER BY createdAt DESC,id LIMIT ? OFFSET ?',
                                      (*values, limit, (page - 1) * limit)).fetchall()
        return {'items': [db.serialize(row) for row in rows], 'total': total, 'page': page, 'limit': limit}

    @app.get(PRIVATE + '/api/{kind}/{record_id}')
    def record(kind: str, record_id: str):
        with db.connect(database) as connection:
            value = db.serialize(db.detail(connection, kind, record_id))
            value['events'] = [dict(row) for row in connection.execute('SELECT actor,action,changes,reason,createdAt FROM record_events WHERE kind=? AND recordId=? ORDER BY id', (kind, record_id))]
        return value

    @app.patch(PRIVATE + '/api/{kind}/{record_id}')
    def change_record(kind: str, record_id: str, value: UpdateRecord):
        return db.update(database, kind, record_id, value)

    return app
