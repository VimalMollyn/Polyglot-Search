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
| 3 | 2026-02-25 | Deduplicate results pointing to the same page across languages (e.g., Apple developer site shown 5 times) | Added `_normalize_url()` to strip www/trailing slashes for URL matching. Replaced round-robin interleaving with dedup+merge: same URL across languages becomes one card showing all language flags. |
| 4 | 2026-02-25 | Rank results by cross-language frequency — links found in more languages get higher priority, show all flags, prefer English version | Results sorted by `lang_count` descending. English version preferred for title/link when available. Result card shows multiple badges + "Found in N languages" note. Summary shows count of multi-language results. |
