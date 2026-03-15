import json
import os
import re
import httpx
import dotenv

dotenv.load_dotenv()

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.5-pro"

N_SCENES = 10

SYSTEM_PROMPT = f"""
You are an expert storyteller who specializes in describing visual scenes that sequentially tell a story.
You have been hired by a greeting card company that is looking to convert their boring old greeting cards into sequential stories. 

You will receieve:
- The title of a greeting card
- A short blurb about the greeting card
- Questions directed to the sender of the card that correspond to who the greeting card is for / who is sending it. These should be used to determine the characters of the story.

Your Task: 
-Given this information, you must create a series of {N_SCENES} visual scenes that sequentially tell the story of that greeting card.
-Each scene will involve either 1 or 2 characters, denoted by {{person_1}} and {{person_2}}. Each scene must refer to at least one of the characters.

Scene Description Requirements:
-The scene description to follow this order: Subject → Setting → Details → Lighting → Atmosphere. That is, describe the subjects first, then the setting, then the details, then the lighting, then the atmosphere.

For example, great word ordering would be:
An elderly woman with silver hair carefully arranges wildflowers in a ceramic vase. Soft afternoon light streams through lace curtains, casting delicate shadows across her focused expression.

Poor word ordering would be:
In a warm, nostalgic room with antique furniture, soft afternoon light streams through lace curtains. An elderly woman with silver hair is there arranging wildflowers

Hard Requirements:
-The story should be easy to follow and MUST logically follow the theme. For example, a story about a space-themed birthday can involve the characters building a rocket to go to space, but it MUST logically end with something birthday-related, like finding a cake on the moon.
-Make sure you describe each scene independent of the other ones. For example, if you mention some object like a "big green basketball" in one scene, you cannot just say "the basketball" in a different scene, since they are independent. The correct approach is to say "big green basketball" again. You should know that each of these prompts will be passed to an image model (independently) to create the scenes.
-If the greeting is directed to a specific demographic, you don't have to specify that in story. For example, if the title is "Dinosaur Roar Birthday for Boys", you shouldn't say "{{person_1}} is a boy" or "{{person_2}} is a boy". Just assume they are one.
-Stories should NEVER be about just opening a greeting card. The point of this story is to be an engaging alternative to just opening a greeting card. It should paint a scenerio like the event happening, or something fantastical.
-Return your result in JSON format like so:

```json
{{
    "scenes": {{
        "scene_1": "description of scene 1",
        "scene_2": "description of scene 2"
    }}
}}
```

Example:

Title: "Power Puff Themed Birthday"
Blurb: "Send this to a girl who loves Power Puff Girls!"

Q1: "Photo of the birthday star?"
Q2: "Photo of yourself?"

From this, you must recognize that the characters are the birthday star and the sender. The birthday star corresponds to {{person_1}} and the sender corresponds to {{person_2}}.

The story should be:

{{
    "scenes": {{
        "scene_1": "{{person_1}} excitedly receives a colorful birthday card featuring the Power Puff Girls.",
        "scene_2": "{{person_1}} opens a greeting card and discovers a cheerful message inside.",
        "scene_3": "{{person_1}} shows a greeting card to {{person_2}}, sharing a smile.",
        "scene_4": "{{person_1}} and {{person_2}} strike Power Puff Girl poses together.",
        "scene_5": "{{person_1}} imagines becoming a superhero like the Power Puff Girls, with {{person_2}} cheering them on."
    }}
}}

"""

def generate_story_prompts(greeting_card_info: str) -> str:
    response = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Make me a sequential story for the following greeting card: " + greeting_card_info},
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]

    # Parse JSON from response (may be wrapped in markdown code blocks)
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    raw_json = json_match.group(1).strip() if json_match else content.strip()

    try:
        data = json.loads(raw_json)
        scenes = data.get("scenes", data)
        if isinstance(scenes, dict):
            scenes = list(scenes.values())
        elif isinstance(scenes, list):
            pass
        else:
            scenes = []
    except json.JSONDecodeError:
        # Fallback: extract "scene_N": "description" pairs via regex when JSON is malformed
        scenes = []
        for m in re.finditer(r'"scene_\d+":\s*"((?:[^"\\]|\\.)*)"', raw_json):
            scenes.append(m.group(1).replace('\\"', '"').replace("\\n", "\n"))
    formatted = []
    for scene in scenes:
        formatted.append(
            f"Create the following scene in a {{aesthetic}} style:\n\n{scene}"
        )
    return formatted
