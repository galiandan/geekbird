#!/usr/bin/env python3
"""Refresh self-hosted font subsets after editing Chinese copy. Network needed only here."""
from html.parser import HTMLParser
import hashlib
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from release import PAGES, ROOT
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': UA}), timeout=45) as response:
        return response.read()


def main():
    content = Text()
    for name in PAGES:
        content.feed((ROOT / name).read_text(encoding='utf-8'))
    text = ''.join(content.parts) + ''.join((ROOT / name).read_text(encoding='utf-8') for name in ('assets/app.js', 'assets/forms.js'))
    chinese = ''.join(sorted({char for char in text if ord(char) > 127}))
    latin = ''.join(chr(code) for code in range(32, 127))
    folder = ROOT / 'assets/fonts'
    folder.mkdir(exist_ok=True)
    css_parts = []
    # Request all weights together so Google serves one variable WOFF2 per family.
    for family, slug, weights, chars, license_folder in [
        ('Noto Sans SC', 'noto-sans-sc', '300;400;500', chinese, 'notosanssc'),
        ('Manrope', 'manrope', '400;500;600', latin, 'manrope'),
    ]:
        query = urlencode({'family': family + ':wght@' + weights, 'display': 'swap', 'text': chars})
        css = fetch('https://fonts.googleapis.com/css2?' + query).decode()
        urls = set(re.findall(r'url\((https://[^)]+)\)', css))
        assert len(urls) == 1 and "format('woff2')" in css, f'Unexpected font response for {family}'
        font = fetch(urls.pop())
        assert font[:4] == b'wOF2', f'Invalid WOFF2 response for {family}'
        license_text = fetch(f'https://raw.githubusercontent.com/google/fonts/main/ofl/{license_folder}/OFL.txt')
        assert b'SIL OPEN FONT LICENSE' in license_text
        (folder / f'{slug}.woff2').write_bytes(font)
        version = hashlib.sha256(font).hexdigest()[:12]
        if slug == 'noto-sans-sc':
            for name in PAGES:
                page = ROOT / name
                page.write_text(re.sub(r'/assets/fonts/noto-sans-sc\.woff2(?:\?v=[^"]+)?',
                                       f'/assets/fonts/noto-sans-sc.woff2?v={version}',
                                       page.read_text(encoding='utf-8')), encoding='utf-8')
        (folder / f'{slug}-OFL.txt').write_bytes(license_text)
        ranges = re.findall(r'unicode-range:\s*([^;]+);', css)
        range_rule = f'\n  unicode-range: {ranges[0]};' if ranges else ''
        low, *_, high = weights.split(';')
        css_parts.append(f"@font-face {{\n  font-family: '{family}';\n  font-style: normal;\n  font-weight: {low} {high};\n  font-display: swap;\n  src: url('/assets/fonts/{slug}.woff2?v={version}') format('woff2');{range_rule}\n}}")
        print(f'{family}: {len(chars)} characters; {len(font):,} bytes')
    (folder / 'fonts.css').write_text('\n\n'.join(css_parts) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
