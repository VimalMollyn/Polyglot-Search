import asyncio
import json
import os

import httpx
from dotenv import load_dotenv
from fasthtml.common import *

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

LANGUAGES = {
    "en": {"name": "English",  "flag": "🇺🇸", "gl": "us", "hl": "en",    "google_domain": "google.com",    "color": "#1a73e8"},
    "ja": {"name": "Japanese", "flag": "🇯🇵", "gl": "jp", "hl": "ja",    "google_domain": "google.co.jp",  "color": "#e63946"},
    "de": {"name": "German",   "flag": "🇩🇪", "gl": "de", "hl": "de",    "google_domain": "google.de",     "color": "#2d2d2d"},
    "fr": {"name": "French",   "flag": "🇫🇷", "gl": "fr", "hl": "fr",    "google_domain": "google.fr",     "color": "#0055a4"},
    "zh": {"name": "Chinese",  "flag": "🇨🇳", "gl": "cn", "hl": "zh-cn", "google_domain": "google.com.hk", "color": "#de2910"},
    "ko": {"name": "Korean",   "flag": "🇰🇷", "gl": "kr", "hl": "ko",    "google_domain": "google.co.kr",  "color": "#003478"},
}

LANG_ORDER = ["en", "ja", "de", "fr", "zh", "ko"]

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={GEMINI_API_KEY}"

# ─── Gemini helpers ───────────────────────────────────────────────────────────

async def _gemini_json(client: httpx.AsyncClient, prompt: str, timeout: int = 20) -> dict | list | None:
    """Send a prompt to Gemini and parse JSON response."""
    try:
        r = await client.post(
            GEMINI_URL,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=timeout,
        )
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(raw)
    except Exception as e:
        print(f"[gemini] error: {e}")
        return None


async def suggest_languages(client: httpx.AsyncClient, query: str) -> list[str]:
    """Ask Gemini which languages would yield the most relevant results for a query."""
    valid = ", ".join(f'{lc} ({LANGUAGES[lc]["name"]})' for lc in LANG_ORDER)
    prompt = (
        f"Given this search query, which of these languages would have the most relevant or unique search results?\n"
        f"Available languages: {valid}\n"
        f"Always include \"en\" (English). Pick 2-4 languages total that are most relevant.\n"
        f"Return ONLY a JSON array of language codes, e.g. [\"en\", \"ja\", \"ko\"]\n"
        f"Query: \"{query}\""
    )
    result = await _gemini_json(client, prompt, timeout=10)
    if isinstance(result, list):
        # Validate codes
        codes = [lc for lc in result if lc in LANGUAGES]
        if "en" not in codes:
            codes.insert(0, "en")
        if codes:
            return codes
    return ["en"]


async def translate_query_batch(client: httpx.AsyncClient, query: str, lang_codes: list[str]) -> dict[str, str]:
    """Translate English query into requested non-English languages in one Gemini call."""
    non_en = [lc for lc in lang_codes if lc != "en"]
    if not non_en:
        return {}

    lang_names = {lc: LANGUAGES[lc]["name"] for lc in non_en}
    prompt = (
        f"Translate this English text into these languages: {json.dumps(lang_names)}.\n"
        f'Return ONLY a valid JSON object with exactly these keys: {json.dumps(non_en)}.\n'
        f"No markdown, no explanation, just the JSON.\n"
        f'Text: "{query}"'
    )
    result = await _gemini_json(client, prompt, timeout=20)
    if isinstance(result, dict):
        return result
    return {lc: query for lc in non_en}


async def translate_results_to_english(client: httpx.AsyncClient, results: list[dict]) -> list[dict]:
    """Batch-translate all non-English titles and snippets back to English."""
    non_en = [(i, r) for i, r in enumerate(results) if r.get("lang_code") != "en"]
    if not non_en:
        return results

    items = {}
    for i, r in non_en:
        items[str(i)] = {"title": r["title"], "snippet": r.get("snippet", "")}

    prompt = (
        "Translate the following JSON values to English. "
        "Keep the same JSON structure and keys. Return ONLY valid JSON, no markdown.\n"
        f"{json.dumps(items, ensure_ascii=False)}"
    )
    translated = await _gemini_json(client, prompt, timeout=30)

    out = list(results)
    if isinstance(translated, dict):
        for i, orig in non_en:
            key = str(i)
            if key in translated:
                out[i] = {
                    **orig,
                    "title_en": translated[key].get("title", orig["title"]),
                    "snippet_en": translated[key].get("snippet", orig.get("snippet", "")),
                    "title_original": orig["title"],
                }
    else:
        # Fallback: show original text
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

