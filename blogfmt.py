"""Renders the plain text typed in the admin blog editor into post HTML.

Kept server-side so the format has exactly one implementation — the public
frontend just drops the returned HTML into `.blog-content`.

The format is deliberately tiny, covering what the hand-written posts in
`blogs/` actually use:

    blank line          -> paragraph break
    single newline      -> <br>
    [Image #1]          -> <img>, on its own line
    [text](https://…)   -> <a href target="_blank">
    **text**            -> <strong>

Everything is HTML-escaped up front, so nothing typed into the editor can
inject markup.
"""
import html
import re
from typing import Optional

# [text](url) — text may not contain brackets, url may not contain spaces or ')'
_LINK_RE = re.compile(r'\[([^\[\]]+)\]\((\S+?)\)')
_BOLD_RE = re.compile(r'\*\*(\S(?:[^*]*\S)?)\*\*')
# A line that is nothing but an image token. Matched after escaping, which
# leaves '[', '#' and ']' untouched.
_IMAGE_LINE_RE = re.compile(r'^\[Image\s*#(\d+)\]$')

_PLACEHOLDER = '\x00{}\x00'
_PLACEHOLDER_RE = re.compile(r'\x00(\d+)\x00')


def _safe_href(url: str) -> Optional[str]:
    """Allow only absolute http(s) and site-relative links."""
    if url.startswith(('http://', 'https://', '/')):
        return url
    return None


def _inline(text: str) -> str:
    """Apply link and bold markup to an already-escaped line."""
    anchors: list[str] = []

    def take_link(m: re.Match) -> str:
        href = _safe_href(m.group(2))
        if href is None:
            return m.group(0)  # leave odd-looking brackets alone
        anchors.append(
            f'<a href="{href}" target="_blank" rel="noopener">{m.group(1)}</a>'
        )
        return _PLACEHOLDER.format(len(anchors) - 1)

    # Links are parked behind placeholders so the bold pass can't chew through
    # the anchor markup it would otherwise see.
    text = _LINK_RE.sub(take_link, text)
    text = _BOLD_RE.sub(lambda m: f'<strong>{m.group(1)}</strong>', text)
    return _PLACEHOLDER_RE.sub(lambda m: anchors[int(m.group(1))], text)


def render(content: str, images: dict, base_url: str = '') -> str:
    """Render editor text to the HTML that goes inside `.blog-content`.

    `images` maps the N in `[Image #N]` to an object with `.id`, `.width` and
    `.height`. Tokens with no matching image are dropped.
    """
    if not content:
        return ''

    base = base_url.rstrip('/')
    # NULs would collide with the link placeholders; nothing legitimate uses them.
    escaped = html.escape(content.replace('\x00', ''), quote=True)

    out: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            out.append('<p>' + '<br>'.join(_inline(line) for line in paragraph) + '</p>')
            paragraph.clear()

    for raw_line in escaped.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = raw_line.strip()
        if not line:
            flush()
            continue

        image_match = _IMAGE_LINE_RE.match(line)
        if image_match:
            flush()
            image = images.get(int(image_match.group(1)))
            if image is not None:
                out.append(
                    f'<img src="{base}/blogimages/{image.id}" '
                    f'width="{image.width}" height="{image.height}" '
                    f'alt="" loading="lazy">'
                )
            continue

        paragraph.append(line)

    flush()
    return '\n'.join(out)


def snippet(content: str, length: int = 60) -> str:
    """A one-line preview of a post, for the admin draft list."""
    text = ' '.join(content.split())
    if len(text) <= length:
        return text
    return text[:length].rstrip() + '…'
