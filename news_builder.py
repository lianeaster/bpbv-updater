"""Build HTML and translations snippets for a new news card."""

from __future__ import annotations

import html
import re
from pathlib import Path


def next_card_index(translations_js: str) -> int:
    found = [int(m.group(1)) for m in re.finditer(r"news\.card(\d+)Title", translations_js)]
    return max(found) + 1 if found else 1


def split_title_excerpt_detail(raw: str, excerpt_lines: int = 3) -> tuple[str, str, str]:
    """
    First non-empty line → title.
    Next `excerpt_lines` non-empty lines → excerpt (visible teaser on card).
    Everything after that → detail (hidden inside «Детальніше», no duplication).
    """
    text = raw.strip()
    if not text:
        return "", "", ""

    lines = text.splitlines()

    title = ""
    body_lines: list[str] = []
    found_title = False
    for line in lines:
        if not found_title:
            if line.strip():
                title = line.strip()
                found_title = True
            continue
        body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if not body:
        return title, "", ""

    non_empty = [l for l in body_lines if l.strip()]
    if len(non_empty) <= excerpt_lines:
        return title, body, ""

    taken = 0
    cut_index = 0
    for i, line in enumerate(body_lines):
        if line.strip():
            taken += 1
        if taken == excerpt_lines:
            cut_index = i + 1
            break

    excerpt = "\n".join(body_lines[:cut_index]).strip()
    detail = "\n".join(body_lines[cut_index:]).strip()
    return title, excerpt, detail


def paragraphs_to_html(text: str) -> str:
    """Turn plain text into <p> blocks; double newlines = new paragraph."""
    text = text.strip()
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not parts:
        return ""
    return "".join(f"<p>{html.escape(p).replace(chr(10), '<br />')}</p>" for p in parts)


def js_single_quoted_string(s: str) -> str:
    """Escape content for a JavaScript single-quoted string."""
    return (
        s.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("'", "\\'")
        .replace("\n", "\\n")
    )


def build_body_html(full_text: str, image_paths: list[str]) -> str:
    inner = paragraphs_to_html(full_text)
    imgs = []
    for p in image_paths:
        safe = html.escape(p, quote=True)
        imgs.append(
            f'<img src="{safe}" alt="" '
            f'style="max-width:100%;border-radius:8px;margin-top:0.75rem;display:block;" loading="lazy" />'
        )
    return inner + "".join(imgs)


def build_article_html(
    card_id: int,
    date_display: str,
    title: str,
    excerpt: str,
    body_html: str,
    rel_image: str | None,
) -> str:
    """One <article> block matching bpbv .news-card structure (no Facebook)."""
    keys = {
        "date": f"news.card{card_id}Date",
        "title": f"news.card{card_id}Title",
        "excerpt": f"news.card{card_id}Excerpt",
        "body": f"news.card{card_id}Body",
    }
    image_block = ""
    if rel_image:
        safe_src = html.escape(rel_image, quote=True)
        safe_alt = html.escape(title[:200] if title else "Новина", quote=True)
        image_block = f"""
          <div class="news-card__image">
            <img src="{safe_src}" alt="{safe_alt}" loading="lazy" />
          </div>"""

    details_block = ""
    if body_html:
        details_block = f"""
            <details class="news-card__details" style="margin-top:auto;">
              <summary class="news-card__link" data-i18n="news.readMore">Детальніше</summary>
              <div class="news-card__full" style="margin-top:1rem;font-size:0.9rem;line-height:1.7;color:rgba(38,26,34,0.85);" data-i18n="{keys['body']}">{body_html}</div>
            </details>"""

    article = f"""        <article class="news-card">{image_block}
          <div class="news-card__body">
            <div class="news-card__date" data-i18n="{keys['date']}">{html.escape(date_display)}</div>
            <h3 class="news-card__title" data-i18n="{keys['title']}">{html.escape(title)}</h3>
            <p class="news-card__excerpt" data-i18n="{keys['excerpt']}">{html.escape(excerpt)}</p>{details_block}
          </div>
        </article>
"""
    return article


def inject_article_into_index(index_html: str, article_html: str) -> str:
    needle = '<div class="news__list reveal" id="newsList">'
    pos = index_html.find(needle)
    if pos == -1:
        raise ValueError("Could not find #newsList container in index.html")
    insert_at = pos + len(needle)
    return index_html[:insert_at] + "\n" + article_html + index_html[insert_at:]


def translation_keys_block(
    card_id: int,
    date_display: str,
    title: str,
    excerpt: str,
    body_html: str,
) -> str:
    """Lines to insert before 'news.readMore' in each locale block."""
    b = js_single_quoted_string(body_html)
    d = js_single_quoted_string(date_display)
    t = js_single_quoted_string(title)
    e = js_single_quoted_string(excerpt)
    return (
        f"    'news.card{card_id}Date': '{d}',\n"
        f"    'news.card{card_id}Title': '{t}',\n"
        f"    'news.card{card_id}Excerpt': '{e}',\n"
        f"    'news.card{card_id}Body': '{b}',\n"
    )


def inject_translation_blocks(translations_js: str, blocks: dict[str, str]) -> str:
    """Insert per-language translation blocks before each ``'news.readMore':`` line.

    *blocks* maps a language code (``'uk'``, ``'en'``, ``'de'``, ``'fr'``) to the
    text block to insert.  Falls back to the ``'uk'`` block when a language key
    is missing from *blocks*.
    """
    lines = translations_js.splitlines(keepends=True)
    out: list[str] = []
    current_lang = "uk"
    lang_re = re.compile(r"^\s*(uk|en|de|fr)\s*:\s*\{")

    for line in lines:
        m = lang_re.match(line)
        if m:
            current_lang = m.group(1)

        stripped = line.lstrip()
        if stripped.startswith("'news.readMore':"):
            block = blocks.get(current_lang) or blocks.get("uk", "")
            if block:
                out.append(block)
        out.append(line)
    return "".join(out)


def bust_translations_cache(index_html: str) -> str:
    """Update ``translations.js`` script tag with a fresh cache-busting query string."""
    import time
    version = str(int(time.time()))
    return re.sub(
        r'src="translations\.js(\?v=\d+)?"',
        f'src="translations.js?v={version}"',
        index_html,
    )


def sanitize_image_filename(original: Path, index: int, stamp: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", original.stem).strip("-").lower() or "photo"
    ext = original.suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"
    return f"{stamp}-{index}-{stem}{ext}"
