#!/usr/bin/env python3
"""Validate and package the static site using only the Python standard library."""
import argparse
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tarfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
PAGES = ("index.html", "service/index.html", "disclaimer/index.html", "booking/index.html", "feedback/index.html")
FILES = (*PAGES, "config.js", "assets/app.js", "assets/forms.js", "assets/forms.css", "assets/style.css", "assets/logo.svg",
         "assets/images/feathers.webp", "assets/images/feathers-mobile.webp",
         "assets/images/landscape.webp", "assets/images/landscape-mobile.webp",
         "assets/images/architecture.webp", "assets/images/architecture-mobile.webp",
         "assets/fonts/fonts.css", "assets/fonts/noto-sans-sc.woff2", "assets/fonts/manrope.woff2",
         "assets/fonts/noto-sans-sc-OFL.txt", "assets/fonts/manrope-OFL.txt")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.platform_links = []
        self.forms = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            assert attrs["id"] not in self.ids, f"Duplicate HTML id: {attrs['id']}"
            self.ids.add(attrs["id"])
        self.forms += tag in ("form", "input", "textarea")
        for key in ("href", "src"):
            if attrs.get(key):
                self.links.append(attrs[key])
        if "data-config-link" in attrs:
            self.platform_links.append(attrs)


def file_for_url(url):
    path = unquote(urlsplit(url).path)
    if path.endswith("/"):
        path += "index.html"
    return path.lstrip("/")


def validate():
    for name in FILES:
        path = ROOT / name
        assert path.is_file() and not path.is_symlink(), f"Missing or linked file: {name}"
        assert path.stat().st_size, f"Empty file: {name}"
    pages = {}
    for name in PAGES:
        page = Page()
        page.feed((ROOT / name).read_text(encoding="utf-8"))
        if name in ('booking/index.html', 'feedback/index.html'):
            assert page.forms, f"Missing service form in {name}"
        else:
            assert not page.forms, f"Unexpected form in {name}"
        pages[name] = page
    for name, page in pages.items():
        for link in page.links:
            parts = urlsplit(link)
            if parts.scheme or parts.netloc:
                continue
            assert link.startswith(("/", "#")), f"Use a root-relative URL: {name}: {link}"
            target = file_for_url(link) if parts.path else name
            assert target in FILES, f"Unpackaged link: {name}: {link}"
            if parts.fragment and target in pages:
                assert parts.fragment in pages[target].ids, f"Missing anchor: {name}: {link}"
    for name, page in pages.items():
        assert page.platform_links, f"Missing direct booking links: {name}"
        expected = {'bookingUrl'} if name == 'feedback/index.html' else {'bookingUrl', 'feedbackUrl'}
        assert {link['data-config-link'] for link in page.platform_links} == expected, f"Missing configurable links: {name}"
        for link in page.platform_links:
            assert not link.get('href') and link.get('aria-disabled') == 'true', f"Link must be initialized from config.js: {name}"
    css = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in FILES if name.endswith(".css"))
    referenced_images = set()
    for url in re.findall(r"url\(['\"]?([^'\")]+)['\"]?\)", css):
        target = file_for_url(url)
        assert target in FILES, f"Unpackaged stylesheet image: {url}"
        if target.endswith(".webp"):
            referenced_images.add(target)
    assert {name for name in FILES if name.endswith('.webp')} == referenced_images
    for name in referenced_images:
        data = (ROOT / name).read_bytes()
        assert data[:4] == b'RIFF' and data[8:12] == b'WEBP', f"Invalid WebP: {name}"
    for name in FILES:
        if name.endswith(".woff2"):
            assert (ROOT / name).read_bytes()[:4] == b"wOF2", f"Invalid WOFF2: {name}"
    config = (ROOT / "config.js").read_text(encoding="utf-8")
    for key in ('bookingUrl', 'feedbackUrl'):
        match = re.search(rf'{key}\s*:\s*("(?:[^"\\]|\\.)*")', config)
        assert match, f"Missing {key} in config.js"
        link = json.loads(match[1]).strip()
        if not link:
            continue
        assert link == {'bookingUrl': '/booking/', 'feedbackUrl': '/feedback/'}[key], f"{key} must use the site form"
    assert re.search(r'emergencyQQ\s*:\s*"[1-9][0-9]{4,14}"', config), "Configure a valid contact QQ before release"
    print(f"Checked {len(FILES)} production files, all local references, images and link configuration.")
    return {f"public/{name}": hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(FILES)}


def package(manifest):
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / "geekbird-site.tar.gz"
    temporary = output / ".geekbird-site.tar.gz.tmp"
    # Fixed metadata makes identical source files produce an identical release archive.
    with temporary.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as tar:
            for name in sorted(FILES):
                path = ROOT / name
                info = tarfile.TarInfo(f"public/{name}")
                info.size = path.stat().st_size
                info.mode = 0o644
                with path.open("rb") as source:
                    tar.addfile(info, source)
    with tarfile.open(temporary, "r:gz") as tar:
        assert set(tar.getnames()) == set(manifest)
        for name, expected in manifest.items():
            assert hashlib.sha256(tar.extractfile(name).read()).hexdigest() == expected
    temporary.replace(archive)
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    checksums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in (archive, manifest_path))
    (output / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    print(f"Packaged {archive.relative_to(ROOT)} ({archive.stat().st_size:,} bytes).")
    print("Only public/ contains deployable site files; design, docs and scripts are excluded.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate without writing a release package")
    args = parser.parse_args()
    try:
        manifest = validate()
        if not args.check:
            package(manifest)
    except (AssertionError, OSError, ValueError) as error:
        parser.exit(1, f"Release check failed: {error}\n")