async def search_all(query: str, lang_codes: list[str]) -> list[dict]:
    async with httpx.AsyncClient() as client:
        # Step 1: Translate query into non-English selected languages
        translations = await translate_query_batch(client, query, lang_codes)
        queries = {"en": query}
        for lc in lang_codes:
            if lc != "en":
                queries[lc] = translations.get(lc, query)
        print(f"[search_all] translated queries: {queries}")

        # Step 2: Fire all searches in parallel
        search_tasks = [search_language(client, queries[lc], lc) for lc in lang_codes]
        all_results_by_lang = await asyncio.gather(*search_tasks)

        # Step 3: Flatten
        flat = [item for lang_results in all_results_by_lang for item in lang_results]

        # Step 4: Batch-translate non-English titles/snippets back to English
        flat = await translate_results_to_english(client, flat)

        # Step 5: Interleave round-robin across languages
        per_lang = {lc: [] for lc in lang_codes}
        for item in flat:
            per_lang.setdefault(item["lang_code"], []).append(item)

        interleaved = []
        max_len = max((len(v) for v in per_lang.values()), default=0)
        for i in range(max_len):
            for lc in lang_codes:
                if lc in per_lang and i < len(per_lang[lc]):
                    interleaved.append(per_lang[lc][i])

        # Step 6: Deduplicate by URL
        seen_urls = set()
        deduped = []
        for item in interleaved:
            url = item["link"].rstrip("/").lower()
            if url not in seen_urls:
                seen_urls.add(url)
                deduped.append(item)

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

    original_el = (
        P(
            f"Original: {original_title}",
            style="color:#888; font-size:12px; margin:2px 0 4px 0; font-style:italic; word-break:break-word;",
        )
        if original_title
        else ""
    )

    return Article(
        language_badge(item["lang_code"]),
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
        P(item["domain"], style="color:#188038; font-size:12px; margin:0 0 4px 0;"),
        P(snippet_display, style="color:#4d5156; font-size:13px; margin:0; line-height:1.5;"),
        style=(
            "background:#fff; border:1px solid #e0e0e0; border-radius:8px;"
            "padding:14px 16px; margin-bottom:10px;"
            "box-shadow:0 1px 3px rgba(0,0,0,0.06);"
            "transition:box-shadow 0.15s;"
        ),
    )


def breathing_indicator(lang_codes: list[str]):
    """Return a breathing/pulsing indicator showing which languages are being searched."""
    parts = ", ".join(f"{LANGUAGES[lc]['flag']} {LANGUAGES[lc]['name']}" for lc in lang_codes)
    return Div(
        Div(cls="spinner-ring"),
        P(f"Searching in {parts}...", cls="breathing-text"),
        style="text-align:center; padding:50px 0;",
    )


def results_fragment(results: list[dict], query: str):
    if not results:
        return Div(
            P("No results found. Try a different query.", style="text-align:center; color:#5f6368; padding:40px 0;"),
        )

    lang_counts = {}
    for r in results:
        lc = r["lang_code"]
        lang_counts[lc] = lang_counts.get(lc, 0) + 1

    summary = ", ".join(
        f"{LANGUAGES[lc]['flag']} {cnt}" for lc, cnt in lang_counts.items()
    )

    return Div(
        P(f'About {len(results)} results for "{query}" \u2014 {summary}', cls="results-header"),
        *[result_card(item) for item in results],
    )


