"""Album discovery and original image downloads for the Windows interface."""
import re
import time
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from yupoo_26_27_downloader import AlbumLinks, HEADERS, safe_name


def album_address(value):
    value = value.strip()
    if '://' not in value:
        value = 'https://' + value
    url = urlsplit(value)
    if (url.scheme not in ('https', 'http') or not url.hostname
            or not url.hostname.endswith('.yupoo.com') or url.username or url.password):
        raise ValueError('请输入有效的 Yupoo 相册或分类地址。')
    return url._replace(fragment='').geturl()


def fetch(url, referer=None):
    headers = {**HEADERS, 'Referer': referer or urljoin(url, '/')}
    with urlopen(Request(url, headers=headers), timeout=35) as response:
        return response.read()


class AlbumPage(HTMLParser):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.photos = {}
        self.title = ''

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'meta' and values.get('property') == 'og:title':
            self.title = values.get('content') or ''
        original = values.get('data-origin-src')
        if tag == 'img' and original and values.get('data-type') != 'video':
            url = urljoin(self.url, original)
            parsed = urlsplit(url)
            if parsed.hostname == 'photo.yupoo.com' and parsed.scheme in ('http', 'https'):
                self.photos[url] = values.get('alt') or ''


def find_albums(address, keywords):
    source = fetch(address).decode('utf-8', errors='replace')
    url = urlsplit(address)
    terms = [term.strip().casefold() for term in re.split('[,，;；]', keywords) if term.strip()]

    def matches(title):
        return not terms or any(term in title.casefold() for term in terms)

    if re.fullmatch(r'/albums/\d+/?', url.path):
        parser = AlbumPage(address)
        parser.feed(source)
        title = parser.title or url.path.strip('/').replace('/', ' ')
        return [(title, address)] if matches(title) else []

    albums = {}
    pending = {1}
    seen = set()
    while pending:
        page = min(pending)
        pending.remove(page)
        seen.add(page)
        query = [(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True) if k != 'page']
        if page != 1 or any(k == 'page' for k, _ in parse_qsl(url.query)):
            query.append(('page', str(page)))
        page_url = url._replace(query=urlencode(query)).geturl()
        if page_url != address:
            source = fetch(page_url).decode('utf-8', errors='replace')
        parser = AlbumLinks()
        parser.feed(source)
        for title, href in parser.items:
            link = urlsplit(urljoin(page_url, href))
            if link.netloc == url.netloc and re.fullmatch(r'/albums/\d+/?', link.path):
                albums.setdefault(link.path.rstrip('/'), (title, link._replace(fragment='').geturl()))
        pages = {int(n) for n in re.findall(r'[?&]page=(\d+)', unescape(source))}
        pending.update(pages - seen - {0})
    return [(title, link) for title, link in albums.values() if matches(title)]


def image_info(data):
    """Return the stored horizontal pixel count and the image extension."""
    if len(data) >= 24 and data.startswith(b'\x89PNG\r\n\x1a\n') and data[12:16] == b'IHDR':
        return int.from_bytes(data[16:20], 'big'), '.png'
    if len(data) >= 10 and data.startswith((b'GIF87a', b'GIF89a')):
        return int.from_bytes(data[6:8], 'little'), '.gif'
    if len(data) >= 30 and data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        kind = data[12:16]
        if kind == b'VP8X':
            return 1 + int.from_bytes(data[24:27], 'little'), '.webp'
        if kind == b'VP8L' and data[20] == 0x2f:
            return 1 + (int.from_bytes(data[21:23], 'little') & 0x3fff), '.webp'
        if kind == b'VP8 ' and data[23:26] == b'\x9d\x01\x2a':
            return int.from_bytes(data[26:28], 'little') & 0x3fff, '.webp'
    if data.startswith(b'\xff\xd8'):
        i = 2
        frame_markers = {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}
        while i + 3 < len(data) and data[i] == 0xff:
            i += 1
            if data[i] == 0xff:
                continue
            marker = data[i]
            i += 1
            if marker in (0xd9, 0xda):
                break
            size = int.from_bytes(data[i:i + 2], 'big')
            if size < 2 or i + size > len(data):
                break
            if marker in frame_markers and size >= 8:
                return int.from_bytes(data[i + 5:i + 7], 'big'), '.jpg'
            i += size
    raise ValueError('无法识别图片格式或读取宽度')


def download(albums, destination, minimum_width, report):
    destination.mkdir(parents=True, exist_ok=True)
    saved = skipped = failed = existing = 0
    with (destination / '下载清单.txt').open('w', encoding='utf-8') as manifest:
        for index, (title, address) in enumerate(albums, 1):
            manifest.write(f'{title}\t{address}\n')
            manifest.flush()
            report('status', f'正在下载 {index}/{len(albums)}：{title}')
            try:
                page = AlbumPage(address)
                page.feed(fetch(address).decode('utf-8', errors='replace'))
                if not page.photos:
                    raise ValueError('页面未提供可下载的原图地址')
                album_id = urlsplit(address).path.rstrip('/').split('/')[-1]
                folder = destination / f'{safe_name(title)[:85]} [{album_id}]'
                folder.mkdir(exist_ok=True)
                for url, alt in page.photos.items():
                    path = urlsplit(url).path.split('/')
                    name = (alt or path[-1]).rsplit('.', 1)[0]
                    photo_id = safe_name(path[-2])[:30]
                    stem = f'{safe_name(name)[:65]} [{photo_id}]'
                    try:
                        previous = next((folder / (stem + ext) for ext in ('.jpg', '.png', '.gif', '.webp')
                                         if (folder / (stem + ext)).is_file()), None)
                        if previous is not None:
                            try:
                                width, _ = image_info(previous.read_bytes())
                            except ValueError:
                                pass
                            else:
                                if width >= minimum_width:
                                    existing += 1
                                else:
                                    skipped += 1
                                continue
                        data = fetch(url, address)
                        width, suffix = image_info(data)
                        if width < minimum_width:
                            skipped += 1
                            continue
                        output = folder / (stem + suffix)
                        partial = output.with_suffix('.part')
                        partial.write_bytes(data)
                        partial.replace(output)
                        saved += 1
                    except Exception as error:
                        failed += 1
                        report('log', f'{stem}：{error}')
                    finally:
                        time.sleep(0.12)
            except Exception as error:
                failed += 1
                report('log', f'{title}：{error}')
            report('progress', (index, len(albums)))
    return f'保存 {saved} 张 · 已存在 {existing} 张 · 宽度不足 {skipped} 张 · 失败 {failed} 项'
