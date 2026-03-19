import json
import os
import random
import re

import dotenv
import httpx

from generate_story_prompts import generate_story_prompts
from generate_template_variation import generate_template_variation
from riff_backend import add_templates, create_gift_template, get_gift_template, update_gift_template, regenerate_panels, generate_nanobanana, update_gift_template_image, backfill_gift_template_music, add_collection_items
from concurrent.futures import ThreadPoolExecutor, as_completed

dotenv.load_dotenv()

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

VISUAL_TAGS = {
    "04f82724-5532-4409-b308-3170151e1dec": "Oil Painting",
    "0d037ca2-6e6e-4ac4-9803-52f6d771c8e6": "Ghibli-style Anime",
    "1c4f6bb3-35c5-49d1-b3b2-773f6b3ea859": "Children's Storybook",
    "1ef914c7-1e6e-4dc2-873e-b128894a6189": "3D Cartoon",
    "3b1c8bb1-251a-441d-b77b-921b493910f4": "Claymation",
    "3cd9e793-3982-4862-aee6-d17f80290f8c": "Photorealistic",
    "42be0fce-1121-4f3c-b7af-e8a4157860af": "Newspaper Comic",
    "565e41ce-e43a-4581-904f-2969bafa0bc7": "Cut Paper Collage",
    "5e4c30ec-ab71-4617-b28b-c15ac001e32d": "Risograph Print",
    "60206eb2-bf52-4b46-ac2b-6aa696a23914": "Low-Poly 3D",
    "63bfe536-adfc-46e2-a029-30cf22b96fbe": "Hand-drawn",
    "758c2081-582c-4924-80cb-4699a90314f0": "Mid-century Editorial Illustration",
    "9355145d-4291-4378-afb7-56d8891c86aa": "Black and White Manga Panels",
    "c545bc6c-2c9a-4be9-b590-dcd58760dc85": "Retro Anime",
    "c9f52b23-a3fd-4495-bac5-cae05581c4ce": "Watercolor",
    "fee44934-cf07-4c6d-809e-8f523d59730e": "Pixel Art",
}

def pick_visual_tag(title: str, blurb: str) -> str:
    options = "\n".join(f"- {name}" for name in VISUAL_TAGS.values())
    prompt = (
        f"Greeting card title: {title}\n"
        f"Blurb: {blurb}\n\n"
        f"Pick the single best visual style for this greeting card from the options below:\n{options}\n\n"
        "Return ONLY the exact style name, nothing else."
    )

    response = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "google/gemini-2.5-flash",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=15,
    )
    response.raise_for_status()
    chosen_name = response.json()["choices"][0]["message"]["content"].strip()

    # Find the tag ID matching the chosen name
    name_to_id = {name: tag_id for tag_id, name in VISUAL_TAGS.items()}
    tag_id = name_to_id.get(chosen_name)
    if tag_id is None:
        # Fuzzy fallback: find closest match
        chosen_lower = chosen_name.lower()
        for name, tid in name_to_id.items():
            if chosen_lower in name.lower() or name.lower() in chosen_lower:
                tag_id = tid
                break
    if tag_id is None:
        tag_id = random.choice(list(VISUAL_TAGS.keys()))
        print(f"Warning: LLM returned unknown style '{chosen_name}', falling back to random")

    print(f"Visual tag for '{title}': {chosen_name} -> {tag_id}")
    return tag_id

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
    visual_tag_ids = []
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
        visual_tag_ids.append(pick_visual_tag(variation["title"], variation["blurb"]))

    results = add_templates(variations, story_prompts, visual_tag_ids=visual_tag_ids)
    print("Template creation results:")
    print(results)

    return {
        "story_prompts": story_prompts,
        "variations": variations,
        "results": results,
    }

def regenerate_gift_template_config(gift_template_id: str) -> dict:
    full = get_gift_template(gift_template_id)["data"]

    questions = [p["name"] for p in full["parameters"]]
    prompt = (
        f"Title: {full['name']}\n"
        f"Blurb: {full['blurb']}\n"
        f"Questions: {questions}"
    )
    print(f"Generating story prompts for: {full['name']}")

    story_prompts = generate_story_prompts(prompt)
    print(story_prompts)

    config = {
        "version": 4,
        "num_panels": len(story_prompts),
        "system_prompt": "Create the following scene in a {aesthetic} style:\n\n",
        "parameters": [
            {
                "referrer": p.get("referrer", f"{{{p['name']}}}"),
                "type": p.get("type", "image"),
                "name": p["name"],
                "position": p.get("position", i),
                "required": p.get("required", True),
            }
            for i, p in enumerate(full["parameters"])
        ],
        "prompts": [
            {"position": str(j), "prompt": prompt}
            for j, prompt in enumerate(story_prompts)
        ],
    }

    result = update_gift_template(gift_template_id, config=config)
    print("Update result:")
    print(result)
    return result

IMAGE_URLS = {
    "indian_man": "https://db.goriff.com/storage/v1/object/public/logo/aihuman/indian-man.jpg",
    "indian_woman": "https://db.goriff.com/storage/v1/object/public/logo/aihuman/indian-woman.jpg",
    "white_man": "https://db.goriff.com/storage/v1/object/public/logo/aihuman/white-man.jpg",
    "white_woman": "https://db.goriff.com/storage/v1/object/public/logo/aihuman/white-woman.jpg",
    "boy": "https://db.goriff.com/storage/v1/object/public/logo/aihuman/boy.jpg",
    "girl": "https://db.goriff.com/storage/v1/object/public/logo/aihuman/girl.jpg",
    "grandma": "https://db.goriff.com/storage/v1/object/public/logo/aihuman/grandma.jpeg",
    "grandpa": "https://db.goriff.com/storage/v1/object/public/logo/aihuman/grandpa.jpeg",
}

def pick_person_images(template_name: str, template_blurb: str, questions: list[str]) -> tuple[str, str]:
    prompt = (
        f"Template name: {template_name}\n"
        f"Blurb: {template_blurb}\n"
        f"Questions/parameters: {questions}\n\n"
        "Based on this greeting card template, pick the best person_one and person_two images.\n\n"
        "Available options: indian_man, indian_woman, white_man, white_woman, boy, girl, grandma, grandpa\n\n"
        "Rules:\n"
        "- If the template is for an Indian festival or culturally Indian, use Indian people.\n"
        "- If woman-centric (e.g. 'for Mom', 'for her'), person_one should be a woman.\n"
        "- If man-centric (e.g. 'for Dad', 'for him'), person_one should be a man.\n"
        "- If for a grandma (e.g. 'for Grandma', 'for Nana'), person_one should be grandma.\n"
        "- If for a grandpa (e.g. 'for Grandpa'), person_one should be grandpa.\n"
        "- If for a boy (e.g. 'for Boys', 'for Son'), person_one should be boy.\n"
        "- If for a girl (e.g. 'for Girls', 'for Daughter'), person_one should be girl.\n"
        "- person_one and person_two should be different people.\n"
        "- Never pick the same character twice. If you need two women, for example, use white_woman and indian_woman.\n"
        "- For generic templates, pick any reasonable combination.\n\n"
        "Return JSON only, no explanation:\n"
        '{"person_one": "<option>", "person_two": "<option>"}'
    )

    response = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "google/gemini-2.5-flash",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]

    print("Character selection response:")
    print(content)

    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    raw_json = json_match.group(1).strip() if json_match else content.strip()
    data = json.loads(raw_json)

    person_one_url = IMAGE_URLS[data["person_one"]]
    person_two_url = IMAGE_URLS[data["person_two"]]
    return person_one_url, person_two_url

def regenerate_template_previews(tid: str):
    full = get_gift_template(tid)["data"]
    visual_tags = [t for t in full.get("tags", []) if t["type"] == "visual"]
    if visual_tags:
        aesthetic = visual_tags[0]["system_prompt"] or visual_tags[0]["display_name"]
    else:
        aesthetic = "pixel art"

    questions = [p["name"] for p in full.get("parameters", [])]
    person_one_url, person_two_url = pick_person_images(full["name"], full["blurb"], questions)
    print(f"{full['name']}: person_one={person_one_url}, person_two={person_two_url}")

    return regenerate_panels(
        tid,
        aesthetic=aesthetic,
        person_one_image_url=person_one_url,
        person_two_image_url=person_two_url,
    )

# with ThreadPoolExecutor(max_workers=2) as executor:
#     futures = {executor.submit(regenerate_for_template, tid): tid for tid in PROD_IDS}
#     for future in as_completed(futures):
#         template_id = futures[future]
#         try:
#             future.result()
#             print(f"Regenerated panels for {template_id}")
#         except Exception as e:
#             print(f"Failed to regenerate panels for {template_id}: {e}")

def shorten_template_name(template_name: str) -> str:
    response = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "google/gemini-2.5-flash",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f'Shorten this title to 3 words max: "{template_name}"\n\n'
                        "Keep the core meaning. Return ONLY the shortened title, nothing else."
                    ),
                }
            ],
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip().strip('"')

