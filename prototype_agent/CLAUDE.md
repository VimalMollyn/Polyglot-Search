## Instructions
You are an agent that is going to help me prototype and idea I have detailed in `ideation4.md`. This is a prototype for a project that I am working on.

Here is the prompt of the project:

Project 2 will be a design of a competitor to an existing product. Students will use AI to research the market and the users. They will then use AI to ideate and prototype the new product. They will then test and evaluate the new product. The core learning objective of this project is to have students explore more advanced use of AI for design and reflect upon where AI is useful and where it is not in their own design process.

----------------
- `ideation4.md` — **Multilingual Search Aggregator.** Search once → auto-translate query → search Google in multiple languages → aggregate results with links to original pages.
- Validated pain point (personal experience + Reddit evidence). No direct competitor exists. LLMs don't solve it (they summarize/hallucinate, don't show real links).
- Technical plan: Google Custom Search JSON API (100 free queries/day, $5/1K paid) with language/region params (`lr`, `gl`, `cr`).

## Tech Stack
- **Backend**: Python 3.12 with FastHTML (`python-fasthtml`)
- **Package Manager**: uv (uses `pyproject.toml` and `uv.lock`)

## Architecture
- `app.py` — Single-file FastHTML app serving the full UI inline

## Logging
You must log all questions you've asked into a new `questions.md` file, so that I can use this to review how we did.

Every time the user requests a change, append a new row to the **Change Requests** table in `questions.md` with:
- Sequential number
- Date (today's date)
- The user's request (verbatim or close paraphrase)
- What was actually changed in the code/files


