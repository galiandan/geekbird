"""Private CLI: migrations, credentials, consistent backup, and retention cleanup."""
import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3

from . import db


def credential(password):
    if len(password) < 16:
        raise ValueError('Use a password with at least 16 characters.')
    salt = secrets.token_bytes(16)
    return {'salt': salt.hex(), 'digest': hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()}


def backup(source, folder, retain=14):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = folder / ('geekbird-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
    temporary = target.with_suffix('.partial')
    try:
        with db.connect(source) as current:
            with closing(sqlite3.connect(temporary)) as copy:
                current.backup(copy)
                if copy.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Backup integrity check failed')
        temporary.chmod(0o600)
        temporary.replace(target)
        for old in sorted(folder.glob('geekbird-*.sqlite3'), reverse=True)[retain:]:
            old.unlink()
    finally:
        temporary.unlink(missing_ok=True)
    return target


def prune_backups(root):
    """Expire snapshots as well as daily copies after 14 days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).timestamp()
    for name in ('daily', 'manual', 'before-deploy'):
        for path in (Path(root) / name).glob('geekbird-*.sqlite3'):
            if path.stat().st_mtime < cutoff:
                path.unlink()


def purge(path, days=180, apply=False):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec='seconds').replace('+00:00', 'Z')
    counts = {}
    with db.connect(path) as connection:
        connection.execute('BEGIN IMMEDIATE')
        for kind in db.KINDS:
            rows = connection.execute(f'SELECT id FROM {kind} WHERE closedAt < ? AND purgedAt IS NULL', (cutoff,)).fetchall()
            counts[kind] = len(rows)
            if not apply:
                continue
            private = ('name', 'gradeMajor', 'phone', 'qq', 'email', 'device', 'os', 'issue', 'preferredContactTime') if kind == 'bookings' else (
                'nameMajor', 'contact', 'bookingReference', 'summary', 'volunteerNames', 'comment')
            for row in rows:
                # Tombstones retain only the used key and non-identifying statistics.
                fields = {key: '' for key in (*private, 'notes')}
                fields.update(payloadHash=None, purgedAt=db.now(), reference='purged-' + row['id'])
                if kind == 'feedback':
                    fields['bookingId'] = None
                else:
                    connection.execute('UPDATE feedback SET bookingId=NULL, bookingReference=CASE WHEN bookingId=? THEN \'\' ELSE bookingReference END WHERE bookingId=?', (row['id'], row['id']))
                connection.execute(f'UPDATE {kind} SET ' + ','.join(k + '=?' for k in fields) + ',version=version+1 WHERE id=?', (*fields.values(), row['id']))
                connection.execute('DELETE FROM record_events WHERE kind=? AND recordId=?', (kind, row['id']))
        if apply:
            db.event(connection, 'maintenance', '', 'purge', counts)
    return counts


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=os.environ.get('GB_DATABASE', '/var/lib/geekbird-api/geekbird.sqlite3'))
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('migrate')
    auth = commands.add_parser('set-password')
    auth.add_argument('--output', required=True)
    auth.add_argument('--generate', action='store_true', help='Write a generated password to a private sibling .password file.')
    b = commands.add_parser('backup')
    b.add_argument('--directory', required=True)
    b.add_argument('--prune-root', help='Expire known backup subfolders after a successful backup.')
    p = commands.add_parser('purge')
    p.add_argument('--apply', action='store_true', help='Default is a count-only dry run. Back up first.')
    args = parser.parse_args()
    if args.command == 'set-password':
        password = secrets.token_urlsafe(24) if args.generate else getpass.getpass('New API administrator password: ')
        if not args.generate and password != getpass.getpass('Repeat password: '):
            parser.error('Passwords do not match')
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if args.generate:
            with output.with_suffix('.password').open('x') as secret:
                secret.write(password + '\n')
        output.write_text(json.dumps(credential(password)) + '\n')
        output.chmod(0o600)
        print('Credential written. Restart the API after rotating it.')
    elif args.command == 'migrate':
        db.migrate(args.database)
        print('Schema ready; existing records and settings preserved.')
    elif args.command == 'backup':
        if not Path(args.database).is_file():
            parser.error('Database does not exist')
        print(backup(args.database, args.directory))
        if args.prune_root:
            prune_backups(args.prune_root)
    else:
        if not Path(args.database).is_file():
            parser.error('Database does not exist')
        print(json.dumps(purge(args.database, apply=args.apply)))


if __name__ == '__main__':
    main()
