import json
import re
import time

from generate_template_variation import generate_template_variation
from generate_story_prompts import generate_story_prompts


PARENT_GREETINGS = [
    {
        "title": "Birthday Wishes",
        "blurb": "To wish them the happiest of birthdays.",
        "questions": [
            "Photo of the birthday star?",
            "Photo of yourself?",
        ],
    },
    {
        "title": "Wedding Congratulations",
        "blurb": "Celebrate the newlyweds on their special day.",
        "questions": [
            "Photo of the happy couple?",
            "Photo of yourself?",
        ],
    },
    {
        "title": "Graduation Celebration",
        "blurb": "Honor the graduate's hard work and bright future.",
        "questions": [
            "Photo of the graduate?",
            "Photo of yourself?",
        ],
    },
]


def parse_variations(raw_response: str) -> list[dict]:
    """Extract the list of variation dicts from the LLM's raw text response."""
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_response)
    raw_json = json_match.group(1).strip() if json_match else raw_response.strip()
    data = json.loads(raw_json)
    return data["variations"]


def format_greeting_prompt(card: dict) -> str:
    return (
        f"Title: {card['title']}\n"
        f"Blurb: {card['blurb']}\n"
        f"Questions: {card['questions']}"
    )


def run_full_workflow(parent_greeting: dict, max_variations: int = 2) -> dict:
    """Run the full pipeline for a single parent greeting card.

    1. Generate template variations from the parent card.
    2. Pick up to `max_variations` and generate story prompts for each.

    Returns a summary dict with the parent, parsed variations, and story outputs.
    """
    prompt = format_greeting_prompt(parent_greeting)
    print(f"\n{'='*60}")
    print(f"Parent: {parent_greeting['title']}")
    print(f"{'='*60}")

    print("  -> Generating template variations...")
    raw_variations = generate_template_variation(prompt)
    variations = parse_variations(raw_variations)
    print(f"  -> Got {len(variations)} variations")

    stories = []
    for i, variation in enumerate(variations[:max_variations]):
        print(f"  -> [{i+1}/{min(max_variations, len(variations))}] "
              f"Generating story for: {variation['title']}")
        variation_prompt = format_greeting_prompt(variation)
        story_output = generate_story_prompts(variation_prompt)
        stories.append({
            "variation": variation,
            "story_prompts": story_output,
        })
        print(f"     Done ({story_output[0][:80]}...)")

    return {
        "parent": parent_greeting,
        "num_variations": len(variations),
        "stories": stories,
    }


def run_all():
    results = []
    for greeting in PARENT_GREETINGS:
        start = time.time()
        result = run_full_workflow(greeting)
        elapsed = time.time() - start
        result["elapsed_seconds"] = round(elapsed, 1)
        results.append(result)
        print(f"  => Finished in {result['elapsed_seconds']}s\n")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for r in results:
        parent_title = r["parent"]["title"]
        n_vars = r["num_variations"]
        n_stories = len(r["stories"])
        print(f"  {parent_title}: {n_vars} variations generated, "
              f"{n_stories} stories created ({r['elapsed_seconds']}s)")
        for s in r["stories"]:
            print(f"    - {s['variation']['title']}")

    failed = [r for r in results if not r["stories"]]
    if failed:
        print(f"\nFAILED: {len(failed)} parent(s) produced no stories.")
    else:
        print(f"\nALL PASSED: {len(results)} parent greetings processed successfully.")

    return results

