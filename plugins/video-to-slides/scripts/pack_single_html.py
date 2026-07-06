#!/usr/bin/env python3
"""
pack_single_html.py — 分割ソース版デッキ（index.html + assets/ + img/）を
単一の自己完結HTMLに固める（video-to-slides スキル用）

CSS・JS はインライン化し、画像は base64 の data URI として埋め込む。
Pillow があれば画像を幅1600px・JPEG品質82に再圧縮してファイルサイズを抑える
（再圧縮後の方が大きくなる場合は元データを使う）。

Usage:
  python3 pack_single_html.py DECK_DIR/index.html OUTPUT.html
"""

import argparse
import base64
import io
import re
import sys
from pathlib import Path

MIME = {
    "jpg": "jpeg", "jpeg": "jpeg", "png": "png",
    "gif": "gif", "webp": "webp", "svg": "svg+xml",
}


def image_data_uri(path, max_width=1600, quality=82):
    raw = path.read_bytes()
    data = raw
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        if img.width > max_width:
            img = img.resize(
                (max_width, round(img.height * max_width / img.width)),
                Image.LANCZOS,
            )
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
        if len(buf.getvalue()) < len(raw):
            data = buf.getvalue()
            return "data:image/jpeg;base64," + base64.b64encode(data).decode()
    except ImportError:
        pass
    mime = MIME.get(path.suffix.lower().lstrip("."), "jpeg")
    return f"data:image/{mime};base64," + base64.b64encode(data).decode()


def pack(src_html, out_html):
    src = Path(src_html)
    base = src.parent
    html = src.read_text(encoding="utf-8")

    def inline_css(m):
        p = base / m.group(1)
        return "<style>\n" + p.read_text(encoding="utf-8") + "\n</style>"

    def inline_js(m):
        p = base / m.group(1)
        return "<script>\n" + p.read_text(encoding="utf-8") + "\n</script>"

    def inline_img(m):
        p = base / m.group(1)
        if not p.exists():
            sys.stderr.write(f"warn: missing image {p}\n")
            return m.group(0)
        return f'src="{image_data_uri(p)}"'

    html = re.sub(
        r'<link\s+rel="stylesheet"\s+href="([^"]+)"\s*/?>', inline_css, html
    )
    html = re.sub(r'<script\s+src="([^"]+)"\s*>\s*</script>', inline_js, html)
    html = re.sub(r'src="((?!data:|https?:)[^"]+\.(?:jpe?g|png|gif|webp|svg))"',
                  inline_img, html)

    leftover = re.findall(
        r'(?:src|href)="((?!data:|https?:|mailto:|#)[^"]+)"', html
    )
    out = Path(out_html)
    out.write_text(html, encoding="utf-8")

    size_mb = out.stat().st_size / 1024 / 1024
    print(f"packed: {out}  ({size_mb:.1f} MB)")
    if leftover:
        print(f"warn: unresolved local refs remain: {leftover}", file=sys.stderr)
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_html")
    ap.add_argument("out_html")
    args = ap.parse_args()
    sys.exit(pack(args.src_html, args.out_html))


if __name__ == "__main__":
    main()
