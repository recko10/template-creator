# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A greeting card template generator that uses LLMs (via OpenRouter API) to create variations of greeting cards, generate sequential visual story prompts, and publish them to a backend API. The full pipeline: parent greeting card → template variations → story scene prompts → backend creation → panel generation → cover art.

## Commands

- **Run the main pipeline:** `uv run python main.py`
- **Run integration tests:** `uv run python integration_tests.py` (calls live LLM APIs; no pytest)
- **Install dependencies:** `uv sync`

## Architecture

### LLM Stages (all via OpenRouter chat completions API)

1. **`generate_template_variation.py`** — Takes a parent greeting card (title, blurb, questions) and generates N_VARIATIONS (currently 50) themed variations using Gemini 2.5 Pro via OpenRouter. Returns raw LLM text containing JSON with a `variations` array.

2. **`generate_story_prompts.py`** — Takes a variation and generates 10 sequential visual scene descriptions using Gemini 2.5 Pro via OpenRouter. Scenes use `{person_1}`/`{person_2}` placeholders for characters. Returns formatted scene strings with an `{aesthetic}` placeholder prefix.

3. **`main.py`** — Orchestrates the full pipeline and contains several additional LLM-powered helpers (all using Gemini 2.5 Flash):
   - `pick_visual_tag()` — Selects the best visual style (from VISUAL_TAGS map of UUID→style name) for a variation
   - `pick_person_images()` — Chooses appropriate person images (from IMAGE_URLS) for panel generation based on template demographics
   - `shorten_template_name()` — Shortens a title to 3 words for cover art text
   - `process_variation()` — End-to-end single variation: story prompts → create template → regenerate panels → cover art
   - `create_templates_full()` — Full pipeline: generate variations then process each in parallel (ThreadPoolExecutor, 5 workers)
   - `create_single_template()` — Convenience wrapper around `process_variation()` for one-off template creation
   - Also contains backfill utilities, cover art regeneration, and large ID lists (PROD_IDS, BIRTHDAY_TEMPLATE_IDS, etc.) for batch operations

4. **`riff_backend.py`** — HTTP client for the backend API (`BACKEND_ENDPOINT`). Functions: `create_gift_template`, `update_gift_template`, `get_gift_template`, `regenerate_panels`, `update_gift_template_image`, `backfill_gift_template_music`, `generate_nanobanana`, `add_templates`, `add_collection_items`.

5. **`integration_tests.py`** — End-to-end tests that run the LLM stages (variation + story generation) against live APIs for Birthday, Wedding, and Graduation parent cards. Does not hit the backend API.

### Single Variation Pipeline (`process_variation`)

Each variation goes through these steps sequentially:
1. Generate 10 story scene prompts (Gemini 2.5 Pro)
2. Pick a random visual tag (no LLM call)
3. Build config with referrer placeholders (question names → `{snake_case}` referrers replacing `{person_1}`/`{person_2}` in prompts), then create template in backend
4. Regenerate panel previews — picks person images via LLM, then calls backend `regenerate_panels`
5. Generate cover art — shortens title to 3 words via LLM, takes panel 8's image, runs it through `generate_nanobanana` to add poster text, then sets as template image

## Environment Variables (`.env`)

- `OPENROUTER_API_KEY` — Required for all LLM calls
- `BACKEND_ENDPOINT` — Required by `riff_backend.py` and `main.py`
- `ADMIN_PASSWORD` — Required by `riff_backend.py` for admin API endpoints

## Key Patterns

- LLM responses may be wrapped in markdown code blocks; all JSON parsing uses `re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)` to extract content before `json.loads`.
- `generate_story_prompts.py` has a fallback regex parser for malformed JSON responses.
- Story prompt strings contain an `{aesthetic}` placeholder that gets filled at panel generation time with the visual tag's style name.
- Uses `uv` for dependency management (Python 3.11+, httpx, python-dotenv).
- LLM model split: Gemini 2.5 Pro for heavy generation (variations, story prompts), Gemini 2.5 Flash for lightweight helpers (visual tag, person images, title shortening).
- `main.py` is run as a script — the entry point is typically uncommenting/editing function calls at the bottom of the file, not a CLI interface.
