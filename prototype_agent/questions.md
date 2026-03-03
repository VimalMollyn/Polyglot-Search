# Design Questions & Decisions

## API & Infrastructure

- **Q:** Do you have a Google Custom Search API key ready, or need mock mode?
  **A:** Can make keys, need setup instructions → switched to Serper.dev (Google CSE no longer supports "search entire web" easily; Serper.dev offers 2,500 free queries one-time)

- **Q:** Which translation approach? (Google Translate API, DeepL, LLM-based)
  **A:** Google Translate API initially considered → switched to Gemini 2.0 Flash via Google AI Studio (user has free credits; batching all 5 translations into one API call is efficient)

- **Q:** Should back-translation (non-English results → English) be done per-result or batched?
  **A:** Batched — all non-English titles + snippets sent in one Gemini call per search completion, minimizing API round-trips

## UI Layout

- **Q:** How to present results from 6 languages without overwhelming the user?
  Options considered:
  1. Tabs per language (hides cross-language serendipity)
  2. Interleaved with language/flag badge (promotes discovery)
  3. Side-by-side columns (hard to read on mobile)
  **A:** Interleaved with language/flag badge per result (round-robin: EN[0], JA[0], DE[0], FR[0], ZH[0], KO[0], EN[1], ...)

- **Q:** What information should each result card show?
  **A:** English-translated title (as clickable link to original URL), original-language title (muted, smaller), translated snippet, domain name, language badge with flag

## Languages

- **Q:** Which languages to support in MVP?
  **A:** English 🇺🇸, Japanese 🇯🇵, German 🇩🇪, French 🇫🇷, Chinese 🇨🇳, Korean 🇰🇷
  Rationale: covers major internet content blocs; Japanese/Chinese/Korean unlock large volumes of non-indexed-in-English content

## Architecture

- **Q:** Should we use FastHTML's built-in JS or HTMX for the search form?
  **A:** HTMX — keeps the page from full reloading, allows progressive loading indicator, fits FastHTML's paradigm

- **Q:** Should we paginate results or show all 30 at once?
  **A:** Show all 30 (5 per language × 6 languages) — prototype scope; pagination can come later

- **Q:** How to handle API errors gracefully (Serper rate limit, Gemini failure)?
  **A:** Return empty results for that language with a silent fallback; show whatever languages succeeded

---

## Change Requests

