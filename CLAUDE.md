# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A greeting card template generator that uses LLMs (via OpenRouter API) to create variations of greeting cards and generate sequential visual story prompts for each variation. The pipeline: parent greeting card → template variations → story scene prompts.

## Commands

- **Run the main pipeline:** `uv run python main.py`
- **Run integration tests:** `uv run python integration_tests.py` (calls live LLM APIs; no pytest)
- **Install dependencies:** `uv sync`

## Architecture

The pipeline has two LLM stages, each calling OpenRouter's chat completions API (`httpx.post`):

1. **`generate_template_variation.py`** — Takes a parent greeting card (title, blurb, questions) and generates themed variations using Claude Opus via OpenRouter. Returns raw LLM text containing JSON with a `variations` array.

2. **`generate_story_prompts.py`** — Takes a variation and generates 10 sequential visual scene descriptions using Gemini 2.5 Pro via OpenRouter. Scenes use `{person_1}`/`{person_2}` placeholders for characters. Returns formatted scene strings with an aesthetic prefix (default: "pixel art").

3. **`main.py`** — Orchestrates the pipeline: calls variation generation, parses JSON response (handles markdown code block wrapping), then generates story prompts for each variation.

4. **`riff_backend.py`** — HTTP client for creating gift templates on a backend API (`BACKEND_ENDPOINT`). Not yet integrated into the main pipeline.

5. **`integration_tests.py`** — End-to-end tests that run the full workflow against live APIs for multiple parent greeting cards (Birthday, Wedding, Graduation).

## Environment Variables (`.env`)

- `OPENROUTER_API_KEY` — Required for LLM calls
- `BACKEND_ENDPOINT` — Required by `riff_backend.py`

## Key Patterns

- LLM responses may be wrapped in markdown code blocks; all JSON parsing uses a regex to extract content from ` ```json ... ``` ` blocks before `json.loads`.
- `generate_story_prompts.py` has a fallback regex parser for malformed JSON responses.
- Uses `uv` for dependency management (Python 3.11+, httpx, python-dotenv).