def regenerate_cover_art(gift_template_id: str) -> dict:
    full = get_gift_template(gift_template_id)["data"]

    refs = full.get("gift_template_references", [])
    panel_image_url = refs[7]["image_url"]

    short_name = shorten_template_name(full["name"])
    print(f"Shortened name: {full['name']} -> {short_name}")

    size = random.choice(["large"])
    # prompt = f'Add {size} text that reads "{short_name}" at the top of this image in a style that matches its aesthetic. The resulting image should not need to be exact — you must interweave the text in a natural way into the image so that it doesnt just feel like a title, but rather is woven thoughtfully. As a hard requirement, the text should never be blocked or covered by anything in the image.'
    prompt = f'Create a cohesive poster for a story called "{short_name}". Use the provided image as the main illustration and add poster text "{short_name}" in the appropriate spot, blending in with the surrounding elements. The resulting image should not need to be exact — you must interweave the text in a natural way into the image so that it doesnt just feel like a title, but rather is woven thoughtfully. As a hard requirement, the text should never be blocked or covered by anything in the image. As a hard requirement, none of the people in the photo should have any physical contact (if this exists, you should change the photo to have NO body contact -- you may change the entire photo to achieve this).'
    print(f"Cover art for {full['name']}: using panel 8, prompt: {prompt}")

    result = generate_nanobanana(prompt, image_urls=[panel_image_url], aspect_ratio="3:4", model="nanobanana")
    print(f"Nanobanana result for {full['name']}: {result}")

    asset_id = result["data"]["asset_id"]
    update_result = update_gift_template_image(gift_template_id, asset_id)
    print(f"Updated cover art for {full['name']}")
    return update_result

def sanitize_cover_art(gift_template_id: str) -> dict:
    full = get_gift_template(gift_template_id)["data"]

    refs = full.get("gift_template_references", [])
    panel_image_url = refs[7]["image_url"]

    short_name = shorten_template_name(full["name"])
    print(f"Shortened name: {full['name']} -> {short_name}")

    size = random.choice(["large"])
    prompt = f'Make these two characters stand farther away from each other, while smiling to each other. NO physical contact. Make the title text "Totally 80s Congrats"'
    print(f"Cover art for {full['name']}: using panel 8, prompt: {prompt}")

    result = generate_nanobanana(prompt, image_urls=[panel_image_url], aspect_ratio="3:4", model="nanobanana")
    print(f"Nanobanana result for {full['name']}: {result}")

    asset_id = result["data"]["asset_id"]
    update_result = update_gift_template_image(gift_template_id, asset_id)
    print(f"Updated cover art for {full['name']}")
    return update_result