def search_page():
    return Html(
        Head(
            Meta(charset="utf-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            Title("Polyglot Search \u2014 Search the World's Internet"),
            Link(rel="preconnect", href="https://fonts.googleapis.com"),
            Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=True),
            Link(rel="stylesheet", href="https://fonts.googleapis.com/css2?family=Poppins:wght@600&display=swap"),
            Script(src="https://unpkg.com/htmx.org@2.0.3"),
            Style("""
                * { box-sizing: border-box; }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: #f8f9fa; margin: 0; padding: 0; color: #202124;
                }
                .hero {
                    background: #f8f9fa;
                    padding: 20px 20px 32px; text-align: center; color: #202124;
                    min-height: 60vh; display: flex; flex-direction: column;
                    align-items: center; justify-content: center;
                    transition: all 0.3s ease;
                }
                .hero.compact {
                    min-height: auto; padding: 16px 20px 12px;
                    flex-direction: row; flex-wrap: wrap; gap: 12px;
                    justify-content: flex-start; align-items: center;
                    border-bottom: 1px solid #e0e0e0;
                }
                .hero h1 { font-family: 'Poppins', sans-serif; font-size: 64px; font-weight: 600; margin: 0 0 6px 0; letter-spacing: -1px; transition: font-size 0.3s ease; }
                .hero.compact h1 { font-size: 28px; margin: 0; cursor: pointer; }
                .hero.compact .search-row { max-width: 480px; flex: 1; }
                .hero.compact .lang-selector { display: none; }
                .lang-toggle-btn {
                    display: none; align-items: center; gap: 4px;
                    padding: 6px 12px; border-radius: 16px; font-size: 12px; font-weight: 500;
                    background: #fff; color: #5f6368; border: 1px solid #dadce0;
                    cursor: pointer; transition: all 0.15s; white-space: nowrap;
                }
                .lang-toggle-btn:hover { background: #e8f0fe; color: #1a73e8; border-color: #1a73e8; }
                .hero.compact .lang-toggle-btn { display: inline-flex; }
                .lang-dropdown {
                    display: none; position: absolute; top: 100%; right: 0; margin-top: 6px;
                    background: #fff; border: 1px solid #dadce0; border-radius: 12px;
                    padding: 10px; box-shadow: 0 4px 16px rgba(0,0,0,0.12);
                    z-index: 100; gap: 6px; flex-wrap: wrap; min-width: 280px;
                }
                .lang-dropdown.open { display: flex; }

                /* Search bar — Google-style pill */
                .search-row {
                    display: flex; align-items: center; max-width: 640px; margin: 0 auto;
                    background: #fff; border: 1px solid #dfe1e5; border-radius: 24px;
                    padding: 6px 6px 6px 20px; gap: 8px;
                    box-shadow: none; transition: box-shadow 0.2s, border-color 0.2s;
                }
                .search-row:hover { box-shadow: 0 1px 6px rgba(32,33,36,0.18); border-color: rgba(223,225,229,0); }
                .search-row:focus-within { box-shadow: 0 1px 6px rgba(32,33,36,0.18); border-color: rgba(223,225,229,0); }
                .search-input {
                    flex: 1; padding: 8px 0; font-size: 16px;
                    border: none; outline: none; background: transparent; color: #202124;
                }
                .search-input::placeholder { color: #9aa0a6; }
                .search-input:-webkit-autofill,
                .search-input:-webkit-autofill:hover,
                .search-input:-webkit-autofill:focus {
                    -webkit-box-shadow: 0 0 0 1000px white inset !important;
                    -webkit-text-fill-color: #202124 !important;
                    transition: background-color 5000s ease-in-out 0s;
                }
                .search-btn {
                    padding: 10px 20px; font-size: 14px; font-weight: 600;
                    background: #f8f9fa; color: #3c4043; border: 1px solid #f8f9fa; border-radius: 20px;
                    cursor: pointer; white-space: nowrap; transition: all 0.15s;
                }
                .search-btn:hover { background: #e8e8e9; border-color: #dadce0; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }

                /* Language toggles */
                .lang-selector { max-width: 640px; margin: 14px auto 0; display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; align-items: center; }
                .lang-toggle {
                    display: inline-flex; align-items: center; gap: 4px;
                    padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 500;
                    background: #fff; color: #5f6368;
                    border: 1.5px dashed #dadce0; cursor: pointer;
                    transition: all 0.15s; user-select: none;
                }
                .lang-toggle:hover {
                    background: #e8f0fe; color: #1a73e8;
                    border-style: solid; border-color: #1a73e8; transform: scale(1.05);
                }
                .lang-toggle:active { transform: scale(0.97); }
                .lang-toggle.selected {
                    background: #1a73e8; color: white;
                    border-color: #1a73e8; border-style: solid; font-weight: 600;
                    box-shadow: 0 1px 4px rgba(26,115,232,0.3);
                }
                .lang-toggle input { display: none; }

                /* Max polyglot button — sits inside the search pill */
                .polyglot-btn {
                    display: inline-flex; align-items: center; gap: 4px;
                    padding: 10px 16px; border-radius: 20px; font-size: 13px; font-weight: 600;
                    background: #f3e8ff; color: #7c3aed;
                    border: 1px solid #e9d5ff; cursor: pointer;
                    transition: all 0.15s; user-select: none; white-space: nowrap;
                }
                .polyglot-btn:hover { background: #ede9fe; border-color: #c4b5fd; }
                .polyglot-btn.active {
                    background: #7c3aed; color: white; border-color: #7c3aed;
                    box-shadow: 0 2px 10px rgba(167,79,237,0.4);
                }

                /* Results area */
                .results-container { max-width: 700px; margin: 28px auto; padding: 0 16px; }
                .results-header {
                    font-size: 13px; color: #5f6368; margin-bottom: 14px;
                    padding-bottom: 10px; border-bottom: 1px solid #e0e0e0;
                }

                /* Breathing animation for search indicator */
                .spinner-ring {
                    display: inline-block; width: 40px; height: 40px;
                    border: 3px solid #e0e0e0; border-top-color: #1a73e8;
                    border-radius: 50%; animation: spin 0.8s linear infinite;
                }
                @keyframes spin { to { transform: rotate(360deg); } }
                @keyframes breathe {
                    0%, 100% { opacity: 0.4; }
                    50% { opacity: 1; }
                }
                .breathing-text {
                    margin-top: 16px; font-size: 15px; color: #5f6368;
                    animation: breathe 2s ease-in-out infinite;
                }

                /* Empty state */
                .empty-state { text-align: center; padding: 60px 20px; color: #5f6368; }
                .empty-state .big-icon { font-size: 40px; margin-bottom: 16px; }
                .empty-state h2 { font-size: 20px; font-weight: 500; margin: 0 0 8px 0; color: #202124; }
                .empty-state p { font-size: 14px; margin: 0; }
                article:hover { box-shadow: 0 3px 10px rgba(0,0,0,0.12) !important; }
            """),
            Script("""
                function toggleLang(el) {
                    var pg = document.getElementById('polyglot-btn');
                    if (pg && pg.classList.contains('active')) {
                        pg.classList.remove('active');
                    }
                    el.classList.toggle('selected');
                    // Sync: keep main and dropdown toggles in sync by data-lang
                    var lang = el.dataset.lang;
                    var isSelected = el.classList.contains('selected');
                    document.querySelectorAll('.lang-toggle[data-lang="'+lang+'"]').forEach(function(other) {
                        if (isSelected) other.classList.add('selected');
                        else other.classList.remove('selected');
                    });
                }
                function togglePolyglot(el) {
                    var isActive = el.classList.toggle('active');
                    document.querySelectorAll('.lang-toggle').forEach(function(lt) {
                        if (isActive) lt.classList.add('selected');
                        else lt.classList.remove('selected');
                    });
                }
                function toggleLangDropdown(e) {
                    e.stopPropagation();
                    document.getElementById('lang-dropdown').classList.toggle('open');
                }
                // Close dropdown when clicking outside
                document.addEventListener('click', function(e) {
                    var dd = document.getElementById('lang-dropdown');
                    if (dd && !e.target.closest('.lang-toggle-btn') && !e.target.closest('.lang-dropdown')) {
                        dd.classList.remove('open');
                    }
                });
                function gatherFormData() {
                    // Use main toggles (or dropdown — they're synced) to collect selected
                    var selected = new Set();
                    document.querySelectorAll('.lang-toggle.selected').forEach(function(el) {
                        selected.add(el.dataset.lang);
                    });
                    document.getElementById('selected-langs').value = Array.from(selected).join(',');
                    var pg = document.getElementById('polyglot-btn');
                    document.getElementById('polyglot-flag').value = pg && pg.classList.contains('active') ? '1' : '0';
                    document.querySelector('.hero').classList.add('compact');
                    // Close dropdown if open
                    var dd = document.getElementById('lang-dropdown');
                    if (dd) dd.classList.remove('open');
                }
            """),
        ),
        Body(
            Div(
                H1(
                    Span("P", style="color:#4285F4;"),
                    Span("o", style="color:#EA4335;"),
                    Span("l", style="color:#FBBC04;"),
                    Span("y", style="color:#4285F4;"),
                    Span("g", style="color:#34A853;"),
                    Span("l", style="color:#EA4335;"),
                    Span("o", style="color:#FBBC04;"),
                    Span("t", style="color:#4285F4;"),
                ),
                Form(
                    Div(
                        Input(
                            type="text", name="query",
                            placeholder="",
                            cls="search-input", autofocus=True, required=True,
                        ),
                        Button("Search", type="submit", cls="search-btn"),
                        Span(
                            "Max Polyglot",
                            id="polyglot-btn", cls="polyglot-btn",
                            onclick="togglePolyglot(this)",
                        ),
                        # Compact mode: languages dropdown trigger
                        Div(
                            Span(
                                "\u2699 Languages",
                                cls="lang-toggle-btn",
                                onclick="toggleLangDropdown(event)",
                            ),
                            Div(
                                *[
                                    Span(
                                        f"{LANGUAGES[lc]['flag']} {LANGUAGES[lc]['name']}",
                                        data_lang=lc, cls="lang-toggle lang-toggle-dd",
                                        onclick="toggleLang(this)",
                                    )
                                    for lc in LANG_ORDER
                                ],
                                id="lang-dropdown", cls="lang-dropdown",
                            ),
                            style="position:relative;",
                        ),
                        cls="search-row",
                    ),
                    # Language selector strip (visible on homepage, hidden in compact)
                    Div(
                        *[
                            Span(
                                f"{LANGUAGES[lc]['flag']} {LANGUAGES[lc]['name']}",
                                data_lang=lc, cls="lang-toggle lang-toggle-main",
                                onclick="toggleLang(this)",
                            )
                            for lc in LANG_ORDER
                        ],
                        cls="lang-selector",
                    ),
                    # Hidden fields to carry state into the POST
                    Input(type="hidden", name="langs", id="selected-langs", value=""),
                    Input(type="hidden", name="polyglot", id="polyglot-flag", value="0"),
                    hx_post="/search",
                    hx_target="#results",
                    hx_swap="innerHTML",
                    # Gather toggle state right before HTMX sends the request
                    **{"hx-on::before-request": "gatherFormData()"},
                ),
                cls="hero",
            ),
            Div(
                id="results",
                cls="results-container",
            ),
        ),
    )


