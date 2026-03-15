import json
import os
import re
import httpx
import dotenv

dotenv.load_dotenv()

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-opus-4.6"
N_VARIATIONS = 100

SYSTEM_PROMPT = f"""
You are an expert at creating personal greeting cards. 
A personal greeting card is a card that includes questions directed to the sender of the card asking for relevant photos/info to make the card more personal.

Your task:
-Given an existing personal greeting card, you must generate {N_VARIATIONS} variations of the card.
-A variation is defined as a personal greeting card that has the same core premise as its parent card, but is more specific and paints a novel scenerio.
-Be creative with the variations by entrenching them in a specific theme, not just scenerio. For example, "Mamma Mia Themed Sweet 16" beats "Sweet 16 Birthday Wishes". Themes do not have to relate to pop culture, but should be fun or novel. Similar to how Hallmark cards are structured.

Examples of bad greeting card variations:
- "Sports Birthday Wishes"
- "Finally 21!"
- "Daily Horoscope"
- "Happy Diwali!"

Examples of great greeting card variations:
- "Football Themed Birthday"
- "Casamigos-filled 21st Birthday"
- "Aquarius Daily Horoscope"
- "Cracking eggs on Diwali!"

An example of a personal greeting card:

Title: "Birthday Wishes"
Blurb: "To wish them the happiest of birthdays."
Questions:
- "Whose birthday is it?"
- "A picture of the birthday star?"
- "A picture of yourself?"

An example of 1 variation of the above card:

Title: "Giraffe Themed Birthday"
Blurb: "Send this to a boy who loves giraffes!"
Questions:
- "Photo of the birthday star?"
- "Photo of yourself?"

Requirements:
-Only include photo related questions. You may use either exactly 1 or 2 questions based on whether the card is dedicated to just yourself (yes this is possible), just someone else, or involves both you and someone else.
-Make sure the questions are labeled plainly, such as "photo of yourself?" or "photo of the birthday star?", as some basic examples. Do not be too poetic here.
-If there are obvious variations, you should just use those. For example, "Daily Horoscope" can easily be broken down into "Aquarius Daily Horoscope", "Pisces Daily Horoscope", etc.
-You are allowed to be creative with the titles, but make it clear what the card is about whenever you decide to do this.
-Return your result in JSON format like so:

```json
{{
    "variations": [
        {{
            "title": "variation 1 title",
            "blurb": "variation 1 blurb",
            "questions": [
                "variation 1 question 1",
                "variation 1 question 2",
                "variation 1 question 3",
            ]
        }},
        {{
    ]
}}
"""

def generate_template_variation(user_prompt: str, timeout: int = 120) -> str:
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
                {"role": "user", "content": f"Generate {N_VARIATIONS} variations of the following card: " + user_prompt},
            ],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


# GREETING_CARD_INFO = {
#     "title": "Birthday Wishes",
#     "blurb": "To wish them the happiest of birthdays.",
#     "questions": [
#         "Whose birthday is it?",
#         "A picture of the birthday star?",
#         "A picture of yourself?",
#     ]
# }

# GREETING_CARD_PROMPT = f"""
# Title: {GREETING_CARD_INFO["title"]}
# Blurb: {GREETING_CARD_INFO["blurb"]}
# Questions: {GREETING_CARD_INFO["questions"]}
# """
# print(generate_template_variation(GREETING_CARD_PROMPT))