PROD_IDS = [
    "93b6da56-97e2-4f79-8e3e-b34e84f4bb99", "315b70c0-671e-44df-abf7-c268a81470a5", 
    "32b9323e-6412-4862-aabb-f9e891ff4cc0", "5bb2f77b-28f0-41fe-98bb-fe612de6fadf", 
    "93b98849-47ca-4ed7-ae9f-4a078f859081", "fc4deed7-8be3-41e2-9ac5-16319c79c5ab", 
    "1c3c6f58-6f71-4137-bd96-9a2aae8c88c6", "7b4834cc-c165-43ab-990f-e8f49f62ec67", 
    "79849175-4c0b-4ff7-9c28-c85891b5c552", "dd8bb77c-e0d5-44ce-94da-b36851e7700f", 
    "5dcc247a-d047-42cf-8a7d-0b1384f7afa9", "018a6a4a-29f8-4d1a-aaa1-208a7bbd1a70", 
    "2a75fad1-ad8b-4b90-8a96-ababf2b077e6", "2b474138-4efe-490e-b4f6-68a7888c1bc3", 
    "8930250c-84d1-4cb0-aca6-e0ed9faa48d3", "089436a1-cb71-4609-b144-c2de0df5d5f9", 
    "1865ec07-a30b-4baa-81fc-a5821d865123", "0b831a85-7d16-4a43-a785-3a5a2062e722", 
    "2a0192c7-9389-42cc-aed8-6d5348be9f61", "b837a44b-38b6-4727-a799-201f769ec709", 
    "ce5c614f-5c6f-47ce-8fe7-71b186196fec", "d58f797b-ff13-4514-8f8d-5b67d54478a3", 
    "dc886ad1-27c9-4acc-af29-0a4ab259a8b6", "f5056d04-792b-4a38-b41c-5d9767628c9e", 
    "fe6c9dea-99ae-45f9-944c-146493a030d6", "8714daba-1ad2-42df-a399-c45f70de5b41", 
    "6a5ab22e-9afe-47f0-ba68-00f591038dd0", "7df221c0-fa5f-43c5-a7da-632c49903331", 
    "8bfb4d08-bc54-428c-b581-e9e45a2b5aa4", "998b9a9b-1349-4ac2-8d7a-00e11f9b625f", 
    "93d818d3-b934-4dfb-b3d8-6fc6ede0f699", "a6a48c5a-ed1d-4c40-a54b-eff05a6c3e07", 
    "b4f70a78-b23c-41ff-8267-1e2822ac3b0f", "495b8f23-7a1b-481d-81af-b1bc7d0d511d", 
    "aa41775b-72c2-4535-9175-3fe160438e08", "4bfdfbfa-6a6c-47c9-a422-c7c78cee7f56", 
    "002958c4-d444-49c7-aa2e-cd20d7ea9fed", "2caa6d91-fca8-48b7-8d5e-8a4ddb02e3ec", 
    "fb9fdc43-1af6-48ad-8500-2ecc03bce72f", "b6f011a9-2504-4345-9eea-59537d84399a", 
    "d019555b-dd9c-4c41-8b19-e5409180830e", "4d90f35b-4659-4e94-85b5-8530a7ba71ea", 
    "583057d1-b049-417f-bba6-ef27bd00492e", "fb24603d-5336-4824-9404-9e17d2ddba06", 
    "62236659-110e-4a5b-a3ee-37e650d3245b", "0cbe0dde-74d2-4f64-b291-307ba5f044b4", 
    "3b4d6cf8-d567-4b49-993b-802f6b81de2c", "674a0956-87a2-40dd-ae30-cf412976d2b9", 
    "a2f4d8f1-13fc-48f5-ad24-0c7c1b1358b8", "684cdcb6-b700-46e0-9b4e-ae0979078844", 
    "2d07254b-6199-46ed-9ba7-6493e91ab0e8", "c8bd88c9-6b0f-4aa6-9e30-289c0946ce63", 
    "cce726c7-48a5-4b8a-a204-a37d6cb41362", "ca1a03aa-717f-4127-9ca8-8458414896c7", 
    "0f7b8dba-37dc-4ecf-89dc-cb855cd3e506", "4644d237-8db7-458e-9e22-771c725e14ec", 
    "b7305fb8-b209-41e5-8708-9a0335775428", "5364ce06-45bb-4291-8162-ca0b27a26cfa", 
    "7b4dc997-7195-4bcf-8d39-557ed7d08918", "da32102e-ef42-49c7-88e0-5f05bd2999f4", 
    "de5371d5-0c56-4faa-acbc-b71f603c89a9", "e511a3b6-b7b1-47b1-a6c3-41e3b077b114", 
    "90869c84-b372-4615-8e01-e8237f515542", "407dee79-7d8f-4e7a-a2dc-4e819ce3738e", 
    "eb32775f-33ac-4280-b004-36e723747721", "f60a110d-d108-4d13-9cb9-544fefd0c967", 
    "52c0db91-10e2-4beb-8ede-4bc788478a23", "9de28483-6306-4bca-aa1f-9d65083acb9b", 
    "a23793e0-db41-49c3-bad8-9c5d96d9ba19", "a6ec4f04-f094-41fc-a632-5a07c5dc5dde", 
    "c51fd5fe-ddd8-4648-9061-c31e59bf9a10", "5c7a4e24-c42b-4ba7-80c4-2466df2676d3", 
    "6e0d415f-443d-47d9-b6cf-b0f8a3e22774", "c755f8f0-35e2-4a6f-82ac-c83868d0435b", 
    "ce22819f-2392-4ab2-bed2-b69a326c0cce", "cf710551-1df4-42d6-a8a7-a5cc8059958b", 
    "e59515b9-9f4e-420d-8bbb-3123a54f2015", "00099e19-74ff-4600-97fb-7b45e6e34c44", 
    "8cb5fc81-f71f-4bf5-b785-5774bdf02c18", "22a9d7ed-221f-41f3-82b4-639de99403c8", 
    "ad1a5a98-40dc-41d4-b0f3-9d050ced27a8", "b8f5c0be-e2d6-4600-a4c2-234afedcec2f", 
    "c6885bc0-0a3e-47a8-ac86-4c6196be7e4b", "3bfd7a58-2e01-4a77-960a-fcaf0e6b3bfd", 
    "cc18c509-32e5-489a-b7d7-2141c1c305da", "3a9e7745-f312-4938-a133-583da29d26ff", 
    "fb84d7ca-5ae5-41f2-9121-2bc93622bd4c", "cf8d0f36-d1dc-49ad-902d-eae9cf57aef6", 
    "3aa8dfae-1d34-49b8-8f89-bcc0902f02d7", "470de4d7-4d92-4f5f-8df4-318f735ef1de", 
    "2dcbe4a1-2012-43e8-a4ca-a94882d0df97", "ecf22a95-988e-48f8-a987-b89d9dc22cb5", 
    "f1a3b1be-d5d4-4170-82bf-5b9eb6c4c357", "b7e98b90-3e5a-4db7-b1d5-3fe47c20daa4", 
    "90cb65f7-001d-497c-b57e-aa63c1c62a3b", "2e0f891d-8bb9-4b02-943e-624492942031", 
    "1ec43965-65e9-4035-9f24-88013f8d6d20", "3e5f512e-1b2b-4f66-a47e-890a72203c09", 
    "4e68c512-cfbc-4c6b-b411-307c6bd2da9d", "567050ac-f574-4765-ac57-e7f792fea647", 
    "69e9ce36-2420-43b5-9bdd-76531244638c", "d5756ccb-eeeb-4fab-b7a3-9eaa895f40e0", 
    "60c4064f-5c84-43e1-977c-0d19bae3613e", "fedf40eb-04a1-43f7-b761-ee22d2771a0d", 
    "7d87264d-b076-488a-a162-85d51cc2e1bf", "18991d54-9285-4d52-8838-1a1ebaf2bc1a", 
    "2e71dad0-35ce-4826-877e-5f2991ed5595", "eeddb822-82e1-404f-8c1a-47111ceb4bcf", 
    "36842f17-e74d-47fd-aa07-deb6e1eab221", "3cb650a9-d84f-4509-8a5a-e4376630b824", 
    "570766d8-fc45-41ed-acb8-9f206029c700", "60fc477a-ea25-4012-94eb-90749224644d", 
    "e4d65df9-0795-4f06-a048-62ae4df3a8e0", "9eec34fc-3b13-42f7-accd-252bee96d8ef", 
    "6d2a34ad-561d-4baf-81f2-801af054d927", "fcc7d063-9905-4d82-95b0-7d4592816c32", 
    "a71c73d2-29f4-46fb-860b-e3399cba2dce", "a6c6ce1d-9bbe-49e4-b4f9-9e4567ec2854", 
    "6e0ad0da-8591-4b07-86ae-23ce4f9a6f06", "ddcd1914-fd6a-4ee1-809d-73c1b4b1a05d", 
    "85b1cb4c-5100-4559-a725-bff904d98d9d", "dff5bd41-4808-4210-ac48-defe5cd67336", 
    "9c1b7ea2-87b6-420e-b73f-22332aa12e86", "f1a4083b-75f7-4d66-850c-5d326a6920e7", 
    "1700595f-3761-4f66-b38e-e411c496827e", "29d58290-aa49-4c87-b0cf-822588447381", 
    "35a40ecb-ca95-49f2-b637-4b25c10fd85d", "af0396c7-eaf6-4529-bb55-e823b3a41960", 
    "b6ef2ff5-e398-4aa2-af85-76d33301cb27", "bd0c3d2f-4ba8-4de6-b904-5468ae2592b3", 
    "c8f6388b-1fc7-4e67-a391-89dc3cac03cc", "cb0ec69c-a637-4640-9fae-7b8f9af20a27", 
    "11576c28-1106-4005-9673-15b53e6833d5", "1bf5115a-7986-4b39-8db0-51ba1617ed2a", 
    "e97f7823-ea24-4905-9905-e44177f7aba6", "e81fd049-b6a1-4c1c-a49b-c575aa39b08c", 
    "294440b9-41c3-4378-95fb-73aa4af435ce", "3f2c53d7-91ec-40c1-b66f-aa9a59e2c95a", 
    "eb4f6f09-d9fc-4c77-84f7-3151fe8a0a4f", "db87caea-44ca-4925-adb6-8d1146f66d0f", 
    "465749f5-eb83-48c5-872a-ca153b4733cd", "484f638a-05ca-41e6-9f09-81bf32def4fd", 
    "09b60adc-8e05-4b38-99ea-e408c9b2f57d", "4a6656da-192f-4c31-91fd-7c16acda229e", 
    "581557da-62da-4886-ab80-492377729326", "5905306b-8231-41fd-803c-5b568be1c5c6", 
    "6a93c57c-1a97-45e8-abdb-844cf91a527c", "97d16610-3827-4c9a-af25-eb6141104ea9", 
    "1288d22b-a03b-4356-9f58-c418bc0c367d", "1d86880e-1cf5-42a6-9871-d2f50d82246e", 
    "d9101e52-bd5d-454d-8347-da1efe5dd583", "752ddb91-8d6d-4a7a-b025-9ec5e01c4b98", 
    "e0f8b2db-8550-46c9-9b70-3d5f844ea4d7", "296f4c0f-2b8e-4c25-a2b4-f9129b38663b", 
    "37ef9ea5-719e-4ccb-90df-d6846c2a8170", "82dc0e63-404b-454b-a8d9-a0f53a8d9d37", 
    "db261741-b8e9-478e-b0fe-54bd3fa4ac3c", "e2a40333-a6c2-4f6e-908b-1a122266c070", 
    "3b1280a3-b3f7-4eca-a8c2-1bfc3e6c3b49", "85ae28a7-2087-40a8-a80a-489a84f939fa", 
    "8682e6ef-bb4a-4e2b-8bb3-aad03af25868", "63105f93-0b40-43cb-92d9-5d24ab50e3ab", 
    "8e4889b4-dfd4-4cb1-9a18-b767999cf5cc", "95592ada-d076-4288-8a85-fca7cd6d5200", 
    "ad52586e-a050-46ef-ac95-feac4e710d95", "04bbef40-2aac-41fd-8068-9490ca3db579", 
    "e9d46e41-fee7-42e5-b345-f48bafdf723b", "c7e1649b-cbe1-4c57-bc4c-ae58866643aa", 
    "6c98acf1-05ce-4759-9ec2-1ce86913deb2", "10b329cf-f731-49db-a696-26875722fdb6", 
    "6fe123a5-ad4f-4cc0-87e8-9d9890e9dde7", "fa6626c0-4972-45e9-b456-6a3deb114311", 
    "d5b3ca41-e991-446f-8498-68fee994210e", "fe2bdf8b-8e59-4592-917b-0d248f4af16b", 
    "ed25106a-d8ff-4a2d-9e41-e73c7af02036", "9b4da1fe-56b6-444a-8026-d5a42cf76e57", 
    "f2529d40-a05f-43e0-8def-6cf797322fa0", "a8173ee0-cd1a-44e0-a3eb-b657662626c5", 
    "f913bdf4-296e-4fef-b52f-cba3427f78fc", "fa014ae3-fd1c-4d22-a694-ed152f1bcd50", 
    "adb25759-ae12-4708-89aa-1a1a44c0b6c1", "b086a147-38e7-4aa4-babe-2643000e1559", 
    "5a115edf-3586-4d99-973b-624f0158828e", "d4b491ed-0532-44ff-8943-9d98f09777a6", 
    "d2e903c6-ec9a-4a10-a32e-8d99b1660180", "1d8ab63b-d694-4464-bd2a-85f45f143d42", 
    "1d4eebe7-d76b-45be-885d-f037a886f3e7", "1e83615f-609c-4093-aafd-d828fda7fb12", 
    "d46823b8-a03d-4243-b9f6-88a9eb5b419b", "3c4dae6e-e445-40b9-9f6f-59f1150926fc", 
    "133c8d71-541c-462a-b879-b921376eee63", "5432b93e-e0e0-4441-910e-8e775e3ee787", 
    "910fdac3-7545-490b-a1dc-cafa8190ae1a", "958e1315-a636-4b6e-8353-d356628e2925", 
    "47ad3665-f9d1-470d-bec9-94677f879c3a", "4bf7e5c7-193e-4059-a222-9271bc556796", 
    "d7a5e579-11f5-4a4b-acb5-1bbea5655c83", "e37ea5d6-36f5-48a3-ae45-1f3ef585bbc6", 
    "e9a13133-76ac-40b3-b2e3-3eca8187b31a", "36208e55-f10d-4fdb-be5e-de3e505dc796", 
    "3d872842-646a-4d78-86be-44691ba61ac7", "b3de9407-0e1e-4433-a1fd-bfa79221af0f", 
    "4b8c48d4-b520-4ef0-934f-32b8e29c6112", "5239aa16-642a-4fdd-bcc0-095e76ec3bfe", 
    "5938aa04-5083-4e2c-9fb3-5c2c33e9d7df", "67c105dd-f0d8-4835-b60c-5bb287aa0244", 
    "6c087711-cd0c-4327-bd89-e469ecf08f3d", "765370d4-b4e7-40af-a451-23143b0fc55a", 
    "249d69c8-6f12-4191-8ffc-5af5d4ffff60", "f4408d31-f802-4596-991b-d5f1ff3618de", 
    "7a194b49-c0ac-49e1-9a08-b8dcee7aaaf8", "db723c0f-b04d-460e-83f2-273ec23b42c1", 
    "849d0e64-ae0c-45fb-a35e-a38962b44c2a", "8c7fd2e8-eb55-4c11-ba4f-89bd967d4e06", 
    "905a1b60-ea40-423f-a823-7d169e3746ed", "0275e867-d8de-4311-a4bb-8c95ad51b6fe", 
    "08a30979-1e61-4605-8e8b-176594ba2dae", "21c1a46c-118d-4378-ad54-2f3bbc9d03f7", 
    "2ad3bda7-7b1a-4032-b2cd-06999e7006c5", "2c7c2210-757c-4311-8a74-fc34787d29f9", 
    "afe9a0b9-ad0a-43c2-9016-5f577df063fb", "993ee63e-140c-4ba8-bd28-cf5a97b5f881", 
    "b8b7714b-db90-4c12-b519-9486d269ed9b", "67b7bbf8-17bb-445a-8ec1-fb91a15c9df6", 
    "f0b62c15-7cf6-4095-ab55-da9b72b5d100", "61c21e6e-4a9f-4e7c-bb25-7d8af39c362d", 
    "c1a54e47-47f1-4920-adf7-257b2fbea204", "0010bed5-f967-4e0a-95f6-7c91c462568b", 
    "0de3b44c-1069-4a87-9d22-cb8c7038cd8b", "f537d7b7-3809-44ec-be50-86032206235f", 
    "fedd71a3-e5c6-420e-b1ef-44e4b2fb5a0a", "8783cde7-a987-40b9-88ec-3b20cf537b57", 
    "3aef5302-789b-4933-8df0-fef7a7d9e58c", "0b4f5847-af58-49be-a5d1-a4e217570982", 
    "f40348bc-c8a9-4d72-9c9c-52a248a0c65d", "e7a8ad07-21ef-42c4-80ba-7b326737ae65", 
    "38c4ab46-9d35-48df-bfdf-376d5d1763ca", "5993edf6-d873-4468-b5f4-7ce669a25a4e", 
    "59cecab9-b981-4129-92db-864f5dc80d74", "59babfe6-186e-430b-b9c9-0bf4eddabe20", 
    "38819dd1-fdf4-4566-b130-59dad7e2caa6", "72a9714c-87bd-4625-a2e9-9b592bb89d65", 
    "88e73482-3456-4804-8314-19f43fefd58e", "9096e700-0f3d-4633-a4ac-7d3b7fa808db", 
    "95463c6a-d407-42ae-95aa-e3681da07188", "93e59895-b21a-4c48-b889-3dc3abbe9e23", 
    "4a1b6c54-8e28-4ea2-8c0e-9fa4aa9b4fd0", "06e8c4d8-17e1-442d-ba69-253add3fd25b", 
    "70192cda-ff83-43d4-907f-0d59e35a3bd7", "6e6e58f0-5e4f-4478-8c53-70fc5f9c8f9b", 
    "9220289a-7fe9-4024-8fc0-901d4e0b3c10", "715fe749-17b9-41a6-a2da-d2419326b8a7", 
    "6dbb8b36-3654-49f4-a42b-465171c7b7c3", "0baa888a-d262-45ab-9630-946c369a10d2", 
    "1f7e3837-72fb-4a1c-b404-0a80181f05b2", "a1c0c4fe-6cf9-4b53-8225-c79da5681406", 
    "1fff2886-5e0b-4e75-a788-7bc469cb3f48", "81975d2e-b64f-4aa8-bcb5-d7033e9a59e3", 
    "534ebece-8e52-4ec3-aa76-3d49da788dcc", "85a73616-388d-4ced-94bf-49f925cf3184", 
    "6bd3a451-6300-4501-a595-e4aec648d5c4", "a73d4bd7-c541-457a-81e8-f90450a27d7a", 
    "ad218bd2-5067-455c-8a8a-251e24b98999", "8dfbb123-521d-4d5e-8aef-b4386c646121", 
    "bb06c331-6d75-4a95-a381-6342548bfb5c", "0cde13bb-e7b4-4eeb-a66e-ec2ccdb603fb", 
    "26783e2f-2d17-46f5-b5c0-056013178f10", "6bf849c1-961a-4485-a775-5a03c1ec149c", 
    "92351fce-6291-48b5-a458-6369e4ae4e16", "c38d23f7-6277-429b-be01-259136f49005", 
    "cd39acb5-1194-41b4-b9ce-09822ada8bce", "1c5a45c6-bd6b-4449-ada6-320b9e76ca80", 
    "2c714c4d-0ef1-4f76-8335-3684479ca945", "e1babc7f-bd21-414f-a02b-971af5f76ea3", 
    "ed6565c4-18aa-43f4-8e85-978b78cdd6e4", "fcf9770a-4c3e-46d4-b63f-770963a6a53d", 
    "4b3e4d29-b2d2-467b-a641-fcf5163df74e", "4ecd9850-6ae9-435b-978a-723778c6241c", 
    "4ecdcd9c-e932-4222-a9e3-4f233b52681f", "506dace6-e600-4e28-b179-5be160eb113b", 
    "6db91307-58ca-4c8b-aaeb-53831a02db7e", "9b7a2f53-2a78-43b1-98bd-79b8fec81f2d", 
    "aa1ace12-01e2-41bf-a333-553ec107895a", "b27ed2f6-cf52-4b00-ae55-d133494c5faf", 
    "f37fcfe9-b810-4011-a02e-9b9c9fe13a0c", "2bf57fcc-0328-4df0-a4cc-8d1ca450407f", 
    "0ef531ff-3c60-4544-b60b-03ebf648e428", "f591bf28-3e9a-4cf8-ba77-1ba3eaac3ccc", 
    "0b55c62f-2876-413e-b693-bd8ea756c55d", "20c84da1-9681-48e8-829f-7c6cf05676a7", 
    "2982b40b-6e0b-46a6-9857-db199361a770", "4fd3ec54-c519-460f-ba2b-3977fc93ae1d", 
    "64498a52-b5f7-4699-b102-4ad9bfb49479", "83d2fe25-0599-484d-906e-7b4e1f39de48", 
    "965fa4c1-6c0a-4820-a668-7d0b8994d2d2", "ec705d86-8181-45da-ab30-8204a0a21006", 
    "9e946c0a-ccc4-4d0a-84b2-31e0a349bfac", "dacba9de-9e96-400f-ae33-38142dc825f0", 
    "308e2a8c-7123-4f49-ae18-98b310d1a585", "f2972e7d-0c74-45f5-97b6-9d54dc4754eb", 
    "5c97175d-dab8-4054-823d-b49016539495", "6236a818-76d6-4345-bde4-d27e0509831e", 
    "44edba48-8787-4ecf-b535-601dec20de7e", "431777cd-fd5c-4d5c-816b-eb99c8bc9bb0", 
    "ff4156a3-52c9-45bb-b2b2-133a7b80b603", "4670a753-eac1-4d1b-908d-d61aeba6dcf6", 
    "4dbe7a55-04c6-4849-a7cc-1719b9957db8", "6b9f24d8-bc74-40fe-acb8-bc1326651e29", 
    "bd0c3d2f-4ba8-4de6-b904-5468ae2592b3", "92f03bcc-21e2-4d10-8357-80e24e00f3e0", 
    "ed475285-2300-433f-9ae3-5beddf0dff83", "4e5c81f9-9813-4541-b94f-c580d8dfd448", 
    "e238034a-4fec-43ef-b70b-5c9f3981a159", "07efa84d-16b1-443f-8d44-8255967b911c", 
    "4a67aac6-668c-4ea5-b085-3bc2c0af5db3", "2d09d7be-0941-4e39-a57a-397ef1085dbe", 
    "6db0115a-470c-419d-8cda-f6b228834094", "3d92b19e-75f4-4fab-982a-dfd8e474fa15", 
    "709bc1b9-5342-4adc-890f-bb608608df78", "9a44cede-abe2-4141-b7b8-e841c4e23461", 
    "9af256c2-c8c8-4688-8bc8-1a75fb01ab8c", "b146c319-2b64-489c-9481-c664aefbda30", 
    "b7fcddf4-c77d-43d0-943d-9c410fcbfb24", "8917b9af-debe-4909-9cf8-d75650a51ebd", 
    "aa8c21ef-6b18-4a11-b575-12f01de5d514", "c9724eb7-e6a7-478e-8ef3-a48857d3b40b", 
    "cd15aa38-762c-4be5-96ff-569bdd9c3f10", "e78e0b18-844c-4a52-8b7f-1980188f3452", 
    "0866c8b6-2fbc-41cd-b588-7d79bae7005f", "31992cab-0f3c-471b-9455-940d55b625c3", 
    "61fe4dcb-c853-4e56-8d17-a4ded4f83606", "7d98804c-a402-420f-9acd-fecaf7082d1a", 
    "e969f459-9b5e-488b-852e-c973d9a1ff23", "f1138f06-d402-4bbd-8601-ea4a610a4565", 
    "6e549a76-9d9e-444d-b52e-f5c78770d597", "2db19696-4491-4987-a040-c4f9d4dcd008", 
    "4b9ebcef-861d-4061-9876-fd1f9479bfac", "aea5c3a0-4c85-4068-8de2-a8e29cfcded3", 
    "27330ad0-9dba-4781-8f9f-99528ee6dc74", "e07d50a1-34e1-45ba-a6cb-3e21fa362367", 
    "e8042c5f-f6d2-47f6-bb49-6f4dd8627b3e", "f75f01e7-0b77-4738-96ac-5515d8c41a3c", 
    "79924731-9399-4425-825a-d68fbb13ae67", "11802bd3-35e6-40e2-a069-5b5054382834", 
    "2c8dd2c2-c3fa-4d94-9d3f-cb817d0dcf5c", "705fdc9a-e580-4ae2-a3aa-086088614929", 
    "8692c770-cd72-4241-90c5-2a728bc741b9", "88c89333-c429-4228-bd16-cc13fffa68eb", 
    "08b7bda3-0785-47ce-b4d2-ad515c6275d8", "e10b1439-9f98-4074-ab49-f5266a9b7e14", 
    "e4fad91c-1fa9-4881-ac65-127e595b93d1", "e9f40c43-89c0-4488-a6b5-cbc719e7b9c3", 
    "fcf585f8-d28f-4e08-adf1-8442c813b56b", "e8f9a12a-e982-4056-a242-24120e34c70c", 
    "15d22b44-e41d-4ed9-b7fb-48df629874ca", "301bada0-e3f6-48be-ac22-8dba189f4d69", 
    "3e133976-0f34-4da4-831f-3f4634880af9", "13c550f9-a233-4732-981b-a194ffe17346", 
    "6481ca7d-1510-4bca-bfa6-38e91f2b3521", "a0198ffd-0ac6-41a1-85c0-a1ee46d3e5aa", 
    "cfe4a509-9766-4d47-9abf-353a1cac80b6", "d0e4a896-b965-40ca-b67c-3b0933b21b08", 
    "db6fa396-d3f0-49b6-bd82-5422ec78276f", "1d8b4aea-9b82-4872-9bc8-cd6c4c8f1658", 
    "2584b85f-7542-486f-8e37-3cb1072bc1ff", "73545e38-4360-407a-8ef8-8b89b61a12b3", 
    "544843d1-60b4-4814-83e6-5825861104f4", "7dca5718-776c-4e2e-bcc1-0d1316074edd", 
    "82c6be74-36d0-4dd2-8b4e-e92234cfeaaf", "9cf02b00-a61d-4e55-9fd9-9c30132df1f1", 
    "d519ee66-9cfe-4753-8cdf-2cd1d9c61199", "f755f2d9-e4e9-408a-8067-a8cc3a697cbb"
]

