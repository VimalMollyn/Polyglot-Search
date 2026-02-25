# Ideation 4 — Multilingual Search Aggregator

## The Idea
- Search once → auto-translate query into multiple languages → search across different language versions of Google → aggregate and present combined results
- Born from user's lived experience: searching on **Japanese Google** often surfaces better results than English Google for certain topics
- Different language internets have genuinely different content, perspectives, and quality
- **Key differentiator vs LLMs:** Shows real links to real pages. Discovery, not answers. No hallucination.

## Status: Ready to prototype next session

---

## User Pain Points & Evidence

### Reddit: u/nexflatline on r/perplexity_ai (10 upvotes)
**Post:** "Perplexity's unique ability to make searches in a different languages from the query"

**Key quote:** *"If you need information that is not usually available in one language but is abundant in other languages, the reply you get is very strongly biased by the language used in the query, not the language with most resources about what you have asked."*

**Pain points identified:**
1. **All major LLMs (ChatGPT, Gemini, Claude) are strongly biased toward the query language** — even if you explicitly tell them to search in another language, it has "almost no effect"
2. **Perplexity is the only one that partially works** — you can ask it to search in a specific language from specific countries, but:
   - The reply often comes back in that other language (friction)
   - You have to manually ask for translation (extra step)
   - You have to *know* which language to search in (no auto-discovery)
3. **English-language results are often wrong for non-English contexts** — e.g., searching for Japanese hotel law in English gives you "wrong reddit posts and opinions from tourism forums where people just automatically assume things are the same as in their own country"
4. **This applies broadly:** legal info, products, artists, items, places that are famous in one country but unheard of elsewhere

**This validates our core thesis:** The information asymmetry across languages is real, and no product solves it well — even Perplexity only gets partway there with manual prompting.

---

## Competitive Landscape (Research)

### No direct competitor exists
- No dedicated product does "search once in multiple languages, aggregate results"
- Perplexity is closest but requires manual prompting and doesn't auto-discover which languages are relevant

### LLMs partially solve the casual case but fail at rigorous use
- LLMs hallucinate more on non-English content (confirmed by research)
- They hide sources — can't browse original Japanese forum post or German article
- Strong English bias in training data creates blind spots
- Untranslated content is essentially invisible to AI search (Weglot study: 1.3M citations analyzed)

### The gap
| What users need | LLMs today | Multilingual aggregator |
|---|---|---|
| See actual results & browse originals | No — just summaries | Yes |
| Know which languages were searched | Opaque | Transparent |
| Auto-discover best language for a query | No | Core feature |
| No hallucination risk | Always present | Zero — showing real results |
| Fresh/real-time results | Partial, weak for non-English | As fresh as underlying search engines |

---

## Technical Architecture

### Planned flow
```
User types query in English
  → Auto-translate to Japanese, German, French, etc. (translation API or LLM)
  → Fire parallel searches via Google Custom Search API
      (using lr, gl, cr params to target each language/region)
  → Aggregate results
  → Translate snippets/titles back to English
  → Present unified, browsable results with links to original pages
```

### API: Google Custom Search JSON API (official)
- **Free tier:** 100 queries/day
- **Paid:** $5 per 1,000 queries (up to 10,000/day hard cap)
- **Language/region params:**
  - `lr=lang_ja` — restrict results to Japanese language
  - `gl=jp` — geolocation boost (as if searching from Japan)
  - `cr=countryJP` — restrict to country
- Note: `googlehost` param (for targeting google.co.jp directly) is deprecated; use the combo of `lr` + `gl` + `cr` instead
- Results are real Google results but "may differ" slightly from google.com

### Capacity math
- 5 languages per user query = 5 API calls
- Free tier: ~20 user searches/day
- Paid at 10K/day cap: ~2,000 user searches/day (~$50/day)
- **For a class project prototype, free tier is sufficient**

### Alternative APIs (if needed later)
| API | Free tier | Paid | Notes |
|-----|-----------|------|-------|
| **Google CSE** | 100/day | $5/1K queries | Official, clean, recommended for prototype |
| **Serper.dev** | 2,500 one-time | $50/50K/mo | Can set `google_domain=google.co.jp` directly, closest to real localized Google |
| **SerpAPI** | 100/month | $50/5K/mo | Richest structured data |
| **Brave Search** | 2,000/month | ~$3/1K | Own index (not Google), privacy-focused |
| **Bing API** | 1,000/month | $7/1K | Good for English, weaker non-English |

### Translation layer
- Google Translate API, DeepL API, or LLM-based translation for query translation + result snippet translation
- TBD which is best for short search queries vs. snippet translation

---

## Key Design Questions (for prototyping)

1. **How to present results from 5+ languages without overwhelming the user?**
   - Tabs per language? Interleaved with language tags? Grouped sections?
2. **How to rank/interleave results across languages?**
   - By relevance? By language? Let the user choose?
3. **How to signal "this result is unique to Japanese Google"?**
   - This is the core value — surfacing things you'd never find in English
4. **Auto-detect which languages are relevant vs. let user pick?**
5. **Form factor:** Website (simplest for prototype), browser extension, or standalone app?

---

## Why This Could Work (Summary)
- **Real pain point:** User experiences it personally; Reddit validates it broadly
- **No direct competitor:** Nobody does this as a dedicated product
- **LLMs don't solve it:** They summarize, hallucinate, and hide sources. This shows real links.
- **Technically feasible:** Google's own API + translation API. Weekend prototype.
- **Great HCI problem:** The interaction design of mixed-language results is the hard, interesting part
- **Low cost:** Free tier is enough for class project; cheap to scale

## Open Questions
- What's the right scope for a class project prototype?
- Which languages to support initially? (Japanese + English as MVP?)
- Does the user want AI summarization on top, or purely raw results?
- What's the product name?
