"""
social_extractor.py - Извлечение ссылок на социальные сети (Instagram и др.) из текста анкет.
"""

import re
from typing import Optional, Tuple

INSTA_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_\.]{3,30})/?",
    re.I
)

INSTA_KEYWORD_PATTERN = re.compile(
    r"\b(?:instagram|insta|ig)\b[\s:▶︎\-—]+@?([a-zA-Z0-9_\.]{3,30})",
    re.I
)

INSTA_CONTEXT_PATTERN = re.compile(
    r"(?:\bfollow\b|\bdm\b|\bmessage\b|\bphoto\b|\bcontact\b|\bfind\s+me\b)[\s\w]{0,25}@([a-zA-Z0-9_\.]{3,30})",
    re.I
)

EXCLUDED_HANDLES = {
    "account", "photos", "link", "profile", "stories", "reels", "reel",
    "explore", "p", "tv", "com", "and", "the", "for", "with"
}


def extract_instagram(text: Optional[str]) -> Tuple[str, str]:
    """
    Извлекает Instagram handle и полный URL из текста описания или правил хоста.
    Возвращает: (instagram_url, instagram_handle).
    Если не найден - возвращает ("", "").
    """
    if not text:
        return "", ""

    # 1. Прямой URL: instagram.com/<handle>
    m = INSTA_URL_PATTERN.search(text)
    if m:
        handle = m.group(1).strip().rstrip("./")
        if handle.lower() not in EXCLUDED_HANDLES:
            return f"https://www.instagram.com/{handle}/", handle

    # 2. По ключевому слову Instagram: @handle, IG: handle
    m = INSTA_KEYWORD_PATTERN.search(text)
    if m:
        handle = m.group(1).strip().lstrip("@").rstrip("./")
        if handle.lower() not in EXCLUDED_HANDLES:
            return f"https://www.instagram.com/{handle}/", handle

    # 3. Упоминание в контексте соцсетей (@handle)
    m = INSTA_CONTEXT_PATTERN.search(text)
    if m:
        handle = m.group(1).strip().lstrip("@").rstrip("./")
        if handle.lower() not in EXCLUDED_HANDLES:
            return f"https://www.instagram.com/{handle}/", handle

    return "", ""