# with ThreadPoolExecutor(max_workers=5) as executor:
#     futures = {executor.submit(regenerate_cover_art, tid): tid for tid in PROD_IDS}
#     for future in as_completed(futures):
#         template_id = futures[future]
#         try:
#             future.result()
#             print(f"Cover art done for {template_id}")
#         except Exception as e:
#             print(f"Failed cover art for {template_id}: {e}")


def process_variation(variation: dict) -> str:
    """Process one variation end-to-end: story prompts, visual tag, create template, panels, cover art."""
    variation_prompt = (
        f"Title: {variation['title']}\n"
        f"Blurb: {variation['blurb']}\n"
        f"Questions: {variation['questions']}"
    )

    # Step 1: generate story prompts
    story_prompts = generate_story_prompts(variation_prompt)

    # Step 2: pick random visual tag
    visual_tag_id = random.choice(list(VISUAL_TAGS.keys()))

    # Step 3: create template in backend
    parameters = [
        {"name": q, "type": "image", "required": True, "position": j}
        for j, q in enumerate(variation["questions"])
    ]
    config = {
        "version": 4,
        "num_panels": len(story_prompts),
        "system_prompt": "Create the following scene in a {aesthetic} style:\n\n",
        "parameters": [
            {
                "referrer": "{" + q.lower().replace(" ", "_").replace("?", "") + "}",
                "type": "image",
                "name": q,
                "position": j,
                "required": True,
            }
            for j, q in enumerate(variation["questions"])
        ],
        "prompts": [
            {"position": str(j), "prompt": prompt}
            for j, prompt in enumerate(story_prompts)
        ],
    }
    result = create_gift_template(
        variation["title"],
        blurb=variation["blurb"],
        tag_ids=[visual_tag_id],
        parameters=parameters,
        config=config,
    )
    template_id = result["data"]["id"]
    print(f"Created template {template_id} for '{variation['title']}'")

    # Step 4: regenerate panel previews
    regenerate_template_previews(template_id)
    print(f"Regenerated panels for {template_id}")

    # Step 5: generate cover art (depends on panels from step 4)
    regenerate_cover_art(template_id)
    print(f"Cover art done for {template_id}")

    return template_id

