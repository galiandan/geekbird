#!/usr/bin/env python3
"""Deploy the API and isolated preview over SSH; production acceptance stays closed on first install."""
import argparse
import hashlib
from pathlib import Path
import subprocess

from api import build

REMOTE = r'''
import hashlib, json, os, pathlib, pwd, shutil, subprocess, sys, tarfile, time
from datetime import datetime, timezone
os.umask(0o077)
P = pathlib.Path
def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)
incoming = P('/tmp/geekbird-api-incoming.tar.gz')
assert hashlib.sha256(incoming.read_bytes()).hexdigest() == sys.argv[1], 'Package checksum mismatch'
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
base = P('/opt/geekbird-api')
release = base / 'releases' / stamp
release.mkdir(parents=True, mode=0o755)
for parent in (base, base / 'releases'): parent.chmod(0o755)
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
run('python3', '-m', 'venv', str(release / 'venv'))
run(str(release / 'venv/bin/pip'), 'install', '-r', str(release / 'api/requirements.txt'), '--index-url', 'https://mirrors.aliyun.com/pypi/simple/', '--disable-pip-version-check')
# A root-created virtual environment must be readable by the service users.
for path in (release / 'venv', *list((release / 'venv').rglob('*'))):
    if not path.is_symlink(): path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o100 else 0o644)
py = str(release / 'venv/bin/python')
previous = str((base / 'current').resolve()) if (base / 'current').exists() else ''
(release / 'previous-release.txt').write_text(previous + '\n')
for user, folder, allowed in [
    ('geekbird-api', 'geekbird-api', 'https://geekbird.org,https://47.120.64.37'),
    ('geekbird-preview', 'geekbird-preview', 'https://feat-self-hosted-booking-backend.geekbird.pages.dev,https://feat-self-hosted-booking-back.geekbird.pages.dev')]:
    try: account = pwd.getpwnam(user)
    except KeyError:
        run('useradd', '--system', '--user-group', '--home-dir', '/nonexistent', '--shell', '/usr/sbin/nologin', user)
        account = pwd.getpwnam(user)
    state, config = P('/var/lib') / folder, P('/etc') / folder
    state.mkdir(exist_ok=True, mode=0o700); os.chown(state, account.pw_uid, account.pw_gid)
    config.mkdir(exist_ok=True, mode=0o750); config.chmod(0o750); os.chown(config, 0, account.pw_gid)
    credential = config / 'credential.json'
    if not credential.exists(): run(py, '-m', 'api.manage', 'set-password', '--output', str(credential), '--generate', cwd=release)
    credential.chmod(0o640); os.chown(credential, 0, account.pw_gid)
    env = config / 'api.env'
    if not env.exists():
        env.write_text(f'GB_DATABASE={state}/geekbird.sqlite3\nGB_CREDENTIAL={credential}\nGB_ADMIN_ORIGIN=https://47.120.64.37\nGB_ALLOWED_ORIGINS={allowed}\n')
    env.chmod(0o640); os.chown(env, 0, account.pw_gid)
    database = state / 'geekbird.sqlite3'
    if database.exists():
        run(py, '-m', 'api.manage', '--database', str(database), 'backup', '--directory', f'/var/backups/{folder}/before-deploy', cwd=release)
    run('runuser', '-u', user, '--', py, '-m', 'api.manage', '--database', str(database), 'migrate', cwd=release)
backup_folder = P('/var/backups/geekbird-api'); backup_folder.mkdir(mode=0o700, exist_ok=True)
nginx = P('/etc/nginx/sites-available/geekbird.conf')
old_nginx = nginx.read_text()
(release / 'previous-nginx.conf').write_text(old_nginx)
snippets = P('/etc/nginx/snippets'); snippets.mkdir(exist_ok=True)
http_config = P('/etc/nginx/conf.d/geekbird-api.conf')
locations = snippets / 'geekbird-api-locations.conf'
errors = snippets / 'geekbird-api-errors.conf'
proxy = snippets / 'geekbird-api-proxy.conf'
replaced = {p: p.read_bytes() if p.exists() else None for p in (http_config, locations, errors, proxy)}
for target, name in [(http_config, 'nginx-api-http.conf'), (locations, 'nginx-api-locations.conf'), (errors, 'nginx-api-errors.conf'), (proxy, 'nginx-api-proxy.conf')]:
    shutil.copyfile(release / 'deploy' / name, target); target.chmod(0o644)
include = '    include /etc/nginx/snippets/geekbird-api-locations.conf;\n    include /etc/nginx/snippets/geekbird-api-errors.conf;'
if include not in old_nginx:
    assert old_nginx.count('    listen 443 ssl;') == 1
    nginx.write_text(old_nginx.replace('    listen 443 ssl;', '    listen 443 ssl;\n' + include))
try: run('nginx', '-t')
except Exception:
    nginx.write_text(old_nginx)
    for target, content in replaced.items():
        if content is None: target.unlink(missing_ok=True)
        else: target.write_bytes(content)
    raise
for name in ('geekbird-api.service', 'geekbird-api-preview.service', 'geekbird-api-backup.service', 'geekbird-api-backup.timer'):
    shutil.copyfile(release / 'deploy' / name, P('/etc/systemd/system') / name)
shutil.copyfile(release / 'deploy/geekbird-api.logrotate', '/etc/logrotate.d/geekbird-api')
link = base / 'current.next'; link.symlink_to(release); link.replace(base / 'current')
run('systemctl', 'daemon-reload')
try:
    run('systemctl', 'enable', '--now', 'geekbird-api', 'geekbird-api-preview', 'geekbird-api-backup.timer')
    run('systemctl', 'restart', 'geekbird-api', 'geekbird-api-preview')
    from urllib.request import urlopen
    for port in (8766, 8767):
        for attempt in range(20):
            try:
                with urlopen(f'http://127.0.0.1:{port}/api/v1/health', timeout=2) as response:
                    assert json.load(response)['status'] == 'ok'
                break
            except Exception:
                if attempt == 19: raise
                time.sleep(0.5)
    run('systemctl', 'reload', 'nginx')
    run('systemctl', 'start', 'geekbird-api-backup')
except Exception:
    if previous:
        rollback = base / 'current.rollback'; rollback.symlink_to(previous); rollback.replace(base / 'current')
        run('systemctl', 'restart', 'geekbird-api', 'geekbird-api-preview')
    else: run('systemctl', 'stop', 'geekbird-api', 'geekbird-api-preview')
    nginx.write_text(old_nginx)
    for target, content in replaced.items():
        if content is None: target.unlink(missing_ok=True)
        else: target.write_bytes(content)
    run('nginx', '-t'); run('systemctl', 'reload', 'nginx')
    raise
incoming.unlink()
print(json.dumps({'release': str(release), 'previous': previous, 'productionPasswordFile': '/etc/geekbird-api/credential.password', 'previewPasswordFile': '/etc/geekbird-preview/credential.password'}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='root@47.120.64.37')
    args = parser.parse_args()
    if not args.host or args.host.startswith('-'):
        parser.error('Invalid SSH target')
    package = build()
    checksum = hashlib.sha256(package.read_bytes()).hexdigest()
    subprocess.run(['scp', '-o', 'BatchMode=yes', str(package), args.host + ':/tmp/geekbird-api-incoming.tar.gz'], check=True)
    subprocess.run(['ssh', '-o', 'BatchMode=yes', args.host, 'python3', '-', checksum], input=REMOTE, text=True, check=True)


if __name__ == '__main__':
    main()
