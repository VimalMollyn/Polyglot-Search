import asyncio
import json
import os
import re
from urllib.parse import urlparse, urlunparse

import httpx
from dotenv import load_dotenv
from fasthtml.common import *

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

LANGUAGES = {
    "en": {"name": "English",  "flag": "🇺🇸", "gl": "us", "hl": "en", "google_domain": "google.com",    "color": "#1a73e8"},
    "ja": {"name": "Japanese", "flag": "🇯🇵", "gl": "jp", "hl": "ja", "google_domain": "google.co.jp",  "color": "#e63946"},
    "de": {"name": "German",   "flag": "🇩🇪", "gl": "de", "hl": "de", "google_domain": "google.de",     "color": "#2d2d2d"},
    "fr": {"name": "French",   "flag": "🇫🇷", "gl": "fr", "hl": "fr", "google_domain": "google.fr",     "color": "#0055a4"},
    "zh": {"name": "Chinese",  "flag": "🇨🇳", "gl": "cn", "hl": "zh-cn", "google_domain": "google.com.hk", "color": "#de2910"},
    "ko": {"name": "Korean",   "flag": "🇰🇷", "gl": "kr", "hl": "ko", "google_domain": "google.co.kr",  "color": "#003478"},
}

LANG_ORDER = ["en", "ja", "de", "fr", "zh", "ko"]

# ─── Translation helpers ──────────────────────────────────────────────────────

async def translate_query_batch(client: httpx.AsyncClient, query: str) -> dict[str, str]:
    """Translate English query into ja, de, fr, zh, ko in one Gemini call."""
    prompt = (
        f'Translate this English text into Japanese, German, French, Simplified Chinese, and Korean.\n'
        f'Return ONLY a valid JSON object with exactly these keys: "ja", "de", "fr", "zh", "ko".\n'
        f'No markdown, no explanation, just the JSON.\n'
        f'Text: "{query}"'
    )
    try:
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={GEMINI_API_KEY}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=20,
        )
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(raw)
    except Exception as e:
        print(f"[translate_query_batch] error: {e}")
        return {"ja": query, "de": query, "fr": query, "zh": query, "ko": query}


async def translate_results_to_english(client: httpx.AsyncClient, results: list[dict]) -> list[dict]:
    """
    Batch-translate all non-English titles and snippets back to English.
    Sends one Gemini call with all texts indexed, returns updated results.
    """
    non_en = [(i, r) for i, r in enumerate(results) if r.get("lang_code") != "en"]
    if not non_en:
        return results

    # Build a flat map: index -> {title, snippet}
    items = {}
    for i, r in non_en:
        items[str(i)] = {"title": r["title"], "snippet": r.get("snippet", "")}

    prompt = (
        "Translate the following JSON values to English. "
        "Keep the same JSON structure and keys. Return ONLY valid JSON, no markdown.\n"
        f"{json.dumps(items, ensure_ascii=False)}"
    )
    try:
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={GEMINI_API_KEY}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=30,
        )
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        translated = json.loads(raw)

        out = list(results)
        for i, orig in non_en:
            key = str(i)
            if key in translated:
                out[i] = {
                    **orig,
                    "title_en": translated[key].get("title", orig["title"]),
                    "snippet_en": translated[key].get("snippet", orig.get("snippet", "")),
                    "title_original": orig["title"],
                }
        return out
    except Exception as e:
        print(f"[translate_results_to_english] error: {e}")
        # Fallback: show original text
        out = list(results)
        for i, orig in non_en:
            out[i] = {**orig, "title_en": orig["title"], "snippet_en": orig.get("snippet", ""), "title_original": orig["title"]}
        return out


# ─── Search ───────────────────────────────────────────────────────────────────