def create_single_template(template: dict) -> str:
    """Create a single template end-to-end: story prompts, create in backend, panels, cover art.
    template should have: title, blurb, questions."""
    return process_variation(template)

def create_templates_full(greeting_card: dict) -> list[str]:
    # Sequential: generate all variations at once (single LLM call)
    prompt = (
        f"Title: {greeting_card['title']}\n"
        f"Blurb: {greeting_card['blurb']}\n"
        f"Questions: {greeting_card['questions']}"
    )
    raw_response = generate_template_variation(prompt)
    variations = parse_variations(raw_response)
    print(f"Generated {len(variations)} variations")

    # Parallel: process each variation end-to-end, concurrency 5
    template_ids = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(process_variation, variation): i
            for i, variation in enumerate(variations)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                tid = future.result()
                template_ids.append(tid)
                print(f"Done variation {idx}: {tid}")
            except Exception as e:
                print(f"Failed variation {idx}: {e}")

    return template_ids

# create_templates_full({
#     "title": "Wedding Congratulations",
#     "blurb": "Celebrate the newlyweds on their special day.",
#     "questions": [
#         "Photo of the groom?",
#         "Photo of bride?",
#     ]
# })

BIRTHDAY_TEMPLATE_IDS = [
    "0866c8b6-2fbc-41cd-b588-7d79bae7005f",  # Happy Birthday to Grandpa!
    "20c84da1-9681-48e8-829f-7c6cf05676a7",  # Happy Birthday to Grandma!
    "61fe4dcb-c853-4e56-8d17-a4ded4f83606",  # Happy Birthday to Dad!
    "07efa84d-16b1-443f-8d44-8255967b911c",  # Happy Birthday to Mom!
    "4fd3ec54-c519-460f-ba2b-3977fc93ae1d",  # Happy Birthday to My Best Friend
    "4b9ebcef-861d-4061-9876-fd1f9479bfac",  # Hot Sauce Birthday
    "f1138f06-d402-4bbd-8601-ea4a610a4565",  # Retro Diner Birthday
    "26783e2f-2d17-46f5-b5c0-056013178f10",  # Stargazing Birthday
    "6db91307-58ca-4c8b-aaeb-53831a02db7e",  # Treehouse Adventure Birthday
    "4670a753-eac1-4d1b-908d-d61aeba6dcf6",  # Coquette Bow Birthday
    "0baa888a-d262-45ab-9630-946c369a10d2",  # Movie Marathon Birthday
    "9af256c2-c8c8-4688-8bc8-1a75fb01ab8c",  # Lana Del Rey Birthday
    "2d09d7be-0941-4e39-a57a-397ef1085dbe",  # Snowboarding Birthday
    "308e2a8c-7123-4f49-ae18-98b310d1a585",  # Ramen Bowl Birthday
    "85a73616-388d-4ced-94bf-49f925cf3184",  # Champagne Pop Birthday
    "bb06c331-6d75-4a95-a381-6342548bfb5c",  # Sunflower Field Birthday
    "6bf849c1-961a-4485-a775-5a03c1ec149c",  # Pottery Wheel Birthday
    "506dace6-e600-4e28-b179-5be160eb113b",  # K-Pop Stan Birthday
    "4ecdcd9c-e932-4222-a9e3-4f233b52681f",  # Festival Wristband Birthday
    "1fff2886-5e0b-4e75-a788-7bc469cb3f48",  # Pickleball Birthday
    "4ecd9850-6ae9-435b-978a-723778c6241c",  # Cherry Blossom Birthday
    "e1babc7f-bd21-414f-a02b-971af5f76ea3",  # Astro Boy Birthday
    "e238034a-4fec-43ef-b70b-5c9f3981a159",  # Vinyl Records Birthday
    "92351fce-6291-48b5-a458-6369e4ae4e16",  # Roller Coaster Birthday
    "6b9f24d8-bc74-40fe-acb8-bc1326651e29",  # Confetti Cannon Birthday
    "534ebece-8e52-4ec3-aa76-3d49da788dcc",  # Balloon Dog Birthday
    "aa1ace12-01e2-41bf-a333-553ec107895a",  # Yoga & Zen Birthday
    "83d2fe25-0599-484d-906e-7b4e1f39de48",  # True Crime Obsessed Birthday
    "64498a52-b5f7-4699-b102-4ad9bfb49479",  # Drag Brunch Birthday
    "c38d23f7-6277-429b-be01-259136f49005",  # Golf Course Birthday
    "910fdac3-7545-490b-a1dc-cafa8190ae1a",  # Fishing Trip Birthday
    "544843d1-60b4-4814-83e6-5825861104f4",  # Eras Tour Birthday
    "993ee63e-140c-4ba8-bd28-cf5a97b5f881",  # Matcha Latte Birthday
    "08a30979-1e61-4605-8e8b-176594ba2dae",  # Swiftie Friendship Bracelet Birthday
    "9b4da1fe-56b6-444a-8026-d5a42cf76e57",  # Passport Stamp Birthday
    "765370d4-b4e7-40af-a451-23143b0fc55a",  # Chef's Kiss Birthday
    "67c105dd-f0d8-4835-b60c-5bb287aa0244",  # Puppy Paw-ty Birthday
    "e9a13133-76ac-40b3-b2e3-3eca8187b31a",  # Dancing Queen Birthday
    "8c7fd2e8-eb55-4c11-ba4f-89bd967d4e06",  # Charcuterie Board Birthday
    "7a194b49-c0ac-49e1-9a08-b8dcee7aaaf8",  # Sneakerhead Birthday
    "3d872842-646a-4d78-86be-44691ba61ac7",  # Avocado Toast Birthday
    "36208e55-f10d-4fdb-be5e-de3e505dc796",  # Fairy Enchanted Birthday
    "db723c0f-b04d-460e-83f2-273ec23b42c1",  # Soccer Pitch Birthday
    "0275e867-d8de-4311-a4bb-8c95ad51b6fe",  # Boba Tea Birthday
    "5432b93e-e0e0-4441-910e-8e775e3ee787",  # Witch & Wizard Birthday
    "13c550f9-a233-4732-981b-a194ffe17346",  # Neon Glow Party Birthday
    "d7a5e579-11f5-4a4b-acb5-1bbea5655c83",  # Spa Day Birthday
    "249d69c8-6f12-4191-8ffc-5af5d4ffff60",  # Lego Builder Birthday
    "ed25106a-d8ff-4a2d-9e41-e73c7af02036",  # Garden Tea Party Birthday
    "adb25759-ae12-4708-89aa-1a1a44c0b6c1",  # Race Car Birthday
    "21c1a46c-118d-4378-ad54-2f3bbc9d03f7",  # Tennis Court Birthday
    "fe2bdf8b-8e59-4592-917b-0d248f4af16b",  # Balloon Arch Birthday
    "a8173ee0-cd1a-44e0-a3eb-b657662626c5",  # Pirate Treasure Birthday
    "fa6626c0-4972-45e9-b456-6a3deb114311",  # Roller Skating Rink Birthday
    "296f4c0f-2b8e-4c25-a2b4-f9129b38663b",  # Baseball Diamond Birthday
    "ad52586e-a050-46ef-ac95-feac4e710d95",  # Karaoke Night Birthday
    "04bbef40-2aac-41fd-8068-9490ca3db579",  # Yarn & Knitting Birthday
    "2e71dad0-35ce-4826-877e-5f2991ed5595",  # Skater Boy Birthday
    "b7e98b90-3e5a-4db7-b1d5-3fe47c20daa4",  # Safari Adventure Birthday
    "ad1a5a98-40dc-41d4-b0f3-9d050ced27a8",  # Vintage Hollywood Birthday
    "3e5f512e-1b2b-4f66-a47e-890a72203c09",  # Camping Under the Stars Birthday
    "752ddb91-8d6d-4a7a-b025-9ec5e01c4b98",  # Harry Potter Birthday
    "1d86880e-1cf5-42a6-9871-d2f50d82246e",  # Ice Cream Sundae Birthday
    "90cb65f7-001d-497c-b57e-aa63c1c62a3b",  # Tropical Flamingo Birthday
    "97d16610-3827-4c9a-af25-eb6141104ea9",  # Groovy 70s Birthday
    "eb4f6f09-d9fc-4c77-84f7-3151fe8a0a4f",  # Fiesta Birthday
    "3aa8dfae-1d34-49b8-8f89-bcc0902f02d7",  # Construction Zone Birthday
    "e9f40c43-89c0-4488-a6b5-cbc719e7b9c3",  # Basketball Court Birthday
    "73545e38-4360-407a-8ef8-8b89b61a12b3",  # Hot Girl Birthday
    "60c4064f-5c84-43e1-977c-0d19bae3613e",  # Hiking Adventure Birthday
    "3bfd7a58-2e01-4a77-960a-fcaf0e6b3bfd",  # Butterfly Garden Birthday
    "2584b85f-7542-486f-8e37-3cb1072bc1ff",  # Retro 80s Birthday
    "de5371d5-0c56-4faa-acbc-b71f603c89a9",  # Wine & Cheese Birthday
    "a6a48c5a-ed1d-4c40-a54b-eff05a6c3e07",  # Superheroes Birthday
    "fc4deed7-8be3-41e2-9ac5-16319c79c5ab",  # Princess Themed Birthday
    "aa41775b-72c2-4535-9175-3fe160438e08",  # Surf's Up Birthday
    "a71c73d2-29f4-46fb-860b-e3399cba2dce",  # Coffee Addict Birthday
    "af0396c7-eaf6-4529-bb55-e823b3a41960",  # Unicorn Magic Birthday
    "09b60adc-8e05-4b38-99ea-e408c9b2f57d",  # Dog Dad Birthday
    "11576c28-1106-4005-9673-15b53e6833d5",  # Brunch-Obsessed Birthday
    "1700595f-3761-4f66-b38e-e411c496827e",  # Gamer Level-Up Birthday
    "bdc078c4-e6d4-40ea-9e84-50ca2026e11e",  # Cottagecore Birthday
    "9cf02b00-a61d-4e55-9fd9-9c30132df1f1",  # Gym Bro Birthday
    "9c1b7ea2-87b6-420e-b73f-22332aa12e86",  # Taylor Swift Era Birthday
    "5905306b-8231-41fd-803c-5b568be1c5c6",  # Bookworm Birthday
    "e97f7823-ea24-4905-9905-e44177f7aba6",  # Sushi Rolling Into Another Year
    "db87caea-44ca-4925-adb6-8d1146f66d0f",  # Cowboy Birthday Hoedown
    "1d8b4aea-9b82-4872-9bc8-cd6c4c8f1658",  # Barbie-Themed Birthday
    "3cb650a9-d84f-4509-8a5a-e4376630b824",  # Space Explorer Birthday
    "b6ef2ff5-e398-4aa2-af85-76d33301cb27",  # Pizza Party Birthday
    "567050ac-f574-4765-ac57-e7f792fea647",  # Plant Parent Birthday
    "c6885bc0-0a3e-47a8-ac86-4c6196be7e4b",  # Golden Retriever Energy Birthday
    "69e9ce36-2420-43b5-9bdd-76531244638c",  # Astrology-Obsessed Birthday
    "29d58290-aa49-4c87-b0cf-822588447381",  # Football Themed Birthday
    "fcc7d063-9905-4d82-95b0-7d4592816c32",  # Disco Ball Birthday Bash
    "cf8d0f36-d1dc-49ad-902d-eae9cf57aef6",  # Taco 'Bout a Birthday (doc 2)
    "2dcbe4a1-2012-43e8-a4ca-a94882d0df97",  # Dinosaur Themed Birthday
    "d5756ccb-eeeb-4fab-b7a3-9eaa895f40e0",  # Mermaid Birthday Splash
    "f60a110d-d108-4d13-9cb9-544fefd0c967",  # Golden Hour Birthday
    "998b9a9b-1349-4ac2-8d7a-00e11f9b625f",  # Arcade Mode Birthday
    "5c7a4e24-c42b-4ba7-80c4-2466df2676d3",  # Espresso Yourself Birthday
    "c755f8f0-35e2-4a6f-82ac-c83868d0435b",  # Cottagecore Birthday Wishes
    "6a5ab22e-9afe-47f0-ba68-00f591038dd0",  # Space Explorer Birthday (doc 2)
    "ca1a03aa-717f-4127-9ca8-8458414896c7",  # Vintage Hollywood Birthday (doc 2)
    "8714daba-1ad2-42df-a399-c45f70de5b41",  # Plant Parent Birthday (doc 2)
    "0010bed5-f967-4e0a-95f6-7c91c462568b",  # Taco 'Bout a Birthday (doc 2 alt)
    "f537d7b7-3809-44ec-be50-86032206235f",  # Under the Sea Birthday
    "afe9a0b9-ad0a-43c2-9016-5f577df063fb",  # Disco Ball Birthday Bash (doc 2)
    "7d98804c-a402-420f-9acd-fecaf7082d1a",  # Fiesta Themed 30th Birthday
    "dd8bb77c-e0d5-44ce-94da-b36851e7700f",  # Sweet 16 Mamma Mia Themed Birthday
    "1865ec07-a30b-4baa-81fc-a5821d865123",  # Casamigos-Filled 21st Birthday
    "b837a44b-38b6-4727-a799-201f769ec709",  # Over The Hill 50th Birthday
    "d58f797b-ff13-4514-8f8d-5b67d54478a3",  # Little Princess Birthday
]

