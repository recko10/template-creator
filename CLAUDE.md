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

1. **`generate_template_variation.py`** — Takes a parent greeting card (title, blurb, questions) and generates N_VARIATIONS themed variations using Gemini 2.5 Pro via OpenRouter. Returns raw LLM text containing JSON with a `variations` array.

2. **`generate_story_prompts.py`** — Takes a variation and generates 10 sequential visual scene descriptions using Gemini 2.5 Pro via OpenRouter. Scenes use `{person_1}`/`{person_2}` placeholders for characters. Returns formatted scene strings with an `{aesthetic}` placeholder prefix.

3. **`main.py`** — Orchestrates the full pipeline and contains several additional LLM-powered helpers (all using Gemini 2.5 Flash):
   - `pick_visual_tag()` — Selects the best visual style (from VISUAL_TAGS map of UUID→style name) for a variation
   - `pick_person_images()` — Chooses appropriate person images (from IMAGE_URLS) for panel generation based on template demographics
   - `shorten_template_name()` — Shortens a title to 3 words for cover art text
   - `process_variation()` — End-to-end single variation: story prompts → create template → regenerate panels → cover art
   - `create_templates_full()` — Full pipeline: generate variations then process each in parallel (ThreadPoolExecutor, 3 workers)
   - `generate_text_params()` / `regenerate_with_text_params()` — Adds text input parameters (name, personal message) to templates and regenerates panels with them
   - Also contains backfill utilities and ID lists (DEV_IDS, PROD_IDS, BIRTHDAY_TEMPLATE_IDS) for batch operations

4. **`riff_backend.py`** — HTTP client for the backend API (`BACKEND_ENDPOINT`). Functions: `create_gift_template`, `update_gift_template`, `get_gift_template`, `regenerate_panels`, `update_gift_template_image`, `backfill_gift_template_music`, `generate_nanobanana`, `add_templates`, `add_text_param`.

5. **`integration_tests.py`** — End-to-end tests that run the LLM stages (variation + story generation) against live APIs for Birthday, Wedding, and Graduation parent cards. Does not hit the backend API.

## Environment Variables (`.env`)

- `OPENROUTER_API_KEY` — Required for all LLM calls
- `BACKEND_ENDPOINT` — Required by `riff_backend.py` and `main.py`
- `ADMIN_PASSWORD` — Required by `riff_backend.py` for admin API endpoints

## Key Patterns

- LLM responses may be wrapped in markdown code blocks; all JSON parsing uses `re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)` to extract content before `json.loads`.
- `generate_story_prompts.py` has a fallback regex parser for malformed JSON responses.
- Uses `uv` for dependency management (Python 3.11+, httpx, python-dotenv).
- Concurrency: `ThreadPoolExecutor` with 3 workers for parallel variation processing.
- LLM models: Gemini 2.5 Pro for generation tasks, Gemini 2.5 Flash for lightweight classification/selection tasks. All via OpenRouter.

## Placeholder System

Story prompt strings use three types of placeholders that get resolved at different stages:

1. **`{aesthetic}`** — Filled at panel generation time with the visual tag's style name (e.g., "Oil Painting", "Ghibli-style Anime")
2. **`{person_1}`, `{person_2}`** — Character image placeholders, resolved via `referrer_map` during `regenerate_panels()`
3. **`{their_name}`, `{personal_message}`** — Text input parameters filled by the end user at card creation time

## Template Config Structure

Templates use a `config` dict with `version`, `num_subjects` (image params), `num_panels` (scene count), `system_prompt`, and a `prompts` array of `{position, prompt}` objects. Text parameters are added separately via `add_text_param()` with position-based ordering.
