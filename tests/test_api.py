"""Exercise the real ASGI app, transactions and backup without production data."""
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from api.app import create_app
from api import db
from api.manage import backup, credential, prune_backups, purge
from api.models import CONSENT_VERSION

ORIGIN = 'https://geekbird.org'
ADMIN = 'https://backend.example'
PASSWORD = 'local-test-only-password'
AUTH = 'Basic ' + base64.b64encode(('admin:' + PASSWORD).encode()).decode()
BOOKING = dict(name='测试同学', gradeMajor='2026 计算机', phone='', qq='12345678', email='', device='测试笔记本',
               os='Windows 11', issue='开机以后无法进入系统', preferredContactTime='', consent=True, consentVersion=CONSENT_VERSION)
FEEDBACK = dict(nameMajor='测试同学 计算机', contactType='qq', contact='12345678', bookingReference='', serviceTypes=['repair'],
                summary='排查无法启动', volunteerNames='测试志愿者', reportedHours='2.5', requestedOn='2026-09-01',
                attitudeRating=5, skillRating=4, overallRating=5, comment='', consent=True, consentVersion=CONSENT_VERSION)


@pytest.fixture
def service(tmp_path):
    path = tmp_path / 'service.sqlite3'
    creds = credential(PASSWORD)
    with TestClient(create_app(path, creds, ADMIN, [ORIGIN]), base_url=ADMIN) as client:
        yield client, path, creds


def admin(client, method, path, **kwargs):
    return client.request(method, '/_gb-data/api/' + path, headers={'Authorization': AUTH, 'Origin': ADMIN, 'X-GB-Request': 'records'}, **kwargs)


def enable(client, booking=True, feedback=True):
    current = admin(client, 'GET', 'settings').json()
    result = admin(client, 'PATCH', 'settings', json={**current, 'acceptingBookings': booking, 'acceptingFeedback': feedback})
    assert result.status_code == 200, result.text


def submit(client, kind='bookings', value=None, key=None):
    return client.post('/api/v1/' + kind, json=value if value is not None else BOOKING,
                       headers={'Origin': ORIGIN, 'Idempotency-Key': key or str(uuid4())})


def test_closed_persistence_and_replay(service):
    client, path, creds = service
    assert submit(client).status_code == 503
    enable(client)
    key = str(uuid4())
    first = submit(client, key=key)
    assert first.status_code == 201
    assert set(first.json()) == {'reference', 'createdAt', 'message'}
    enable(client, False, False)
    assert submit(client, key=key).json() == first.json()
    assert submit(client, key=key).status_code == 200
    assert submit(client, value={**BOOKING, 'name': '另一人'}, key=key).status_code == 409
    assert submit(client).status_code == 503
    with TestClient(create_app(path, creds, ADMIN, [ORIGIN]), base_url=ADMIN) as restarted:
        assert submit(restarted, key=key).json() == first.json()
        assert admin(restarted, 'GET', 'bookings').json()['total'] == 1


def test_concurrent_retry_is_one_record(service):
    client, path, _ = service
    enable(client)
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(lambda _: submit(client, key=key), range(8)))
    assert sorted(r.status_code for r in replies) == [200] * 7 + [201]
    assert len({r.json()['reference'] for r in replies}) == 1
    assert admin(client, 'GET', 'bookings').json()['total'] == 1


@pytest.mark.parametrize('change', [dict(phone='', qq=''), dict(phone='bad'), dict(qq='01234'), dict(email='bad'),
    dict(consent=False), dict(consent='true'), dict(status='completed'), dict(website='spam'), dict(issue=''), dict(name='\x00')])
def test_invalid_booking_never_writes(service, change):
    client, path, _ = service
    enable(client)
    result = submit(client, value={**BOOKING, **change})
    assert result.status_code == 422
    assert BOOKING['issue'] not in result.text
    assert admin(client, 'GET', 'bookings').json()['total'] == 0


@pytest.mark.parametrize('change', [dict(reportedHours='0'), dict(reportedHours='5.01'), dict(reportedHours='NaN'),
    dict(reportedHours='1.111'), dict(requestedOn='2999-01-01'), dict(attitudeRating=True), dict(skillRating='5'),
    dict(overallRating=6), dict(serviceTypes=['other']), dict(contactType='email'), dict(confirmedHours='5')])
def test_invalid_feedback(service, change):
    client, _, _ = service
    enable(client)
    assert submit(client, 'feedback', {**FEEDBACK, **change}).status_code == 422
    assert admin(client, 'GET', 'feedback').json()['total'] == 0


