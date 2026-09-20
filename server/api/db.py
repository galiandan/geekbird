"""Short transactions and explicit columns; no public record lookup."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo

from .models import CONSENT_VERSION

KINDS = ('bookings', 'feedback')
TRANSITIONS = {
    'new': {'contacted', 'cancelled'},
    'contacted': {'scheduled', 'in_progress', 'cancelled'},
    'scheduled': {'in_progress', 'cancelled'},
    'in_progress': {'completed', 'cancelled'},
    'completed': {'contacted'}, 'cancelled': {'contacted'},
}


class Problem(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


@contextmanager
def connect(path):
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA busy_timeout = 5000')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def migrate(path):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute('PRAGMA journal_mode = WAL')
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
        if not exists:
            db.executescript((Path(__file__).parent / 'migrations/001_initial.sql').read_text())
        if db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0] != 1:
            raise RuntimeError('Unsupported database schema; deploy a compatible release.')
    path.chmod(0o600)


def settings(db):
    result = dict(db.execute('SELECT * FROM service_settings WHERE id=1').fetchone())
    result.pop('id')
    for key in ('acceptingBookings', 'acceptingFeedback'):
        result[key] = bool(result[key])
    return result


def event(db, kind, record_id, action, changes, reason=''):
    db.execute('INSERT INTO record_events (kind,recordId,actor,action,changes,reason,createdAt) VALUES (?,?,?,?,?,?,?)',
               (kind, record_id, 'admin', action, json.dumps(changes, ensure_ascii=False), reason, now()))


def receipt(row, kind):
    return {'reference': row['reference'], 'createdAt': row['createdAt'],
            'message': '预约已收到，请等待志愿者联系。' if kind == 'bookings' else '反馈已收到，感谢你的认真填写。'}


def submit(path, kind, model, key):
    assert kind in KINDS
    value = model.model_dump(mode='json', exclude={'website'})
    if kind == 'feedback':
        value['reportedHours'] = format(model.reportedHours.quantize(Decimal('0.01')), 'f')
    digest = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute(f'SELECT * FROM {kind} WHERE idempotencyKey=?', (key,)).fetchone()
        if old:
            if old['purgedAt']:
                raise Problem(410, 'SUBMISSION_EXPIRED', '该申请已按保留规则清理，请开始新的申请。')
            if old['payloadHash'] != digest:
                raise Problem(409, 'IDEMPOTENCY_CONFLICT', '此前提交内容可能已收到。请恢复原内容重试，或通过 QQ 联系我们核对后再开始新的申请。')
            return 200, receipt(old, kind)
        if model.consentVersion != CONSENT_VERSION:
            raise Problem(409, 'CONSENT_VERSION_CHANGED', '信息使用说明已更新，请刷新页面阅读后重新确认。')
        current = settings(db)
        if not current['acceptingBookings' if kind == 'bookings' else 'acceptingFeedback']:
            raise Problem(503, 'SUBMISSIONS_CLOSED', current['closedMessage'])
        if kind == 'feedback':
            value['serviceTypes'] = json.dumps(model.serviceTypes)
            value['reportedHoursX100'] = int(model.reportedHours * 100)
            del value['reportedHours']
        stamp = now()
        reference = 'GB-' + ('B' if kind == 'bookings' else 'F') + '-' + datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d') + '-' + secrets.token_hex(6).upper()
        value.update(id=str(uuid4()), reference=reference, idempotencyKey=key, payloadHash=digest,
                     createdAt=stamp, updatedAt=stamp)
        columns = ','.join(value)
        db.execute(f'INSERT INTO {kind} ({columns}) VALUES ({",".join("?" for _ in value)})', tuple(value.values()))
        return 201, receipt(value, kind)


def serialize(row):
    value = dict(row)
    for key in ('payloadHash', 'idempotencyKey'):
        value.pop(key, None)
    if 'serviceTypes' in value:
        value['serviceTypes'] = json.loads(value['serviceTypes'])
        for name in ('reportedHours', 'confirmedHours'):
            raw = value.pop(name + 'X100')
            value[name] = format(Decimal(raw) / 100, '.2f') if raw is not None else None
    return value


def filters(kind, status=None, start=None, end=None):
    if kind not in KINDS:
        raise Problem(404, 'NOT_FOUND', '没有这个页面。')
    clauses, values = ['purgedAt IS NULL'], []
    allowed = TRANSITIONS if kind == 'bookings' else ('pending', 'reviewed', 'invalid')
    if status:
        if status not in allowed:
            raise Problem(422, 'VALIDATION_ERROR', '请选择有效状态。')
        clauses.append('status=?')
        values.append(status)
    if start and end and start > end:
        raise Problem(422, 'VALIDATION_ERROR', '开始日期不能晚于结束日期。')
    for day, op, advance in ((start, '>=', False), (end, '<', True)):
        if day:
            local = datetime.combine(day + timedelta(days=int(advance)), datetime.min.time(), ZoneInfo('Asia/Shanghai'))
            clauses.append('createdAt' + op + '?')
            values.append(local.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'))
    return ' AND '.join(clauses), values


def detail(db, kind, record_id):
    filters(kind)
    row = db.execute(f'SELECT * FROM {kind} WHERE id=? AND purgedAt IS NULL', (record_id,)).fetchone()
    if not row:
        raise Problem(404, 'NOT_FOUND', '记录不存在或已清理。')
    return row


def update(path, kind, record_id, model):
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        old = detail(db, kind, record_id)
        if old['version'] != model.version:
            raise Problem(409, 'VERSION_CONFLICT', '记录已被更新，请重新读取后核对。')
        fields = {'status': model.status, 'notes': model.notes, 'updatedAt': now(), 'version': old['version'] + 1}
        if kind == 'bookings':
            if model.confirmedHours is not None or model.bookingId is not None:
                raise Problem(422, 'VALIDATION_ERROR', '预约不能填写反馈核实字段。')
            if model.status != old['status'] and model.status not in TRANSITIONS[old['status']]:
                raise Problem(422, 'INVALID_TRANSITION', '请按联系、安排、处理、结案的顺序更新。')
            if model.status != old['status'] and (model.status == 'cancelled' or old['status'] in ('completed', 'cancelled')) and not model.reason:
                raise Problem(422, 'REASON_REQUIRED', '取消或重新打开记录时请填写原因。')
            closed = model.status in ('completed', 'cancelled')
        else:
            if model.status not in ('pending', 'reviewed', 'invalid'):
                raise Problem(422, 'VALIDATION_ERROR', '反馈状态无效。')
            if model.status == 'reviewed' and model.confirmedHours is None:
                raise Problem(422, 'HOURS_REQUIRED', '已核实反馈需要填写确认时长。')
            if (model.status == 'invalid' or model.confirmedHours == 0) and not model.reason:
                raise Problem(422, 'REASON_REQUIRED', '无效反馈或不计时长时请填写原因。')
            if model.status != 'reviewed' and model.confirmedHours is not None:
                raise Problem(422, 'VALIDATION_ERROR', '只有已核实反馈可以填写确认时长。')
            if model.bookingId:
                detail(db, 'bookings', model.bookingId)
            fields.update(confirmedHoursX100=int(model.confirmedHours * 100) if model.confirmedHours is not None else None,
                          bookingId=model.bookingId or None)
            closed = model.status != 'pending'
        fields['closedAt'] = (old['closedAt'] or fields['updatedAt']) if closed else None
        db.execute(f'UPDATE {kind} SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?', (*fields.values(), record_id))
        changes = {k: {'from': old[k], 'to': v} for k, v in fields.items() if k not in ('updatedAt', 'version', 'notes', 'closedAt') and old[k] != v}
        changes['notesChanged'] = old['notes'] != model.notes
        event(db, kind, record_id, 'update', changes, model.reason)
        return serialize(detail(db, kind, record_id))
