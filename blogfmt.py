"""Renders the plain text typed in the admin blog editor into post HTML.

Kept server-side so the format has exactly one implementation — both the
published page and the editor's live preview call through here.

Block markers, each at the start of a line:

    / Heading           -> section heading
    // Subheading       -> smaller heading
    > quoted line       -> blockquote (consecutive lines merge)
    - list item         -> bullet list (consecutive lines merge)
    # note to self      -> dropped entirely, never published
    [Image #1]          -> an image uploaded to this post
    https://x.com/…/status/…  -> an embedded tweet

Inline, anywhere:

    [text](url)         -> link
    **text**            -> bold

Blank lines separate paragraphs; single newlines become <br>. Everything is
HTML-escaped, so nothing typed into the editor can inject markup.
"""
import html
import re
from typing import Optional

# [text](url) — text may not contain brackets, url may not contain spaces or ')'
_LINK_RE = re.compile(r'\[([^\[\]]+)\]\((\S+?)\)')
_BOLD_RE = re.compile(r'\*\*(\S(?:[^*]*\S)?)\*\*')
_IMAGE_LINE_RE = re.compile(r'^\[Image\s*#(\d+)\]$')
# One dash per nesting level: "- top", "-- under it", "--- under that".
# The dashes must be followed by a space, so "-5 degrees" stays prose.
_LIST_RE = re.compile(r'^(-+)(?:[ \t]+(.*))?$')
MAX_LIST_DEPTH = 4  # deeper than this and the indent marches off the column
_TWEET_URL_RE = re.compile(
    r'^https?://(?:www\.|mobile\.)?(?:twitter\.com|x\.com)/[^/\s]+/status(?:es)?/(\d+)',
    re.IGNORECASE,
)

_PLACEHOLDER = '\x00{}\x00'
_PLACEHOLDER_RE = re.compile(r'\x00(\d+)\x00')


def tweet_id_from(url: str) -> Optional[str]:
    """The numeric id in a tweet URL, or None if it isn't one."""
    match = _TWEET_URL_RE.match(url.strip())
    return match.group(1) if match else None


def find_tweet_ids(content: str) -> list:
    """Every tweet the post embeds, in order, without duplicates."""
    found = []
    for raw in (content or '').replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = raw.strip()
        if line.startswith('#'):
            continue  # a commented-out tweet shouldn't be fetched
        tweet_id = tweet_id_from(line)
        if tweet_id and tweet_id not in found:
            found.append(tweet_id)
    return found


def _safe_href(url: str) -> Optional[str]:
    """Allow only absolute http(s) and site-relative links."""
    if url.startswith(('http://', 'https://', '/')):
        return url
    return None


def _inline(text: str) -> str:
    """Escape a run of text, then apply link and bold markup."""
    anchors = []

    def take_link(match):
        href = _safe_href(match.group(2))
        if href is None:
            return match.group(0)  # leave odd-looking brackets alone
        label = _inline_escape(match.group(1))
        anchors.append(
            '<a href="{}" target="_blank" rel="noopener">{}</a>'.format(
                _inline_escape(href), label
            )
        )
        return _PLACEHOLDER.format(len(anchors) - 1)

    # Links are pulled out first and parked behind placeholders, so neither the
    # escaping pass nor the bold pass can chew through the anchor markup.
    parked = _LINK_RE.sub(take_link, text)
    escaped = _inline_escape(parked)
    bolded = _BOLD_RE.sub(lambda m: '<strong>{}</strong>'.format(m.group(1)), escaped)
    return _PLACEHOLDER_RE.sub(lambda m: anchors[int(m.group(1))], bolded)


def _inline_escape(text: str) -> str:
    return html.escape(text, quote=True)


def _image_tag(image, base: str) -> str:
    return (
        '<img src="{}/blogimages/{}" width="{}" height="{}" alt="" loading="lazy">'
    ).format(base, image.id, image.width, image.height)


def _tweet_card(tweet, base: str) -> str:
    """A static tweet card. No third-party script, no tracking — the text and
    avatar were copied into our own database when the post was published."""
    body = '<br>'.join(_inline_escape(line) for line in (tweet.text or '').split('\n'))
    url = _inline_escape(tweet.url or '')
    avatar = (
        '<img class="tweet-avatar" src="{}/blogtweets/{}/avatar" alt="" '
        'width="44" height="44" loading="lazy">'
    ).format(base, tweet.tweet_id) if tweet.has_avatar else ''
    return (
        '<div class="tweet">'
        '<a class="tweet-head" href="{url}" target="_blank" rel="noopener">'
        '{avatar}'
        '<span class="tweet-who">'
        '<span class="tweet-name">{name}</span>'
        '<span class="tweet-handle">@{handle}</span>'
        '</span>'
        '</a>'
        '<div class="tweet-text">{body}</div>'
        '<a class="tweet-date" href="{url}" target="_blank" rel="noopener">{date}</a>'
        '</div>'
    ).format(
        url=url,
        avatar=avatar,
        name=_inline_escape(tweet.author_name or ''),
        handle=_inline_escape(tweet.author_handle or ''),
        body=body,
        date=_inline_escape(tweet.date_label or ''),
    )


