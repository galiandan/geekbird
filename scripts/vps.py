#!/usr/bin/env python3
"""Package the public site and the private Python settings service for a VPS."""
import io
import tarfile
import hashlib
import json
from release import ROOT, FILES, validate


def build():
    validate()
    output = ROOT / 'dist/geekbird-vps.tar.gz'
    output.parent.mkdir(exist_ok=True)
    files = [(ROOT / name, 'public/' + name) for name in FILES]
    files += [(ROOT / 'server/admin.py', 'server/admin.py'),
              (ROOT / 'cloudflare/admin.html', 'server/admin.html'),
              (ROOT / 'deploy/nginx-vps.conf', 'deploy/nginx-vps.conf')]
    manifest = {}
    with tarfile.open(output, 'w:gz') as archive:
        for source, name in files:
            content = source.read_bytes()
            manifest[name] = hashlib.sha256(content).hexdigest()
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            entry.mode = 0o644
            archive.addfile(entry, io.BytesIO(content))
        content = json.dumps(manifest, indent=2).encode()
        entry = tarfile.TarInfo('manifest.json')
        entry.size, entry.mode = len(content), 0o644
        archive.addfile(entry, io.BytesIO(content))
    print(f'Packaged {output.relative_to(ROOT)}')
    return output


if __name__ == '__main__':
    build()