# ─── App & Routes ─────────────────────────────────────────────────────────────

app, rt = fast_app()


@rt("/")
def get():
    return search_page()


@rt("/search")
async def post(query: str, langs: str = "", polyglot: str = "0"):
    """Phase 1: Validate, determine languages or kick off suggestion."""
    query = query.strip()
    if not query:
        return Div(P("Please enter a search query.", style="text-align:center; color:#5f6368; padding:40px 0;"))
    if not SERPER_API_KEY:
        return Div(P("\u26a0\ufe0f SERPER_API_KEY not set in .env", style="color:red; text-align:center; padding:40px 0;"))
    if not GEMINI_API_KEY:
        return Div(P("\u26a0\ufe0f GEMINI_API_KEY not set in .env", style="color:red; text-align:center; padding:40px 0;"))

    if polyglot == "1":
        lang_codes = list(LANG_ORDER)
    elif langs:
        lang_codes = [lc for lc in langs.split(",") if lc in LANGUAGES]
        if not lang_codes:
            lang_codes = ["en"]
    else:
        # No selection — show "obtaining languages" then auto-trigger suggestion
        return Div(
            Div(
                Div(cls="spinner-ring"),
                P("Obtaining best languages to search in...", cls="breathing-text"),
                style="text-align:center; padding:50px 0;",
            ),
            Div(
                hx_post="/suggest-and-search",
                hx_vals=json.dumps({"query": query}),
                hx_trigger="load",
                hx_target="#results",
                hx_swap="innerHTML",
            ),
        )

    langs_str = ",".join(lang_codes)
    # Languages known — show breathing search indicator + auto-trigger search
    return Div(
        breathing_indicator(lang_codes),
        Div(
            hx_post="/execute-search",
            hx_vals=json.dumps({"query": query, "langs": langs_str}),
            hx_trigger="load",
            hx_target="#results",
            hx_swap="innerHTML",
        ),
    )


@rt("/suggest-and-search")
async def post(query: str):
    """Phase 1b: Ask Gemini for languages, then show breathing indicator + trigger search."""
    async with httpx.AsyncClient() as client:
        lang_codes = await suggest_languages(client, query)

    langs_str = ",".join(lang_codes)
    return Div(
        breathing_indicator(lang_codes),
        Div(
            hx_post="/execute-search",
            hx_vals=json.dumps({"query": query, "langs": langs_str}),
            hx_trigger="load",
            hx_target="#results",
            hx_swap="innerHTML",
        ),
    )


@rt("/execute-search")
async def post(query: str, langs: str):
    """Phase 2: Actually perform the searches and return results."""
    lang_codes = [lc for lc in langs.split(",") if lc in LANGUAGES]
    if not lang_codes:
        lang_codes = ["en"]

    results = await search_all(query.strip(), lang_codes)
    return results_fragment(results, query.strip())


serve(port=5001)