async def search_language(client: httpx.AsyncClient, query: str, lang_code: str) -> list[dict]:
    lang = LANGUAGES[lang_code]
    try:
        r = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={
                "q": query,
                "gl": lang["gl"],
                "hl": lang["hl"],
                "google_domain": lang["google_domain"],
                "num": 5,
            },
            timeout=15,
        )
        r.raise_for_status()
        organic = r.json().get("organic", [])
        return [
            {
                "title": item.get("title", ""),
                "title_en": item.get("title", "") if lang_code == "en" else None,
                "title_original": item.get("title", "") if lang_code != "en" else None,
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "snippet_en": item.get("snippet", "") if lang_code == "en" else None,
                "lang_code": lang_code,
                "domain": item.get("link", "").split("/")[2] if item.get("link") else "",
            }
            for item in organic
        ]
    except Exception as e:
        print(f"[search_language:{lang_code}] error: {e}")
        return []


# ─── Aggregation ──────────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """Normalize a URL for dedup: strip trailing slash, fragment, and sort query params."""
    try:
        p = urlparse(url)
        # Strip www. prefix, trailing slash from path, fragment
        host = p.hostname or ""
        if host.startswith("www."):
            host = host[4:]
        path = p.path.rstrip("/") or "/"
        return f"{host}{path}"
    except Exception:
        return url


