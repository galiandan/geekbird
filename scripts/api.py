#!/usr/bin/env python3
"""Build a private API package, entirely separate from Cloudflare assets."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def build():
    files = {str(path.relative_to(ROOT / 'server')): path.read_bytes()
             for path in sorted((ROOT / 'server/api').rglob('*'))
             if path.is_file() and path.suffix in ('.py', '.sql', '.html', '.js', '.txt') and '__pycache__' not in path.parts}
    for path in sorted((ROOT / 'deploy').glob('*api*')):
        files['deploy/' + path.name] = path.read_bytes()
    errors = []
    for prefix, origin in (('gb', '$geekbird_api_origin'), ('gb_preview', '$geekbird_preview_origin')):
        for name, status, code, message in [('too_large', 413, 'BODY_TOO_LARGE', '提交内容过长，请缩短后重试。'),
                                           ('rate_limited', 429, 'RATE_LIMITED', '提交过于频繁，请稍后重试。'),
                                           ('unavailable', 503, 'UNAVAILABLE', '服务暂时不可用，请保留内容稍后重试。')]:
            body = json.dumps({'error': {'code': code, 'message': message}}, ensure_ascii=False)
            errors.append(f'''location @{prefix}_{name} {{
    default_type application/json;
    charset utf-8;
    add_header Access-Control-Allow-Origin {origin} always;
    add_header Vary Origin always;
    add_header Cache-Control no-store always;
    add_header Retry-After 10 always;
    return {status} '{body}';
}}
''')
    files['deploy/nginx-api-errors.conf'] = '\n'.join(errors).encode()
    files['manifest.json'] = json.dumps({key: hashlib.sha256(value).hexdigest() for key, value in files.items()}, indent=2).encode()
    output = ROOT / 'dist/geekbird-api.tar.gz'
    output.parent.mkdir(exist_ok=True)
    with tarfile.open(output, 'w:gz') as package:
        for name, value in files.items():
            entry = tarfile.TarInfo(name)
            entry.mode, entry.size = 0o644, len(value)
            package.addfile(entry, io.BytesIO(value))
    print(f'Private API package: {output.relative_to(ROOT)} ({len(files)} files)')
    return output


if __name__ == '__main__':
    build()
