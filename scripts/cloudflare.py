#!/usr/bin/env python3
"""Build Cloudflare Pages output (no npm dependencies)."""
import json
import hashlib
import shutil
import zipfile
import os
import re
from urllib.parse import urlsplit

from release import FILES, ROOT, validate


def build():
    validate()
    output = ROOT / 'dist' / 'cloudflare'
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for name in FILES:
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    for name in ('404.html', '_headers', 'robots.txt', 'sitemap.xml'):
        shutil.copyfile(ROOT / 'cloudflare' / name, output / name)
    source = (output / 'config.js').read_text(encoding='utf-8')
    config = {key: json.loads(re.search(rf'{key}\s*:\s*("(?:[^"\\]|\\.)*")', source)[1])
              for key in ('emergencyQQ', 'bookingUrl', 'feedbackUrl', 'apiBaseUrl', 'dataAdminUrl')}
    branch = os.environ.get('CF_PAGES_BRANCH', 'main')
    default_api = config['apiBaseUrl'] if branch == 'main' else 'https://47.120.64.37/_gb-preview/api/v1'
    api_base = os.environ.get('GEEKBIRD_API_BASE_URL', default_api).rstrip('/')
    if api_base:
        parsed = urlsplit(api_base)
        assert parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
        assert parsed.scheme == 'https' or (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1'))
        assert parsed.path.endswith('/api/v1'), 'API address must end in /api/v1'
        # Preview paths can have their own protected management prefix.
        config['dataAdminUrl'] = api_base[:-len('/api/v1')] + '/_gb-data/'
    else:
        config['dataAdminUrl'] = ''
    config.update(schemaVersion=2, apiBaseUrl=api_base, isPreview=branch != 'main' or api_base != 'https://47.120.64.37/api/v1')
    (output / 'config.js').write_text('window.GEEKBIRD_CONFIG = Object.freeze(' + json.dumps(config, ensure_ascii=False) + ');\n', encoding='utf-8')
    html = (ROOT / 'cloudflare/admin.html').read_text(encoding='utf-8')
    worker = (ROOT / 'cloudflare/worker.js').read_text(encoding='utf-8')
    assert worker.count('"__ADMIN_HTML__"') == 1
    assert worker.count('"__PUBLIC_CONFIG__"') == 1
    worker = worker.replace('"__ADMIN_HTML__"', json.dumps(html, ensure_ascii=False)).replace('"__PUBLIC_CONFIG__"', json.dumps(config, ensure_ascii=False))
    (output / '_worker.js').write_text(worker, encoding='utf-8')
    (output / '_routes.json').write_text(json.dumps({
        'version': 1,
        'include': ['/config.js', '/_*'],
        'exclude': [],
    }, indent=2) + '\n', encoding='utf-8')
    # Package only the explicit Pages output; secrets, VPS service and docs stay out.
    manifest = {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(output.rglob('*')) if path.is_file()}
    archive = ROOT / 'dist/geekbird-cloudflare-pages.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for name in manifest:
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            package.writestr(entry, (output / name).read_bytes())
    with zipfile.ZipFile(archive) as package:
        assert set(package.namelist()) == set(manifest)
        for name, expected in manifest.items():
            assert hashlib.sha256(package.read(name)).hexdigest() == expected
    (ROOT / 'dist/cloudflare-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'dist/cloudflare-SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
        for path in (archive, ROOT / 'dist/cloudflare-manifest.json')), encoding='utf-8')
    print(f'Cloudflare Pages output: {output.relative_to(ROOT)}')
    print(f'Verified {len(manifest)} files; archive: {archive.relative_to(ROOT)}')


if __name__ == '__main__':
    build()
