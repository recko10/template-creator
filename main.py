import json
import re

from generate_story_prompts import generate_story_prompts
from generate_template_variation import generate_template_variation
from riff_backend import add_templates


def parse_variations(raw: str) -> list[dict]:
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    raw_json = json_match.group(1).strip() if json_match else raw.strip()
    data = json.loads(raw_json)
    return data["variations"]

def populate(greeting_card: dict) -> dict:
    prompt = (
        f"Title: {greeting_card['title']}\n"
        f"Blurb: {greeting_card['blurb']}\n"
        f"Questions: {greeting_card['questions']}"
    )

    raw_response = generate_template_variation(prompt)
    print("Raw response:")
    print(raw_response)

    variations = parse_variations(raw_response)
    print("Variations:")
    print(variations)

    story_prompts = []
    for variation in variations:
        variation_prompt = (
            f"Title: {variation['title']}\n"
            f"Blurb: {variation['blurb']}\n"
            f"Questions: {variation['questions']}"
        )
        print(variation_prompt)
        story_prompt = generate_story_prompts(variation_prompt)
        print(story_prompt)
        story_prompts.append(story_prompt)

    results = add_templates(variations, story_prompts)
    print("Template creation results:")
    print(results)

    return {
        "story_prompts": story_prompts,
        "variations": variations,
        "results": results,
    }

print(populate({
    "title": "Birthday Wishes",
    "blurb": "To wish them the happiest of birthdays.",
    "questions": [
        "Photo of the birthday star?",
        "Photo of yourself?"
    ]
}))