ASTORLOGY_TEMPLATE_IDS = [
    "0ef531ff-3c60-4544-b60b-03ebf648e428",
    "f2972e7d-0c74-45f5-97b6-9d54dc4754eb",
    "ed475285-2300-433f-9ae3-5beddf0dff83",
    "2bf57fcc-0328-4df0-a4cc-8d1ca450407f",
    "bd0c3d2f-4ba8-4de6-b904-5468ae2592b3",
    "92f03bcc-21e2-4d10-8357-80e24e00f3e0",
    "4e5c81f9-9813-4541-b94f-c580d8dfd448",
    "f591bf28-3e9a-4cf8-ba77-1ba3eaac3ccc",
    "0b55c62f-2876-413e-b693-bd8ea756c55d",
    "ec705d86-8181-45da-ab30-8204a0a21006"
]

ST_PATRICK_TEMPLATE_IDS = [
    "9a44cede-abe2-4141-b7b8-e841c4e23461",
    "5c97175d-dab8-4054-823d-b49016539495",
    "e8042c5f-f6d2-47f6-bb49-6f4dd8627b3e",
    "e07d50a1-34e1-45ba-a6cb-3e21fa362367",
    "aa8c21ef-6b18-4a11-b575-12f01de5d514",
    "431777cd-fd5c-4d5c-816b-eb99c8bc9bb0",
    "ff4156a3-52c9-45bb-b2b2-133a7b80b603",
    "b146c319-2b64-489c-9481-c664aefbda30",
    "4dbe7a55-04c6-4849-a7cc-1719b9957db8"
]