def test_cors_body_size_and_consent(service):
    client, _, _ = service
    enable(client)
    response = client.options('/api/v1/bookings', headers={'Origin': ORIGIN, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type,idempotency-key'})
    assert response.status_code == 204
    assert response.headers['Access-Control-Allow-Origin'] == ORIGIN
    assert 'Access-Control-Allow-Credentials' not in response.headers
    assert client.get('/api/v1/meta', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.options('/api/v1/bookings', headers={'Origin': ORIGIN, 'Access-Control-Request-Method': 'DELETE'}).status_code == 403
    large = client.post('/api/v1/bookings', content=b' ' * 33000, headers={'Origin': ORIGIN, 'Content-Type': 'application/json'})
    assert large.status_code == 413 and large.headers['Access-Control-Allow-Origin'] == ORIGIN
    assert submit(client, value={**BOOKING, 'consentVersion': 'old'}).status_code == 409
    assert client.post('/api/v1/bookings', json=BOOKING).status_code == 422
    assert client.post('/api/v1/bookings', content='{}', headers={'Content-Type': 'text/plain'}).status_code == 415
    assert client.get('/api/v1/bookings').status_code == 405


def test_private_paths_csrf_and_headers(service):
    client, _, _ = service
    for path in ('/_gb-data/', '/_gb-data/admin.js', '/_gb-data/api/bookings', '/_gb-data/api/export/bookings', '/_gb-data/unknown'):
        reply = client.get(path)
        assert reply.status_code == 401
        assert reply.headers['Cache-Control'] == 'no-store'
        assert 'Access-Control-Allow-Origin' not in reply.headers
    assert client.get('/_gb-data/', headers={'Authorization': AUTH}).status_code == 200
    assert client.get('/_gb-data/', headers={'Authorization': AUTH, 'Host': 'evil.example'}).status_code == 403
    for headers in ({'Authorization': AUTH}, {'Authorization': AUTH, 'Origin': 'https://evil.example', 'X-GB-Request': 'records'}):
        assert client.patch('/_gb-data/api/settings', json={}, headers=headers).status_code == 403
    assert client.get('/openapi.json').status_code == 404


def test_unexpected_errors_keep_cors_without_private_details(service, monkeypatch):
    client, _, _ = service
    def fail(*args):
        raise RuntimeError('private-data-must-stay-private')
    monkeypatch.setattr(db, 'submit', fail)
    response = submit(client)
    assert response.status_code == 503
    assert response.headers['Access-Control-Allow-Origin'] == ORIGIN
    assert 'private-data-must-stay-private' not in response.text


def test_workflow_optimistic_lock_and_feedback_hours(service):
    client, _, _ = service
    enable(client)
    submit(client)
    row = admin(client, 'GET', 'bookings').json()['items'][0]
    route = 'bookings/' + row['id']
    assert admin(client, 'PATCH', route, json={'version': 1, 'status': 'completed'}).status_code == 422
    assert admin(client, 'PATCH', route, json={'version': 1, 'status': 'cancelled'}).status_code == 422
    for version, status in enumerate(('contacted', 'in_progress', 'completed'), 1):
        result = admin(client, 'PATCH', route, json={'version': version, 'status': status})
        assert result.status_code == 200, result.text
    assert admin(client, 'PATCH', route, json={'version': 1, 'status': 'contacted'}).status_code == 409
    assert admin(client, 'PATCH', route, json={'version': 4, 'status': 'contacted', 'reason': '需要继续跟进'}).status_code == 200
    assert len(admin(client, 'GET', route).json()['events']) == 4
    assert submit(client, 'feedback', FEEDBACK).status_code == 201
    feedback = admin(client, 'GET', 'feedback').json()['items'][0]
    route = 'feedback/' + feedback['id']
    assert feedback['reportedHours'] == '2.50'
    assert admin(client, 'PATCH', route, json={'version': 1, 'status': 'reviewed'}).status_code == 422
    updated = admin(client, 'PATCH', route, json={'version': 1, 'status': 'reviewed', 'confirmedHours': '2', 'bookingId': row['id']})
    assert updated.status_code == 200, updated.text
    assert updated.json()['reportedHours'] == '2.50' and updated.json()['confirmedHours'] == '2.00'
    assert admin(client, 'PATCH', route, json={'version': 2, 'status': 'invalid'}).status_code == 422


def test_filters_csv_backup_restore_and_retention(service, tmp_path):
    client, path, creds = service
    enable(client)
    submit(client, value={**BOOKING, 'name': '=HYPERLINK("bad")'})
    row = admin(client, 'GET', 'bookings').json()['items'][0]
    export = admin(client, 'GET', 'export/bookings')
    assert export.status_code == 200 and "'=HYPERLINK" in export.text
    assert admin(client, 'GET', 'bookings?status=bad').status_code == 422
    assert admin(client, 'GET', 'bookings?start=2026-10-01&end=2026-09-01').status_code == 422
    snapshot = backup(path, tmp_path / 'backups')
    with TestClient(create_app(snapshot, creds, ADMIN, [ORIGIN]), base_url=ADMIN) as restored:
        assert admin(restored, 'GET', 'bookings').json()['total'] == 1
    with db.connect(path) as connection:
        connection.execute("UPDATE bookings SET status='completed',closedAt='2020-01-01T00:00:00Z'")
    assert purge(path) == {'bookings': 1, 'feedback': 0}
    assert admin(client, 'GET', 'bookings').json()['total'] == 1
    assert purge(path, apply=True) == {'bookings': 1, 'feedback': 0}
    assert admin(client, 'GET', 'bookings').json()['total'] == 0
    with db.connect(path) as connection:
        stored = connection.execute('SELECT * FROM bookings').fetchone()
        assert stored['name'] == '' and stored['payloadHash'] is None
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert admin(client, 'GET', 'bookings/' + row['id']).status_code == 404


def test_backup_retention_covers_manual_snapshots(service, tmp_path):
    _, database, _ = service
    folder = tmp_path / 'backup-root'
    old = backup(database, folder / 'manual')
    os.utime(old, (1, 1))
    current = backup(database, folder / 'daily')
    prune_backups(folder)
    assert not old.exists() and current.exists()


def test_password_minimum_six_characters():
    with pytest.raises(ValueError, match='at least 6'):
        credential('abc12')
    value = credential('abc123')
    assert value['digest'] == hashlib.scrypt(b'abc123', salt=bytes.fromhex(value['salt']), n=16384, r=8, p=1).hex()