async def search_all(query: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        # Step 1: Translate query into all non-English languages (one call)
        translations = await translate_query_batch(client, query)
        queries = {
            "en": query,
            "ja": translations.get("ja", query),
            "de": translations.get("de", query),
            "fr": translations.get("fr", query),
            "zh": translations.get("zh", query),
            "ko": translations.get("ko", query),
        }
        print(f"[search_all] translated queries: {queries}")

        # Step 2: Fire all 6 searches in parallel
        search_tasks = [search_language(client, queries[lc], lc) for lc in LANG_ORDER]
        all_results_by_lang = await asyncio.gather(*search_tasks)

        # Step 3: Flatten into a single list (preserving language info)
        flat = [item for lang_results in all_results_by_lang for item in lang_results]

        # Step 4: Batch-translate non-English titles/snippets back to English
        flat = await translate_results_to_english(client, flat)

        # Step 5: Deduplicate by URL and rank by cross-language frequency
        # Group results by normalized URL
        seen: dict[str, dict] = {}  # norm_url -> merged result
        for item in flat:
            norm = _normalize_url(item["link"])
            if norm not in seen:
                # First time seeing this URL — use this result as the base
                seen[norm] = {
                    **item,
                    "lang_codes": [item["lang_code"]],
                    "lang_count": 1,
                }
            else:
                # Duplicate URL from another language — merge flags
                existing = seen[norm]
                if item["lang_code"] not in existing["lang_codes"]:
                    existing["lang_codes"].append(item["lang_code"])
                    existing["lang_count"] += 1
                # Prefer English version for display if available
                if item["lang_code"] == "en":
                    existing["title_en"] = item.get("title_en") or item["title"]
                    existing["snippet_en"] = item.get("snippet_en") or item.get("snippet", "")
                    existing["link"] = item["link"]
                    existing["domain"] = item["domain"]

        # Sort: more languages = higher rank, then preserve original order
        deduped = list(seen.values())
        deduped.sort(key=lambda x: -x["lang_count"])

        return deduped


# ─── UI Components ────────────────────────────────────────────────────────────

def language_badge(lang_code: str):
    lang = LANGUAGES[lang_code]
    return Span(
        f"{lang['flag']} {lang['name']}",
        style=(
            f"display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600;"
            f"background:{lang['color']}22; color:{lang['color']}; border:1px solid {lang['color']}44;"
            f"margin-bottom:6px; letter-spacing:0.3px;"
        ),
    )


def result_card(item: dict):
    title_display = item.get("title_en") or item["title"]
    snippet_display = item.get("snippet_en") or item.get("snippet", "")
    original_title = item.get("title_original")
    lang_codes = item.get("lang_codes", [item["lang_code"]])

    # Show multiple badges if found in multiple languages
    badges = Div(
        *[language_badge(lc) for lc in lang_codes],
        style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px;",
    )

    # "Found in N languages" indicator for multi-language results
    multi_lang_note = (
        Span(
            f"Found in {len(lang_codes)} languages",
            style="font-size:10px; color:#5f6368; margin-left:6px; vertical-align:middle;",
        )
        if len(lang_codes) > 1
        else ""
    )

    original_el = (
        P(
            f"Original: {original_title}",
            style="color:#888; font-size:12px; margin:2px 0 4px 0; font-style:italic; word-break:break-word;",
        )
        if original_title and item.get("lang_code") != "en"
        else ""
    )

    return Article(
        Div(badges, multi_lang_note, style="display:flex; align-items:center; flex-wrap:wrap;"),
        H3(
            A(
                title_display,
                href=item["link"],
                target="_blank",
                rel="noopener noreferrer",
                style="color:#1a0dab; text-decoration:none; font-size:16px; line-height:1.3;",
            ),
            style="margin:0 0 2px 0; font-weight:500;",
        ),
        original_el,
        P(
            item["domain"],
            style="color:#188038; font-size:12px; margin:0 0 4px 0;",
        ),
        P(
            snippet_display,
            style="color:#4d5156; font-size:13px; margin:0; line-height:1.5;",
        ),
        style=(
            "background:#fff; border:1px solid #e0e0e0; border-radius:8px;"
            "padding:14px 16px; margin-bottom:10px;"
            "box-shadow:0 1px 3px rgba(0,0,0,0.06);"
            "transition:box-shadow 0.15s;"
        ),
    )


def search_page(query: str = ""):
    lang_flags = " ".join(f"{LANGUAGES[lc]['flag']} {LANGUAGES[lc]['name']}" for lc in LANG_ORDER)
    return Html(
        Head(
            Meta(charset="utf-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            Title("Polyglot Search — Search the World's Internet"),
            Script(src="https://unpkg.com/htmx.org@2.0.3"),
            Style("""
                * { box-sizing: border-box; }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: #f8f9fa;
                    margin: 0;
                    padding: 0;
                    color: #202124;
                }
                .hero {
                    background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
                    padding: 48px 20px 40px;
                    text-align: center;
                    color: white;
                }
                .hero h1 {
                    font-size: 32px;
                    font-weight: 700;
                    margin: 0 0 8px 0;
                    letter-spacing: -0.5px;
                }
                .hero p {
                    font-size: 15px;
                    opacity: 0.85;
                    margin: 0 0 24px 0;
                }
                .search-form {
                    display: flex;
                    max-width: 640px;
                    margin: 0 auto;
                    gap: 8px;
                }
                .search-input {
                    flex: 1;
                    padding: 14px 18px;
                    font-size: 16px;
                    border: none;
                    border-radius: 28px;
                    outline: none;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                }
                .search-btn {
                    padding: 14px 24px;
                    font-size: 15px;
                    font-weight: 600;
                    background: #fbbc04;
                    color: #202124;
                    border: none;
                    border-radius: 28px;
                    cursor: pointer;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                    white-space: nowrap;
                }
                .search-btn:hover { background: #f9a825; }
                .lang-strip {
                    margin-top: 16px;
                    font-size: 20px;
                    opacity: 0.9;
                    letter-spacing: 4px;
                }
                .lang-strip-labels {
                    font-size: 11px;
                    opacity: 0.7;
                    margin-top: 4px;
                    letter-spacing: 0;
                }
                .results-container {
                    max-width: 700px;
                    margin: 28px auto;
                    padding: 0 16px;
                }
                .spinner {
                    display: none;
                    text-align: center;
                    padding: 40px 0;
                    color: #5f6368;
                }
                .spinner.htmx-request { display: block; }
                .spinner-ring {
                    display: inline-block;
                    width: 40px; height: 40px;
                    border: 3px solid #e0e0e0;
                    border-top-color: #1a73e8;
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                }
                @keyframes spin { to { transform: rotate(360deg); } }
                .spinner-text { margin-top: 12px; font-size: 14px; }
                .results-header {
                    font-size: 13px;
                    color: #5f6368;
                    margin-bottom: 14px;
                    padding-bottom: 10px;
                    border-bottom: 1px solid #e0e0e0;
                }
                .empty-state {
                    text-align: center;
                    padding: 60px 20px;
                    color: #5f6368;
                }
                .empty-state .big-flags { font-size: 40px; margin-bottom: 16px; }
                .empty-state h2 { font-size: 20px; font-weight: 500; margin: 0 0 8px 0; color: #202124; }
                .empty-state p { font-size: 14px; margin: 0; }
                article:hover { box-shadow: 0 3px 10px rgba(0,0,0,0.12) !important; }
            """),
        ),
        Body(
            Div(
                H1("🌐 Polyglot Search"),
                P("Search once. Get results from 6 different Googles."),
                Form(
                    Input(
                        type="text",
                        name="query",
                        value=query,
                        placeholder="Search the world's internet...",
                        cls="search-input",
                        autofocus=True,
                        required=True,
                    ),
                    Button("Search", type="submit", cls="search-btn"),
                    hx_post="/search",
                    hx_target="#results",
                    hx_swap="innerHTML",
                    hx_indicator="#spinner",
                    cls="search-form",
                ),
                Div(
                    " ".join(LANGUAGES[lc]["flag"] for lc in LANG_ORDER),
                    cls="lang-strip",
                ),
                Div(lang_flags, cls="lang-strip-labels"),
                cls="hero",
            ),
            Div(
                Div(
                    Div(cls="spinner-ring"),
                    P(
                        "Searching English, Japanese, German, French, Chinese, Korean Google...",
                        cls="spinner-text",
                    ),
                    id="spinner",
                    cls="spinner",
                ),
                Div(
                    Div("🌐🔍", cls="big-flags"),
                    H2("Search the world's internet"),
                    P("Enter a query above to search Google in 6 languages simultaneously."),
                    cls="empty-state",
                )
                if not query
                else "",
                id="results",
                cls="results-container",
            ),
        ),
    )


def results_fragment(results: list[dict], query: str):
    if not results:
        return Div(
            P("No results found. Try a different query.", style="text-align:center; color:#5f6368; padding:40px 0;"),
        )

    # Count how many results each language contributed to (including shared ones)
    lang_counts = {}
    for r in results:
        for lc in r.get("lang_codes", [r["lang_code"]]):
            lang_counts[lc] = lang_counts.get(lc, 0) + 1

    multi_count = sum(1 for r in results if r.get("lang_count", 1) > 1)
    summary = ", ".join(
        f"{LANGUAGES[lc]['flag']} {cnt}" for lc, cnt in lang_counts.items()
    )
    if multi_count:
        summary += f" ({multi_count} found across multiple languages)"

    return Div(
        P(f'About {len(results)} results for "{query}" \u2014 {summary}', cls="results-header"),
        *[result_card(item) for item in results],
    )


# ─── App & Routes ─────────────────────────────────────────────────────────────

app, rt = fast_app()


@rt("/")
def get():
    return search_page()


@rt("/search")
async def post(query: str):
    if not query.strip():
        return Div(P("Please enter a search query.", style="text-align:center; color:#5f6368; padding:40px 0;"))
    if not SERPER_API_KEY:
        return Div(P("⚠️ SERPER_API_KEY not set in .env", style="color:red; text-align:center; padding:40px 0;"))
    if not GEMINI_API_KEY:
        return Div(P("⚠️ GEMINI_API_KEY not set in .env", style="color:red; text-align:center; padding:40px 0;"))

    results = await search_all(query.strip())
    return results_fragment(results, query.strip())


serve(port=5001)
