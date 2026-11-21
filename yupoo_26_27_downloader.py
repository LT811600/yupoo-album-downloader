#!/usr/bin/env python3
"""Download images from Yupoo albums selected by title keywords."""
from __future__ import annotations

import html
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

CATEGORY = "https://yinglangfushi01.x.yupoo.com/categories/2848794"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
    "Referer": "https://yinglangfushi01.x.yupoo.com/",
}


def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers=HEADERS), timeout=35) as response:
        return response.read()


class AlbumLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[tuple[str, str]] = []
        self.href: str | None = None
        self.text: list[str] = []
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        href = values.get("href")
        if tag == "a" and href and "/albums/" in href:
            self.href, self.title, self.text = href, values.get("title") or "", []

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href is not None:
            title = self.title.strip() or " ".join("".join(self.text).split())
            if title:
                self.items.append((title, self.href))
            self.href, self.title, self.text = None, "", []


class AlbumImages(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        values = dict(attrs)
        src = values.get("data-src") or values.get("src") or values.get("data-original")
        if src and "photo.yupoo.com" in urljoin(CATEGORY, src):
            self.images.append((html.unescape(values.get("alt") or "").strip(), urljoin(CATEGORY, src)))


def safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".")
    return name or "未命名相册"


def largest_image(url: str) -> str:
    parsed = urlparse(url)
    path = re.sub(r"/(?:small|medium|thumb)\.(jpg|jpeg|png|webp)$", r"/big.\1", parsed.path, flags=re.I)
    if path == parsed.path:
        path = re.sub(r"/[^/]+$", "/big.jpg", parsed.path)
    return parsed._replace(path=path).geturl()


def filename_from(url: str, alt: str, index: int) -> str:
    name = safe_name(alt)
    if name == "未命名相册":
        name = Path(urlparse(url).path).parent.name or f"image_{index:03d}.jpg"
    if not Path(name).suffix:
        name += ".jpg"
    return name


def get_albums(keywords: list[str]) -> list[tuple[str, str]]:
    first = fetch(CATEGORY).decode("utf-8", errors="replace")
    parser = AlbumLinks()
    parser.feed(first)
    items = list(parser.items)
    pages = [int(n) for n in re.findall(r"[?&]page=(\d+)", html.unescape(first))]
    for page in range(2, max(pages, default=1) + 1):
        page_parser = AlbumLinks()
        page_parser.feed(fetch(f"{CATEGORY}?page={page}").decode("utf-8", errors="replace"))
        items.extend(page_parser.items)
        time.sleep(0.4)
    unique = {urljoin(CATEGORY, link): (title, urljoin(CATEGORY, link)) for title, link in items}
    # Comma/Chinese comma/semicolon separate alternatives: any term may match.
    terms = [term.casefold() for term in keywords if term]
    return [(title, link) for title, link in unique.values()
            if not terms or any(term in title.casefold() for term in terms)]


def save_album(title: str, album_url: str, destination: Path) -> tuple[int, int]:
    album_dir = destination / safe_name(title)
    album_dir.mkdir(parents=True, exist_ok=True)
    parser = AlbumImages()
    parser.feed(fetch(album_url).decode("utf-8", errors="replace"))
    images = list(dict.fromkeys(parser.images))
    good = failed = 0
    for index, (alt, thumb) in enumerate(images, 1):
        original = largest_image(thumb)
        filename = filename_from(original, alt, index)
        output = album_dir / filename
        if output.exists() and output.stat().st_size > 0:
            good += 1
            continue
        try:
            data = fetch(original)
            if not (data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG") or b"RIFF" in data[:12]):
                raise ValueError("返回内容不是可识别的图片文件")
            output.write_bytes(data)
            good += 1
            print(f"    已保存 {filename} ({len(data) // 1024} KB)")
        except Exception as exc:
            failed += 1
            print(f"    失败 {filename}: {exc}")
        time.sleep(0.15)
    return good, failed


def main() -> int:
    print("Yupoo 相册图片下载器")
    print("输入相册名称关键词；多个关键词用逗号分开（任意一个匹配即可）。")
    print("直接回车使用默认关键词：26,27")
    raw = input("关键词：").strip()
    keywords = [s.strip() for s in re.split(r"[,，;；]", raw or "26,27") if s.strip()]
    default_dir = Path(sys.executable).resolve().parent / "Yupoo下载" if getattr(sys, "frozen", False) else Path(__file__).resolve().parent / "Yupoo下载"
    folder = input(f"保存位置（直接回车使用 {default_dir}）：").strip().strip('"')
    destination = Path(folder).expanduser() if folder else default_dir
    print(f"正在读取相册，关键词：{'、'.join(keywords)}")
    try:
        albums = get_albums(keywords)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"读取 Yupoo 分类失败：{exc}\n请确认网络可访问 Yupoo，然后重新运行。已有文件会跳过。")
        input("按回车退出……")
        return 1
    if not albums:
        print("没有找到名称匹配的相册。")
        input("按回车退出……")
        return 0
    destination.mkdir(parents=True, exist_ok=True)
    print(f"找到 {len(albums)} 个相册，保存到：{destination}")
    total_ok = total_failed = 0
    with (destination / "下载清单.txt").open("w", encoding="utf-8") as manifest:
        for number, (title, album_url) in enumerate(albums, 1):
            print(f"[{number}/{len(albums)}] {title}")
            manifest.write(f"{title}\t{album_url}\n")
            manifest.flush()
            try:
                ok, failed = save_album(title, album_url, destination)
                total_ok += ok
                total_failed += failed
            except Exception as exc:
                total_failed += 1
                print(f"    相册读取失败：{exc}")
            time.sleep(0.4)
    print(f"完成：图片 {total_ok} 张，失败 {total_failed} 项。")
    input("按回车退出……")
    return 0 if total_failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
