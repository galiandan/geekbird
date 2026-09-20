#!/usr/bin/env python3
"""Publish the complete VPS website against the existing production API."""
import argparse
import hashlib
import subprocess

from vps import build

REMOTE = r'''
import hashlib, json, os, pathlib, shutil, sqlite3, subprocess, sys, tarfile, time
from datetime import datetime, timezone
from urllib.request import urlopen
P = pathlib.Path
os.umask(0o077)
def run(*args, **kwargs): subprocess.run(args, check=True, **kwargs)
def switch(path, target):
    temporary = path.with_name(path.name + '.next')
    temporary.symlink_to(target)
    temporary.replace(path)

incoming = P('/tmp/geekbird-vps-incoming.tar.gz')
assert hashlib.sha256(incoming.read_bytes()).hexdigest() == sys.argv[1], 'Checksum mismatch'
api = P('/opt/geekbird-api/current').resolve()
assert (api / 'api/app.py').is_file(), 'Deploy the API first with scripts/deploy_api.py'
sys.path.insert(0, str(api))
from api import db
from api.manage import backup
with urlopen('http://127.0.0.1:8766/api/v1/health', timeout=5) as r: assert json.load(r)['status'] == 'ok'
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
release = P('/var/www/geekbird/releases') / (stamp + '-self-hosted')
release.mkdir(mode=0o755)
with tarfile.open(incoming) as archive:
    for item in archive.getmembers():
        assert item.isfile() and not P(item.name).is_absolute() and '..' not in P(item.name).parts
        target = release / item.name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        target.write_bytes(archive.extractfile(item).read())
        target.chmod(0o644)
for directory in (release, *[p for p in release.rglob('*') if p.is_dir()]): directory.chmod(0o755)
manifest = json.loads((release / 'manifest.json').read_text())
for name, expected in manifest.items(): assert hashlib.sha256((release / name).read_bytes()).hexdigest() == expected, name
public_link, server_link = P('/var/www/geekbird/public'), P('/var/www/geekbird/current-server')
previous_public, previous_server = str(public_link.resolve()), str(server_link.resolve())
(release / 'previous-public.txt').write_text(previous_public + '\n')
(release / 'previous-server.txt').write_text(previous_server + '\n')
nginx = P('/etc/nginx/sites-available/geekbird.conf')
api_map = P('/etc/nginx/conf.d/geekbird-api.conf')
api_env = P('/etc/geekbird-api/api.env')
site_config = P('/var/lib/geekbird/config.json')
saved = {p: p.read_bytes() for p in (nginx, api_map, api_env, site_config)}
saved_stats = {p: p.stat() for p in saved}
legacy = json.loads(saved[site_config])
assert isinstance(legacy.get('emergencyQQ'), str)
database = P('/var/lib/geekbird-api/geekbird.sqlite3')
with db.connect(database) as connection: previous_settings = db.settings(connection)
backup_file = P('/var/backups') / ('geekbird-before-vps-' + stamp + '.tar.gz')
with tarfile.open(backup_file, 'w:gz') as archive:
    for source in (P(previous_public), P(previous_server), P('/var/lib/geekbird'), nginx, api_map, api_env):
        archive.add(source, arcname=str(source).lstrip('/'))
backup_file.chmod(0o600)
database_backup = backup(database, '/var/backups/geekbird-api/before-deploy')

try:
    text = saved[api_map].decode()
    start = text.index('map $http_origin $geekbird_api_origin {')
    end = text.index('\n}', start)
    if '"https://47.120.64.37" $http_origin;' not in text[start:end]:
        text = text[:end] + '\n    "https://47.120.64.37" $http_origin;' + text[end:]
    api_map.write_text(text)
    lines = saved[api_env].decode().splitlines()
    origin_line = next((i for i, line in enumerate(lines) if line.startswith('GB_ALLOWED_ORIGINS=')), None)
    if origin_line is None: lines.append('GB_ALLOWED_ORIGINS=https://geekbird.org,https://47.120.64.37')
    else:
        origins = lines[origin_line].split('=', 1)[1].split(',')
        if 'https://47.120.64.37' not in origins: origins.append('https://47.120.64.37')
        lines[origin_line] = 'GB_ALLOWED_ORIGINS=' + ','.join(origins)
    api_env.write_text('\n'.join(lines) + '\n')
    shutil.copyfile(release / 'deploy/nginx-vps.conf', nginx)
    run('nginx', '-t')
    switch(public_link, release / 'public')
    switch(server_link, release / 'server')
    run('systemctl', 'restart', 'geekbird-admin', 'geekbird-api')
    run('systemctl', 'reload', 'nginx')
    for attempt in range(20):
        try:
            with urlopen('https://47.120.64.37/config.js', timeout=3) as r:
                source = r.read().decode()
                assert '/booking/' in source and '/feedback/' in source and 'wjx.top' not in source
            with urlopen('https://47.120.64.37/api/v1/health', timeout=3) as r: assert json.load(r)['status'] == 'ok'
            break
        except Exception:
            if attempt == 19: raise
            time.sleep(.5)
    for name, expected in manifest.items():
        if not name.startswith('public/') or name == 'public/config.js': continue
        with urlopen('https://47.120.64.37/' + name[len('public/'):], timeout=8) as r:
            assert hashlib.sha256(r.read()).hexdigest() == expected, name
    # Only the initial legacy migration derives acceptance from the old entries.
    # Future website releases preserve the operator's current business settings.
    if legacy.get('schemaVersion') != 2:
        for key in ('bookingUrl', 'feedbackUrl'):
            assert isinstance(legacy.get(key), str), 'Resolve missing legacy entry before activation'
        with db.connect(database) as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('UPDATE service_settings SET acceptingBookings=?,acceptingFeedback=?,version=version+1 WHERE id=1',
                               (bool(legacy['bookingUrl'].strip()), bool(legacy['feedbackUrl'].strip())))
            db.event(connection, 'settings', '1', 'vps-activation', {'acceptingBookings': bool(legacy['bookingUrl'].strip()), 'acceptingFeedback': bool(legacy['feedbackUrl'].strip())}, 'VPS full-site deployment; preserve the legacy entry availability')
        # Use the existing service helper to atomically retain QQ and its ownership.
        import importlib.util
        spec = importlib.util.spec_from_file_location('vps_admin', release / 'server/admin.py')
        settings_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(settings_module)
        owner = site_config.stat()
        settings_module.write_config(site_config, {'schemaVersion': 2, 'emergencyQQ': legacy['emergencyQQ']})
        os.chown(site_config, owner.st_uid, owner.st_gid)
    with db.connect(database) as connection: current_settings = db.settings(connection)
    result = {'release': str(release), 'previousPublic': previous_public, 'previousServer': previous_server,
              'backup': str(backup_file), 'databaseBackup': str(database_backup), 'settings': current_settings}
    (release / 'deployment.json').write_text(json.dumps(result, indent=2) + '\n')
    run('systemctl', 'start', 'geekbird-api-backup')
except Exception:
    switch(public_link, previous_public); switch(server_link, previous_server)
    for path, content in saved.items():
        path.write_bytes(content)
        os.chown(path, saved_stats[path].st_uid, saved_stats[path].st_gid)
        path.chmod(saved_stats[path].st_mode & 0o777)
    with db.connect(database) as connection:
        connection.execute('UPDATE service_settings SET acceptingBookings=?,acceptingFeedback=?,closedMessage=?,version=version+1 WHERE id=1',
                           (previous_settings['acceptingBookings'], previous_settings['acceptingFeedback'], previous_settings['closedMessage']))
    run('nginx', '-t')
    run('systemctl', 'restart', 'geekbird-admin', 'geekbird-api')
    run('systemctl', 'reload', 'nginx')
    raise
incoming.unlink()
print(json.dumps(result, ensure_ascii=False))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='root@47.120.64.37')
    args = parser.parse_args()
    if not args.host or args.host.startswith('-'): parser.error('Invalid SSH target')
    package = build()
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    subprocess.run(['scp', '-o', 'BatchMode=yes', str(package), args.host + ':/tmp/geekbird-vps-incoming.tar.gz'], check=True)
    subprocess.run(['ssh', '-o', 'BatchMode=yes', args.host, '/opt/geekbird-api/current/venv/bin/python', '-', digest], input=REMOTE, text=True, check=True)


if __name__ == '__main__':
    main()