def _render_list(items) -> str:
    """Turn [(depth, html), …] into properly nested <ul>s.

    A sublist belongs inside the <li> above it, not beside it, so the browser
    indents it and CSS can pick the marker off the nesting depth. A level that
    jumps ahead of its parent — "---" with no "--" above it — is pulled back to
    the deepest level that actually exists rather than dropped.
    """
    root = []
    stack = [root]  # stack[n] holds the children of the item at depth n
    for depth, html_text in items:
        depth = max(1, min(depth, len(stack)))
        while len(stack) > depth:
            stack.pop()
        node = {'html': html_text, 'children': []}
        stack[-1].append(node)
        stack.append(node['children'])
    return _render_list_nodes(root)


def _render_list_nodes(nodes) -> str:
    if not nodes:
        return ''
    parts = ['<ul>']
    for node in nodes:
        parts.append('<li>' + node['html'] + _render_list_nodes(node['children']) + '</li>')
    parts.append('</ul>')
    return ''.join(parts)


def render(content: str, images: dict = None, tweets: dict = None, base_url: str = '') -> str:
    """Render editor text to the HTML that goes inside `.blog-content`.

    `images` maps the N in `[Image #N]` to an object with `.id`, `.width` and
    `.height`. `tweets` maps a tweet id to a stored tweet. Anything referenced
    but missing degrades quietly rather than breaking the post.
    """
    if not content:
        return ''

    images = images or {}
    tweets = tweets or {}
    base = base_url.rstrip('/')

    # NULs would collide with the link placeholders; nothing legitimate uses them.
    lines = content.replace('\x00', '').replace('\r\n', '\n').replace('\r', '\n').split('\n')

    out = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index].strip()

        # Blank line, or a note to self — neither reaches the page.
        if not line or line.startswith('#'):
            index += 1
            continue

        # A marker with nothing after it is a line mid-typing, not content.
        if line.startswith('//'):
            text = line[2:].strip()
            if text:
                out.append('<h4 class="blog-subheading">{}</h4>'.format(_inline(text)))
            index += 1
            continue

        if line.startswith('/'):
            text = line[1:].strip()
            if text:
                out.append('<h3 class="blog-heading">{}</h3>'.format(_inline(text)))
            index += 1
            continue

        if line.startswith('>'):
            quoted = []
            while index < total:
                current = lines[index].strip()
                if not current.startswith('>'):
                    break
                text = current[1:].strip()
                if text:
                    quoted.append(_inline(text))
                index += 1
            if quoted:
                out.append('<blockquote>{}</blockquote>'.format('<br>'.join(quoted)))
            continue

        if _LIST_RE.match(line):
            items = []
            while index < total:
                item = _LIST_RE.match(lines[index].strip())
                if not item:
                    break
                text = (item.group(2) or '').strip()
                if text:
                    items.append((min(len(item.group(1)), MAX_LIST_DEPTH), _inline(text)))
                index += 1
            if items:
                out.append(_render_list(items))
            continue

        image_match = _IMAGE_LINE_RE.match(line)
        if image_match:
            image = images.get(int(image_match.group(1)))
            if image is not None:
                out.append(_image_tag(image, base))
            index += 1
            continue

        tweet_id = tweet_id_from(line)
        if tweet_id:
            tweet = tweets.get(tweet_id)
            if tweet is not None:
                out.append(_tweet_card(tweet, base))
            else:
                # Not fetched (yet, or at all) — a plain link still works.
                out.append(
                    '<p><a href="{0}" target="_blank" rel="noopener">{0}</a></p>'.format(
                        _inline_escape(line)
                    )
                )
            index += 1
            continue

        # Anything else is body text, running until a blank line or a new block.
        paragraph = []
        while index < total:
            current = lines[index].strip()
            if not current or _starts_block(current):
                break
            paragraph.append(_inline(current))
            index += 1
        if paragraph:
            out.append('<p>{}</p>'.format('<br>'.join(paragraph)))

    return '\n'.join(out)


def _starts_block(line: str) -> bool:
    """Whether a line opens a new block, so a paragraph should stop before it."""
    return (
        line.startswith(('/', '>', '#'))
        or _LIST_RE.match(line) is not None
        or _IMAGE_LINE_RE.match(line) is not None
        or tweet_id_from(line) is not None
    )


def snippet(content: str, length: int = 60) -> str:
    """A one-line preview of a post, for the admin draft list."""
    text = ' '.join((content or '').split())
    if len(text) <= length:
        return text
    return text[:length].rstrip() + '…'