CONFESSIONS_TEMPLATE_IDS = [
    "0b831a85-7d16-4a43-a785-3a5a2062e722",
    "93b98849-47ca-4ed7-ae9f-4a078f859081",
    "3b4d6cf8-d567-4b49-993b-802f6b81de2c",
    "fb9fdc43-1af6-48ad-8500-2ecc03bce72f",
    "ce5c614f-5c6f-47ce-8fe7-71b186196fec",
    "82c6be74-36d0-4dd2-8b4e-e92234cfeaaf",
    "ed6565c4-18aa-43f4-8e85-978b78cdd6e4",
    "2c714c4d-0ef1-4f76-8335-3684479ca945",
    "f0b62c15-7cf6-4095-ab55-da9b72b5d100",
    "59cecab9-b981-4129-92db-864f5dc80d74",
    "8dfbb123-521d-4d5e-8aef-b4386c646121",
    "81975d2e-b64f-4aa8-bcb5-d7033e9a59e3",
    "0b4f5847-af58-49be-a5d1-a4e217570982",
    "715fe749-17b9-41a6-a2da-d2419326b8a7",
    "0cde13bb-e7b4-4eeb-a66e-ec2ccdb603fb",
    "6bd3a451-6300-4501-a595-e4aec648d5c4",
    "a73d4bd7-c541-457a-81e8-f90450a27d7a",
    "4b3e4d29-b2d2-467b-a641-fcf5163df74e",
    "fedd71a3-e5c6-420e-b1ef-44e4b2fb5a0a",
    "61c21e6e-4a9f-4e7c-bb25-7d8af39c362d"
]

ANNIVERSARY_TEMPLATE_IDS = [
    "f2529d40-a05f-43e0-8def-6cf797322fa0",
    "4bf7e5c7-193e-4059-a222-9271bc556796",
    "15d22b44-e41d-4ed9-b7fb-48df629874ca",
    "cb0ec69c-a637-4640-9fae-7b8f9af20a27",
    "f755f2d9-e4e9-408a-8067-a8cc3a697cbb",
    "570766d8-fc45-41ed-acb8-9f206029c700",
    "a6ec4f04-f094-41fc-a632-5a07c5dc5dde",
    "35a40ecb-ca95-49f2-b637-4b25c10fd85d",
    "c8f6388b-1fc7-4e67-a391-89dc3cac03cc",
    "6e0ad0da-8591-4b07-86ae-23ce4f9a6f06",
    "4e68c512-cfbc-4c6b-b411-307c6bd2da9d",
    "8cb5fc81-f71f-4bf5-b785-5774bdf02c18",
    "7d87264d-b076-488a-a162-85d51cc2e1bf",
    "407dee79-7d8f-4e7a-a2dc-4e819ce3738e",
    "eb32775f-33ac-4280-b004-36e723747721",
    "c51fd5fe-ddd8-4648-9061-c31e59bf9a10"
]

MISSING_YOU_TEMPLATE_IDS = [
    "72a9714c-87bd-4625-a2e9-9b592bb89d65", # Missing My Gym Partner
    "88e73482-3456-4804-8314-19f43fefd58e", # My World is Less Colorful
    "6dbb8b36-3654-49f4-a42b-465171c7b7c3", # You're My Anchor
    "67b7bbf8-17bb-445a-8ec1-fb91a15c9df6", # Can't Wait for Our Next Chapter
    "9096e700-0f3d-4633-a4ac-7d3b7fa808db", # In a Galaxy Far, Far Away
    "38c4ab46-9d35-48df-bfdf-376d5d1763ca", # Holidays Apart
    "3e133976-0f34-4da4-831f-3f4634880af9", # Sending a Bear Hug
    "f4408d31-f802-4596-991b-d5f1ff3618de", # Good Morning, Missing You
    "5938aa04-5083-4e2c-9fb3-5c2c33e9d7df", # My Missing Piece
    "4b8c48d4-b520-4ef0-934f-32b8e29c6112", # Just a Tuesday
    "88c89333-c429-4228-bd16-cc13fffa68eb", # Love You to the Moon and Back
    "cfe4a509-9766-4d47-9abf-353a1cac80b6", # Empty Side of the Bed
    "2c7c2210-757c-4311-8a74-fc34787d29f9", # A 'Pizza' My Heart
    "d0e4a896-b965-40ca-b67c-3b0933b21b08", # My Significant 'Otter'
    "8692c770-cd72-4241-90c5-2a728bc741b9", # Across The Globe
    "705fdc9a-e580-4ae2-a3aa-086088614929", # Player 2 Disconnected
    "e4fad91c-1fa9-4881-ac65-127e595b93d1", # Missing You a Latte
    "11802bd3-35e6-40e2-a069-5b5054382834", # Long Distance Love
    "e10b1439-9f98-4074-ab49-f5266a9b7e14"  # Counting Down the Days
]

INDIAN_WEDDINGS_TEMPLATE_IDS = [
    "6e6e58f0-5e4f-4478-8c53-70fc5f9c8f9b", # Reception Night Congratulations
    "3aef5302-789b-4933-8df0-fef7a7d9e58c", # Destination Indian Wedding Wishes
    "70192cda-ff83-43d4-907f-0d59e35a3bd7", # Sindoor & Mangalsutra Moment
    "8783cde7-a987-40b9-88ec-3b20cf537b57", # Indian Engagement Congratulations
    "cd39acb5-1194-41b4-b9ce-09822ada8bce", # Gujarati Wedding Congratulations
    "1f7e3837-72fb-4a1c-b404-0a80181f05b2", # Rajasthani Royal Wedding Wishes
    "1c5a45c6-bd6b-4449-ada6-320b9e76ca80", # Bengali Wedding Congratulations
    "c1a54e47-47f1-4920-adf7-257b2fbea204", # Punjabi Wedding Congratulations
    "fcf9770a-4c3e-46d4-b63f-770963a6a53d", # South Indian Wedding Congratulations
    "93e59895-b21a-4c48-b889-3dc3abbe9e23", # Haldi Ceremony Wishes
    "ad218bd2-5067-455c-8a8a-251e24b98999", # Saat Phere Blessings
    "38819dd1-fdf4-4566-b130-59dad7e2caa6", # Baraat Arrival Hype
    "59babfe6-186e-430b-b9c9-0bf4eddabe20", # Sangeet Night Congratulations
    "4a1b6c54-8e28-4ea2-8c0e-9fa4aa9b4fd0"  # Mehendi Ceremony Celebrations
]