| # | Date | Request | Change Made |
|---|------|---------|-------------|
| 1 | 2026-02-25 | Use Gemini 3 Flash Preview instead of Gemini 2.0 Flash | Updated model ID in both Gemini API calls in `app.py` from `gemini-2.0-flash` to `gemini-3-flash-preview` |
| 2 | 2026-02-25 | Log all change requests in `questions.md` going forward; update `CLAUDE.md` to enforce this | Added this Change Requests table to `questions.md`; added logging instruction to `CLAUDE.md` |
| 3 | 2026-02-25 | Deduplicate results that point to the same URL across languages (e.g. Apple dev site showing 5 times) | Added Step 6 in `search_all()`: after interleaving, deduplicate by normalized URL, keeping only the first occurrence |
| 4 | 2026-02-25 | Allow selecting specific languages to search in | Added toggleable language badges in the hero; selected languages passed to search via hidden form field; `search_all()` now accepts a `lang_codes` parameter |
| 5 | 2026-02-25 | AI-suggest best languages based on query; show "Searching in X, Y, Z..." breathing animation | Added `suggest_languages()` Gemini call; two-phase HTMX flow: `/search` returns breathing indicator + auto-triggers `/execute-search`; CSS `@keyframes breathe` animation |
| 6 | 2026-02-25 | Add "Max Polyglot" mode that searches all available languages | Added Max Polyglot toggle button; when active, bypasses AI suggestion and sends all 6 languages |
| 7 | 2026-02-25 | Remove the empty state text/icon below the search bar | Removed the "Search the world's internet" empty state div from `search_page()` |
| 8 | 2026-02-25 | Language buttons don't look clickable — make it more obvious | Improved lang-toggle styling: added hover cursor/scale, dashed border, press feedback |
| 9 | 2026-02-25 | Move Max Polyglot next to Search button, make it a different color | Moved polyglot btn into search-row (next to Search); restyled as purple (#a74fed) to distinguish from yellow Search btn |
| 10 | 2026-02-25 | Remove "Select languages or let AI choose..." hint text | Removed hint paragraph from the form |
| 11 | 2026-02-25 | Remove blue background, remove globe emoji from title and Max Polyglot button | Hero bg changed to #f8f9fa (matches body); removed 🌐 from h1 and polyglot btn; updated lang-toggle and polyglot-btn colors for light bg |
| 12 | 2026-02-25 | Make search box look like Google's pill-shaped search bar | Restyled search-row as a single pill container with thin border, hover shadow; input is transparent inside; Search/Polyglot btns sit inside the pill |
| 13 | 2026-02-25 | Move all search elements to the vertical middle of the screen | Hero uses `min-height:60vh` with flexbox centering to push content to screen center |
| 14 | 2026-02-25 | Title should be just "Polyglot" with each letter a different color like Google logo | Replaced H1 with per-letter Spans using Google's color palette: blue, red, yellow, blue, green, red, yellow, blue |
| 15 | 2026-02-25 | Choose a different font for the title | Added Google Fonts Poppins (600 weight); title now uses Poppins at 64px for a clean logo feel |
| 16 | 2026-02-25 | Remove subtitle text below title | Removed "Search once. Get results from multiple Googles." subtitle |
| 17 | 2026-02-25 | Remove placeholder text from search input | Cleared "Search the world's internet..." placeholder |
| 18 | 2026-02-25 | Fix ugly blue autofill highlight on search input when selecting from browser history | Added `-webkit-autofill` CSS overrides to force white background on autofilled input |
| 19 | 2026-02-25 | Hero should move to top-left after search (like Google); remove white gap between hero and results | Added `.hero.compact` CSS class: collapses to top bar with row layout, smaller title, left-aligned; JS adds `compact` class on form submit |
| 20 | 2026-02-25 | Show "Obtaining languages to search in" status when Gemini is suggesting languages | Added 3-phase HTMX flow: `/search` returns instant "Obtaining best languages..." indicator → `/suggest-and-search` calls Gemini → `/execute-search` returns results |
| 21 | 2026-02-25 | Collapse language options in compact mode (behind a dropdown) | In compact mode, `.lang-selector` is hidden; a "\u2699 Languages" button appears in the search row with a dropdown panel; main and dropdown toggles stay synced |
| 22 | 2026-02-25 | Fix search bar overflow in compact mode; fix dropdown language toggles not fitting properly | Added `min-width:0` on input, `flex-shrink:0` on search-row, compact button sizes; fixed dropdown width to 240px with solid borders and smaller font for dropdown toggles |
| 23 | 2026-02-25 | Gemini reranking: reorder results by relevance + uniqueness (non-English content prioritized) | Added `rerank_results()` function — one Gemini call sends compact result data, gets back ordered indices; integrated as Step 7 in `search_all()` after dedup; graceful fallback on error |
| 24 | 2026-03-03 | Search bar too small in compact mode; make wider but left-aligned | Added `flex:1; min-width:0` to `.hero.compact form`; set `.hero.compact .search-row` to max-width 640px with `margin:0` to keep it left-aligned instead of centered |
| 25 | 2026-03-03 | Show status text for translating/ranking phase (otherwise "Searching" shows too long) | Split `search_all` into `search_phase1` (translate query + search) and `search_phase2` (translate results + rerank); added `/translate-and-rank` endpoint; after searches complete, shows "Translating and ranking results..." breathing text before final results appear |
| 25 | 2026-03-03 | Cache search results for a particular query | Added in-memory `_search_cache` dict keyed on `(query_lower, frozenset(lang_codes))`; `search_all()` checks cache before making any API calls and stores results after completion |
| 26 | 2026-03-03 | Clicking a language then searching should skip "Obtaining languages" and search directly | Fixed: `gatherFormData(event)` now injects langs/polyglot directly into `event.detail.parameters` during `htmx:config-request`, bypassing the hidden-input timing issue |
