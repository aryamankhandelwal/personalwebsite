"""Fetches a tweet's content so it can be stored and rendered as a static card.

Uses the same public syndication endpoint that Twitter's own embed widget and
react-tweet use. No API key, but it is undocumented: treat every failure as
expected and let the caller fall back to showing a plain link.

The endpoint requires a token derived from the tweet id, and the derivation is
specified in JavaScript:

    ((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\\.)/g, '')

`Number.toString(36)` is not "the shortest string that round-trips" — V8 emits
digits until the remaining error falls under half an ulp, then rounds. So
_to_base36 below is a port of V8's DoubleToRadixCString rather than anything
simpler; a near-miss produces a different token and the endpoint just returns an
error page. Verified digit-for-digit against Node across a spread of ids.
"""
import math
import re
from datetime import datetime
from typing import Optional

import httpx

SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
# Avatars only ever come from Twitter's own image host — the URL arrives inside
# the API response, so it is not blindly trusted.
ALLOWED_IMAGE_HOSTS = ("pbs.twimg.com", "abs.twimg.com")
REQUEST_TIMEOUT = 12.0
MAX_AVATAR_BYTES = 2 * 1024 * 1024

_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
_TCO_TAIL_RE = re.compile(r'\s*https?://t\.co/\w+\s*$')


def _to_base36(value: float) -> str:
    """Port of V8's DoubleToRadixCString for radix 36."""
    if value == 0:
        return "0"
    negative = value < 0
    value = abs(value)

    integer = math.floor(value)
    fraction = value - integer
    delta = max(math.nextafter(0.0, 1.0), 0.5 * (math.nextafter(value, math.inf) - value))

    frac_digits = []
    if fraction >= delta:
        while True:
            fraction *= 36
            delta *= 36
            digit = int(fraction)
            frac_digits.append(digit)
            fraction -= digit
            if fraction > 0.5 or (fraction == 0.5 and (digit & 1)):
                if fraction + delta > 1:
                    # Round up, propagating the carry back through the digits.
                    i = len(frac_digits) - 1
                    while True:
                        if i < 0:
                            integer += 1
                            break
                        frac_digits[i] += 1
                        if frac_digits[i] < 36:
                            break
                        frac_digits.pop()
                        i -= 1
                    break
            if fraction < delta:
                break

    head = ""
    n = int(integer)
    if n == 0:
        head = "0"
    while n > 0:
        head = _DIGITS[n % 36] + head
        n //= 36

    out = head + ("." + "".join(_DIGITS[d] for d in frac_digits) if frac_digits else "")
    return ("-" + out) if negative else out


def syndication_token(tweet_id: str) -> str:
    return re.sub(r'(0+|\.)', '', _to_base36((int(tweet_id) / 1e15) * math.pi))


def _display_text(payload: dict) -> str:
    """The tweet's own words, without the trailing t.co link Twitter appends
    when the tweet carries media or a quoted tweet."""
    text = payload.get("text") or ""
    text_range = payload.get("display_text_range")
    if isinstance(text_range, list) and len(text_range) == 2:
        start, end = text_range
        if isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(text):
            return text[start:end].strip()
    return _TCO_TAIL_RE.sub('', text).strip()


def _date_label(payload: dict) -> str:
    raw = payload.get("created_at")
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return parsed.strftime("%b %-d, %Y")


def _avatar_url(payload: dict) -> Optional[str]:
    url = ((payload.get("user") or {}).get("profile_image_url_https")) or None
    if not url:
        return None
    # _normal is 48px; ask for the large original and downscale ourselves.
    url = url.replace("_normal.", "_400x400.")
    host = httpx.URL(url).host
    return url if host in ALLOWED_IMAGE_HOSTS else None


async def fetch_tweet(tweet_id: str) -> Optional[dict]:
    """Returns the fields needed to render a tweet, or None if anything is off.

    Never raises — a tweet that has been deleted, made private, or that the
    endpoint declines to serve should degrade to a plain link, not a 500.
    """
    params = {"id": tweet_id, "lang": "en", "token": syndication_token(tweet_id)}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://platform.twitter.com/",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(SYNDICATION_URL, params=params, headers=headers)
            if response.status_code != 200:
                return None
            if "application/json" not in response.headers.get("content-type", ""):
                return None  # the error page comes back as HTML
            payload = response.json()
            if not isinstance(payload, dict) or not payload.get("user"):
                return None

            user = payload.get("user") or {}
            result = {
                "tweet_id": tweet_id,
                "url": "https://x.com/{}/status/{}".format(
                    user.get("screen_name") or "i", tweet_id
                ),
                "author_name": user.get("name") or "",
                "author_handle": user.get("screen_name") or "",
                "text": _display_text(payload),
                "date_label": _date_label(payload),
                "avatar": None,
                "avatar_mime": None,
            }

            avatar_url = _avatar_url(payload)
            if avatar_url:
                try:
                    avatar = await client.get(avatar_url, headers=headers)
                    if (
                        avatar.status_code == 200
                        and avatar.headers.get("content-type", "").startswith("image/")
                        and len(avatar.content) <= MAX_AVATAR_BYTES
                    ):
                        result["avatar"] = avatar.content
                        result["avatar_mime"] = avatar.headers["content-type"].split(";")[0]
                except Exception:
                    pass  # a card without an avatar is still a fine card

            return result
    except Exception:
        return None