WEDDING_TEMPLATE_IDS = [
    # Document 1 - Wedding templates
    "fb24603d-5336-4824-9404-9e17d2ddba06",  # The One Where They Get Married Congratulations
    "0cbe0dde-74d2-4f64-b291-307ba5f044b4",  # A Song of Ice and Fire Wedding Congratulations
    "5dcc247a-d047-42cf-8a7d-0b1384f7afa9",  # Our Office Romance Wedding Congratulations
    "089436a1-cb71-4609-b144-c2de0df5d5f9",  # One Ring to Rule Them All Wedding Congratulations
    "4d90f35b-4659-4e94-85b5-8530a7ba71ea",  # The Force is Strong Wedding Congratulations
    "a0198ffd-0ac6-41a1-85c0-a1ee46d3e5aa",  # A Magical Wedding Congratulations
    "e8f9a12a-e982-4056-a242-24120e34c70c",  # A Fairytale Wedding Congratulations
    "9220289a-7fe9-4024-8fc0-901d4e0b3c10",  # A New Year's Eve Wedding Congratulations
    "e2a40333-a6c2-4f6e-908b-1a122266c070",  # A Foodie Themed Wedding Congratulations
    "82dc0e63-404b-454b-a8d9-a0f53a8d9d37",  # A Steampunk Themed Wedding Congratulations
    "1288d22b-a03b-4356-9f58-c418bc0c367d",  # A Nightmare Before Christmas Wedding Congratulations
    "1d8ab63b-d694-4464-bd2a-85f45f143d42",  # A D&D Themed Wedding Congratulations
    "8e4889b4-dfd4-4cb1-9a18-b767999cf5cc",  # A Carnival Themed Wedding Congratulations
    "63105f93-0b40-43cb-92d9-5d24ab50e3ab",  # A Spring Floral Wedding Congratulations
    "c7e1649b-cbe1-4c57-bc4c-ae58866643aa",  # A Christmas Wedding Congratulations
    "1d4eebe7-d76b-45be-885d-f037a886f3e7",  # A Country Western Wedding Congratulations
    "133c8d71-541c-462a-b879-b921376eee63",  # A LEGO Themed Wedding Congratulations
    "e9d46e41-fee7-42e5-b345-f48bafdf723b",  # A Travel Themed Wedding Congratulations
    "d5b3ca41-e991-446f-8498-68fee994210e",  # An Under the Sea Wedding Congratulations
    "958e1315-a636-4b6e-8353-d356628e2925",  # A Groovy 70s Wedding Congratulations
    "5a115edf-3586-4d99-973b-624f0158828e",  # A Boho Chic Wedding Congratulations
    "f913bdf4-296e-4fef-b52f-cba3427f78fc",  # A Winter Wonderland Wedding Congratulations
    "8682e6ef-bb4a-4e2b-8bb3-aad03af25868",  # A Legend of Zelda Wedding Congratulations
    "d4b491ed-0532-44ff-8943-9d98f09777a6",  # An Animal Crossing Wedding Congratulations
    "60fc477a-ea25-4012-94eb-90749224644d",  # A Pokémon Themed Wedding Congratulations
    "ecf22a95-988e-48f8-a987-b89d9dc22cb5",  # A Friends Themed Wedding Congratulations
    "eeddb822-82e1-404f-8c1a-47111ceb4bcf",  # The Office Themed Wedding Congratulations
    "f1a4083b-75f7-4d66-850c-5d326a6920e7",  # A Shrek Themed Wedding Congratulations
    "ddcd1914-fd6a-4ee1-809d-73c1b4b1a05d",  # Lord of the Rings Wedding Congratulations
    "3a9e7745-f312-4938-a133-583da29d26ff",  # A Star Wars Themed Wedding Congratulations
    "fb84d7ca-5ae5-41f2-9121-2bc93622bd4c",  # A Harry Potter Themed Wedding Congratulations
    "f75f01e7-0b77-4738-96ac-5515d8c41a3c",  # Great Gatsby Themed Wedding Congratulations
    "6e549a76-9d9e-444d-b52e-f5c78770d597",  # Love Wins — LGBTQ+ Wedding Celebration
    "2982b40b-6e0b-46a6-9857-db199361a770",  # Wishing You a Harry Potter-Themed Wedding
    "b27ed2f6-cf52-4b00-ae55-d133494c5faf",  # Wishing You a Disney Fairytale Wedding
    "6e6e58f0-5e4f-4478-8c53-70fc5f9c8f9b",  # Reception Night Congratulations
    "3aef5302-789b-4933-8df0-fef7a7d9e58c",  # Destination Indian Wedding Wishes
    "70192cda-ff83-43d4-907f-0d59e35a3bd7",  # Sindoor & Mangalsutra Moment
    "8783cde7-a987-40b9-88ec-3b20cf537b57",  # Indian Engagement Congratulations
    "cd39acb5-1194-41b4-b9ce-09822ada8bce",  # Gujarati Wedding Congratulations
    "1f7e3837-72fb-4a1c-b404-0a80181f05b2",  # Rajasthani Royal Wedding Wishes
    "1c5a45c6-bd6b-4449-ada6-320b9e76ca80",  # Bengali Wedding Congratulations
    "c1a54e47-47f1-4920-adf7-257b2fbea204",  # Punjabi Wedding Congratulations
    "fcf9770a-4c3e-46d4-b63f-770963a6a53d",  # South Indian Wedding Congratulations
    "93e59895-b21a-4c48-b889-3dc3abbe9e23",  # Haldi Ceremony Wishes
    "ad218bd2-5067-455c-8a8a-251e24b98999",  # Saat Phere Blessings
    "38819dd1-fdf4-4566-b130-59dad7e2caa6",  # Baraat Arrival Hype
    "59babfe6-186e-430b-b9c9-0bf4eddabe20",  # Sangeet Night Congratulations
    "4a1b6c54-8e28-4ea2-8c0e-9fa4aa9b4fd0",  # Mehendi Ceremony Celebrations
    "e7a8ad07-21ef-42c4-80ba-7b326737ae65",  # Congrats to My Best Friend on Their Wedding
    "e37ea5d6-36f5-48a3-ae45-1f3ef585bbc6",  # Congrats to the Childhood Sweethearts Wedding
    "fa014ae3-fd1c-4d22-a694-ed152f1bcd50",  # Congrats to the College Sweethearts Wedding
    "1e83615f-609c-4093-aafd-d828fda7fb12",  # Congrats to the High School Sweethearts Wedding
    "6d2a34ad-561d-4baf-81f2-801af054d927",  # Congrats to the Dating App Couple Wedding
    "db261741-b8e9-478e-b0fe-54bd3fa4ac3c",  # Congrats to the Office Lovebirds Wedding
    "dff5bd41-4808-4210-ac48-defe5cd67336",  # Congrats to the Long-Distance Lovers Wedding
    "7df221c0-fa5f-43c5-a7da-632c49903331",  # Congrats to the Childhood Sweethearts Wedding (2)
    "79924731-9399-4425-825a-d68fbb13ae67",  # Congrats to the High School Sweethearts Wedding (2)
    "e511a3b6-b7b1-47b1-a6c3-41e3b077b114",  # College Sweethearts Tie the Knot
    # Document 2 - Wedding templates
    "d46823b8-a03d-4243-b9f6-88a9eb5b419b",  # A Boho Dream Wedding Congratulations
    "465749f5-eb83-48c5-872a-ca153b4733cd",  # A Winter Wonderland Wedding Congratulations
    "85b1cb4c-5100-4559-a725-bff904d98d9d",  # Everything is Awesome! LEGO Wedding Congratulations
    "9eec34fc-3b13-42f7-accd-252bee96d8ef",  # A Perfect Pairing Wedding Congratulations
    "cc18c509-32e5-489a-b7d7-2141c1c305da",  # Tying the Knot Wedding Congratulations
    "22a9d7ed-221f-41f3-82b4-639de99403c8",  # Viva Las Wedding! Congratulations
    "2caa6d91-fca8-48b7-8d5e-8a4ddb02e3ec",  # Our Greatest Adventure Wedding Congratulations
    "93d818d3-b934-4dfb-b3d8-6fc6ede0f699",  # A Paris-Themed Wedding Congratulations
    "cce726c7-48a5-4b8a-a204-a37d6cb41362",  # That's Amore! Italian Wedding Congratulations
    "b6f011a9-2504-4345-9eea-59537d84399a",  # Tropic-Like-It's-Hot Wedding Congratulations
    "2e0f891d-8bb9-4b02-943e-624492942031",  # Sugar, We're Goin' Down (The Aisle) Congratulations
    "1ec43965-65e9-4035-9f24-88013f8d6d20",  # Better Together Wedding Congratulations
    "18991d54-9285-4d52-8838-1a1ebaf2bc1a",  # Mamma Mia! Wedding Congratulations
    "da32102e-ef42-49c7-88e0-5f05bd2999f4",  # A Rock & Roll Wedding Congratulations
    "c8bd88c9-6b0f-4aa6-9e30-289c0946ce63",  # The Diamond of the Season Wedding Congratulations
    "0f7b8dba-37dc-4ecf-89dc-cb855cd3e506",  # A Sock Hop Wedding Congratulations
    "cf710551-1df4-42d6-a8a7-a5cc8059958b",  # A Totally '80s Wedding Congratulations
    "b7305fb8-b209-41e5-8708-9a0335775428",  # Disco Fever Wedding Congratulations
    "a23793e0-db41-49c3-bad8-9c5d96d9ba19",  # A Roaring Good Wedding Congratulations
    "d019555b-dd9c-4c41-8b19-e5409180830e",  # To Boldly Go Together Wedding Congratulations
    "1c3c6f58-6f71-4137-bd96-9a2aae8c88c6",  # Player 2 Has Joined! Wedding Congratulations
    "6e0d415f-443d-47d9-b6cf-b0f8a3e22774",  # A Timeless Love Wedding Congratulations
    "52c0db91-10e2-4beb-8ede-4bc788478a23",  # A Ghibli-esque Wedding Congratulations
    "684cdcb6-b700-46e0-9b4e-ae0979078844",  # I Choose You Forever! Wedding Congratulations
    "674a0956-87a2-40dd-ae30-cf412976d2b9",  # A Super-Powered Wedding Congratulations
]

# create_templates_full({
#     "title": "Good Luck on Your Exam!",
#     "blurb": "Send this to a friend who is taking an exam.",
#     "questions": [
#         "Photo of the exam taker?",
#         "Photo of yourself?",
#     ]
# })

# NOTE adding templates to a collection
# add_collection_items(
#     collection_id="10df10e1-04c3-447a-8038-17c9b9ec27ff",
#     gift_template_ids=WEDDING_TEMPLATE_IDS,
# )

# NOTE
# Birthdays
# Astrology
# Holidays
# Confessions
# Anniversaries
# Missing You
# Indian Weddings
# Weddings

# Global trending (TODO)
# India trending (TODO)

# TODO populate on create feed too

create_templates_full({
    "title": "Good Luck on Your Exam!",
    "blurb": "Send this to a friend who is taking an exam.",
    "questions": [
        "Photo of the exam taker?",
        "Photo of yourself?",
    ]
})