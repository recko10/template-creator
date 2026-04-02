import json
import os
import random
import re
from typing import Optional

import dotenv
import httpx

from generate_story_prompts import generate_story_prompts
from generate_template_variation import generate_template_variation
from riff_backend import add_templates, add_text_param, create_gift_template, get_gift_template, update_gift_template, regenerate_panels, generate_nanobanana, update_gift_template_image, backfill_gift_template_music
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
        timeout=60,
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

### NOTE BACKFILLING LOGIC
DEV_IDS = [
    "b92bb3dc-f0a7-4ed5-9f6f-d6efb39ab024",
    "8037e5d6-9fcc-482b-b553-15ff351d4089",
    "5ee302b3-6b03-4170-a97b-bdc57146bf09",
    "e2257306-fcbe-4327-b7db-4817c90f99b0",
    "a606d127-958f-4080-b1e5-157201395797",
    "28aa9f99-10b0-45b5-bab3-03265bca4b42",
    "cda2beef-625c-445e-a082-9ffe4fb16b26",
    "a90ba5d0-3872-48c4-93de-9a80409f0e21",
    "bc022a71-f441-490f-a444-cee6d71ca13e",
    "de1a23d2-fda7-441e-96e7-97a33563e611",
    "ca067b5d-ccb9-499b-a638-1e27dd89794d",
    "6728ae37-be2f-40bb-939d-c83515e077ad",
    "c2357d07-1de1-42d3-8bde-3290a9d0d936",
    "eba9279b-e06b-445f-928e-235ac9fcd10c",
    "3fed7d7d-eabd-4a81-b150-3338a2b09e63",
    "8c1044cd-539d-439f-9ca1-e2ee5fad27ac",
    "9d735d03-7a14-4ff7-a3d2-53b505d20ecc",
    "7205d750-3257-4720-ac3c-86cafda75964",
    "9285db81-fef4-46b7-a5c0-4a6f2faa83c9",
    "5ab23052-2d1c-4ed4-96be-b15cfac6a8fc",
    "4a05090a-da6d-48e6-b31c-f68431a67ae0",
    "2d043810-2894-4428-af0b-82fa65316d49",
    "e9d192c8-fc3a-45ce-8f34-72c8972fe271",
    "2272b101-abf0-44bd-8852-fa5650c59065",
    "0374ff2b-4632-499f-bc75-d9f66948a661",
    "514dfe79-c8fa-42fb-9e67-2995ebc42d56",
    "e7e6802c-3a67-420e-b3df-9ce7d14d093e",
    "6b469c10-fbf7-42ea-8b13-4f73e68fb014",
    "f9f790f2-f7b6-467c-b882-62a822165909",
    "6cc8227c-de12-44d7-9ec1-919f81d61a44",
    "7d129963-fa53-402a-b1d2-c6823a474588",
    "7e75c088-c2ff-4c01-90fe-4255ddec548e",
    "68474b55-891b-4e22-a9a2-95b9cbaebce8",
    "19943c40-5885-42f9-8361-0a9516f94722",
    "f81e108c-9e23-4a4f-8222-51d5bb11e432",
    "46d60202-2447-4022-b5e7-b9dfa76645f1",
    "8aa3086d-71dd-41b4-9b04-e336d7336bab",
    "f24bbff8-7bb3-499c-9bce-808df917ba1f",
    "4437301e-0314-4e03-aeb7-c276065461e7",
    "49f31466-9e09-4df7-9860-729dd020328d",
    "9b88bacc-d1a8-4fca-8ffc-71fb276fb86a",
    "2e750555-16d7-4afe-bbaa-10725a4d6494",
    "de9aec9a-2f4e-4647-9d3b-6196bc25fc28",
    "124dde4b-17e7-4fd4-8a9a-0ad3150a701c",
    "d93aa1ad-e838-47ae-9495-8be1dabe1815",
    "49abf12b-cda1-4f88-8c8e-a77f7ba5ba58",
    "0edf8632-3472-43ca-bcc6-62374a45696f",
    "84f84c70-fe98-48bc-a5ef-963b3958945a",
    "6fd9cd05-ccba-4c92-a5ee-30b9aa70e9ea",
    "eacf1ce8-5081-4e37-9e5a-1c273151f1d3",
    "444c866e-bc57-4e8f-ad7b-907a4eb4c2e1",
    "881b937e-2fc0-4816-836d-b459a023af26",
    "91aab674-f51a-4620-8cab-0de6cae7450a",
    "56917dc3-23cf-4591-9187-4f0f0c3c5d00",
    "878561bc-1439-4080-8083-bbca01d81e71",
    "5c7e596d-569b-45db-a835-1479d702e7d3",
    "f6bc8404-1726-427b-b71c-81b67664eb8d",
    "3210a429-faf4-4e41-9613-ea3a3001acfa",
    "8c61c9a5-37ae-4806-8a7e-80ad04eaf736",
    "5c7c5be7-0ba0-4c33-b6e4-bfedfc4df1c6",
    "7e7abf12-5bb3-4fda-ba4b-3cb0bc3fbdaf",
    "67d34bbf-a576-465f-9ab7-7056538176d5",
    "76870771-c2d2-4dac-8e61-134da436fe3b",
    "16311d6c-13ad-468b-b17a-92aa387babb8",
    "8c6ad4db-6bc4-4611-90db-e25fab888ef9",
    "3cbf1a98-24e8-4e77-9e09-b9f64b82d34d",
    "ef1d37e0-a631-4b83-8f17-326a8778bea9",
    "a9b728dd-96dc-43df-bd5e-8a8a68208e15",
    "d3de4048-858b-4010-979f-df6492ecf791",
    "6c396679-34df-4844-b7c1-a56e2096877e",
    "15f23df3-8401-447d-acff-89dab4e93a29",
    "ca535d54-df5a-4061-b2a2-acc8fd2620cb",
    "56e466c2-d099-452e-90e5-314960017d4d",
    "6c65507e-44f6-4842-a885-a4634348bc2d",
    "a388f9f1-c33e-4f47-9799-79a8b6d74703",
    "0a3f6e39-8e1f-4259-8688-185d98b8184b",
    "19879173-0011-476c-891d-4382740e11f8",
]

PROD_IDS = [
    "002958c4-d444-49c7-aa2e-cd20d7ea9fed",
    "06e8c4d8-17e1-442d-ba69-253add3fd25b",
    "0de3b44c-1069-4a87-9d22-cb8c7038cd8b",
    "10b329cf-f731-49db-a696-26875722fdb6",
    "1bf5115a-7986-4b39-8db0-51ba1617ed2a",
    "27330ad0-9dba-4781-8f9f-99528ee6dc74",
    "294440b9-41c3-4378-95fb-73aa4af435ce",
    "2a75fad1-ad8b-4b90-8a96-ababf2b077e6",
    "2ad3bda7-7b1a-4032-b2cd-06999e7006c5",
    "2b474138-4efe-490e-b4f6-68a7888c1bc3",
    "2c8dd2c2-c3fa-4d94-9d3f-cb817d0dcf5c",
    "2d07254b-6199-46ed-9ba7-6493e91ab0e8",
    "2db19696-4491-4987-a040-c4f9d4dcd008",
    "301bada0-e3f6-48be-ac22-8dba189f4d69",
    "315b70c0-671e-44df-abf7-c268a81470a5",
    "31992cab-0f3c-471b-9455-940d55b625c3",
    "36842f17-e74d-47fd-aa07-deb6e1eab221",
    "3b1280a3-b3f7-4eca-a8c2-1bfc3e6c3b49",
    "3c4dae6e-e445-40b9-9f6f-59f1150926fc",
    "3d92b19e-75f4-4fab-982a-dfd8e474fa15",
    "3f2c53d7-91ec-40c1-b66f-aa9a59e2c95a",
    "44edba48-8787-4ecf-b535-601dec20de7e",
    "4644d237-8db7-458e-9e22-771c725e14ec",
    "470de4d7-4d92-4f5f-8df4-318f735ef1de",
    "47ad3665-f9d1-470d-bec9-94677f879c3a",
    "484f638a-05ca-41e6-9f09-81bf32def4fd",
    "495b8f23-7a1b-481d-81af-b1bc7d0d511d",
    "4a6656da-192f-4c31-91fd-7c16acda229e",
    "4a67aac6-668c-4ea5-b085-3bc2c0af5db3",
    "4bfdfbfa-6a6c-47c9-a422-c7c78cee7f56",
    "5239aa16-642a-4fdd-bcc0-095e76ec3bfe",
    "5364ce06-45bb-4291-8162-ca0b27a26cfa",
    "581557da-62da-4886-ab80-492377729326",
    "583057d1-b049-417f-bba6-ef27bd00492e",
    "5993edf6-d873-4468-b5f4-7ce669a25a4e",
    "6236a818-76d6-4345-bde4-d27e0509831e",
    "6481ca7d-1510-4bca-bfa6-38e91f2b3521",
    "6a93c57c-1a97-45e8-abdb-844cf91a527c",
    "6c087711-cd0c-4327-bd89-e469ecf08f3d",
    "6c98acf1-05ce-4759-9ec2-1ce86913deb2",
    "6db0115a-470c-419d-8cda-f6b228834094",
    "6fe123a5-ad4f-4cc0-87e8-9d9890e9dde7",
    "709bc1b9-5342-4adc-890f-bb608608df78",
    "7b4dc997-7195-4bcf-8d39-557ed7d08918",
    "7dca5718-776c-4e2e-bcc1-0d1316074edd",
    "849d0e64-ae0c-45fb-a35e-a38962b44c2a",
    "85ae28a7-2087-40a8-a80a-489a84f939fa",
    "8917b9af-debe-4909-9cf8-d75650a51ebd",
    "8930250c-84d1-4cb0-aca6-e0ed9faa48d3",
    "8bfb4d08-bc54-428c-b581-e9e45a2b5aa4",
    "905a1b60-ea40-423f-a823-7d169e3746ed",
    "90869c84-b372-4615-8e01-e8237f515542",
    "93b6da56-97e2-4f79-8e3e-b34e84f4bb99",
    "95463c6a-d407-42ae-95aa-e3681da07188",
    "965fa4c1-6c0a-4820-a668-7d0b8994d2d2",
    "9b7a2f53-2a78-43b1-98bd-79b8fec81f2d",
    "9de28483-6306-4bca-aa1f-9d65083acb9b",
    "9e946c0a-ccc4-4d0a-84b2-31e0a349bfac",
    "a1c0c4fe-6cf9-4b53-8225-c79da5681406",
    "a2f4d8f1-13fc-48f5-ad24-0c7c1b1358b8",
    "a6c6ce1d-9bbe-49e4-b4f9-9e4567ec2854",
    "aea5c3a0-4c85-4068-8de2-a8e29cfcded3",
    "b086a147-38e7-4aa4-babe-2643000e1559",
    "b3de9407-0e1e-4433-a1fd-bfa79221af0f",
    "b7fcddf4-c77d-43d0-943d-9c410fcbfb24",
    "b8b7714b-db90-4c12-b519-9486d269ed9b",
    "b8f5c0be-e2d6-4600-a4c2-234afedcec2f",
    "c9724eb7-e6a7-478e-8ef3-a48857d3b40b",
    "cd15aa38-762c-4be5-96ff-569bdd9c3f10",
    "ce22819f-2392-4ab2-bed2-b69a326c0cce",
    "d2e903c6-ec9a-4a10-a32e-8d99b1660180",
    "d519ee66-9cfe-4753-8cdf-2cd1d9c61199",
    "d9101e52-bd5d-454d-8347-da1efe5dd583",
    "dacba9de-9e96-400f-ae33-38142dc825f0",
    "db6fa396-d3f0-49b6-bd82-5422ec78276f",
    "e0f8b2db-8550-46c9-9b70-3d5f844ea4d7",
    "e4d65df9-0795-4f06-a048-62ae4df3a8e0",
    "e59515b9-9f4e-420d-8bbb-3123a54f2015",
    "e78e0b18-844c-4a52-8b7f-1980188f3452",
    "e969f459-9b5e-488b-852e-c973d9a1ff23",
    "f1a3b1be-d5d4-4170-82bf-5b9eb6c4c357",
    "f40348bc-c8a9-4d72-9c9c-52a248a0c65d",
    "fcf585f8-d28f-4e08-adf1-8442c813b56b",
    "fe6c9dea-99ae-45f9-944c-146493a030d6",
    "fedf40eb-04a1-43f7-b761-ee22d2771a0d",
]

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
        "version": 3,
        "num_subjects": sum(1 for p in full["parameters"] if p["type"] == "image"),
        "num_panels": len(story_prompts),
        "system_prompt": "Create the following scene in a {aesthetic} style:",
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
    "grandma": "https://db.goriff.com/storage/v1/object/public/logo/aihuman/grandma.jpg",
    "grandpa": "https://db.goriff.com/storage/v1/object/public/logo/aihuman/grandpa.jpg",
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
        timeout=60,
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

def regenerate_template_previews(tid: str, *, extra_referrers: Optional[dict[str, str]] = None):
    full = get_gift_template(tid)["data"]
    visual_tags = [t for t in full.get("tags", []) if t["type"] == "visual"]
    if visual_tags:
        aesthetic = visual_tags[0]["system_prompt"] or visual_tags[0]["display_name"]
    else:
        aesthetic = "pixel art"

    questions = [p["name"] for p in full.get("parameters", [])]
    person_one_url, person_two_url = pick_person_images(full["name"], full["blurb"], questions)
    print(f"{full['name']}: person_one={person_one_url}, person_two={person_two_url}")

    # Build referrer map from config parameters
    config = full["config"]
    image_params = [p for p in config.get("parameters", []) if p["type"] == "image"]
    text_params = [p for p in config.get("parameters", []) if p["type"] == "text"]
    person_urls = [person_one_url, person_two_url]
    referrer_map = {"{aesthetic}": aesthetic}
    for i, img_param in enumerate(image_params):
        if i < len(person_urls):
            referrer_map[img_param["referrer"]] = person_urls[i]

    # Generate preview values for text params via LLM
    if text_params:
        text_preview_values = pick_preview_text(full["name"], full["blurb"], text_params)
        referrer_map.update(text_preview_values)

    if extra_referrers:
        referrer_map.update(extra_referrers)

    return regenerate_panels(tid, referrer_map=referrer_map)

def pick_preview_text(template_name: str, template_blurb: str, text_params: list[dict]) -> dict[str, str]:
    """Use an LLM to generate realistic preview values for text parameters."""
    params_desc = "\n".join(
        f"- referrer: {p['referrer']}, question: {p['name']}"
        + (f", description: {p['description']}" if p.get("description") else "")
        for p in text_params
    )
    prompt = (
        f"Template name: {template_name}\n"
        f"Blurb: {template_blurb}\n\n"
        f"Text parameters:\n{params_desc}\n\n"
        "For each text parameter, generate a short, realistic preview value that a real user might type in.\n"
        "Keep values concise (1-4 words). Make them feel natural and specific to the template's theme.\n\n"
        "Return JSON only, mapping each referrer to its preview value:\n"
        "{" + ", ".join(f'"{p["referrer"]}": "<value>"' for p in text_params) + "}"
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
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    print(f"Preview text for {template_name}: {content}")

    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    raw_json = json_match.group(1).strip() if json_match else content.strip()
    return json.loads(raw_json)

def pick_preview_name(template_name: str, template_blurb: str) -> str:
    """Use an LLM to pick a realistic first name based on the template's target person."""
    prompt = (
        f"Template name: {template_name}\n"
        f"Blurb: {template_blurb}\n\n"
        "Based on this greeting card template, pick a realistic first name for the person this card is directed to.\n\n"
        "Rules:\n"
        "- For elders and people you show respect to, include a respectful title:\n"
        "  - Grandpa/Grandma templates: return just 'Grandpa' or 'Grandma'\n"
        "  - Uncle/Aunt templates: return 'Uncle <name>' or 'Aunt <name>' (e.g. 'Uncle Robert')\n"
        "  - Dad/Mom templates: return just 'Dad' or 'Mom'\n"
        "  - Teacher/Boss/Mentor templates: return 'Mr. <name>' or 'Ms. <name>'\n"
        "- If the template targets a woman (e.g. 'for Her', 'for Wife'), pick a woman's name.\n"
        "- If the template targets a man (e.g. 'for Him', 'for Husband'), pick a man's name.\n"
        "- If the template targets a boy (e.g. 'for Son'), pick a boy's name.\n"
        "- If the template targets a girl (e.g. 'for Daughter'), pick a girl's name.\n"
        "- If the template is culturally Indian, pick an Indian name.\n"
        "- For generic templates (e.g. 'for Friend', 'for Colleague'), pick any common first name.\n\n"
        "Return ONLY the name (with title if applicable), nothing else."
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
        timeout=60,
    )
    response.raise_for_status()
    name = response.json()["choices"][0]["message"]["content"].strip().strip('"')
    print(f"Picked preview name for {template_name}: {name}")
    return name

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
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip().strip('"')

def regenerate_cover_art(gift_template_id: str) -> dict:
    full = get_gift_template(gift_template_id)["data"]

    refs = full.get("gift_template_references", [])
    image_refs = [r for r in refs if r.get("image_url")]
    if not image_refs:
        raise ValueError(f"No image references found for {gift_template_id}")
    panel_image_url = image_refs[min(7, len(image_refs) - 1)]["image_url"]

    short_name = shorten_template_name(full["name"])
    print(f"Shortened name: {full['name']} -> {short_name}")

    size = random.choice(["large"])
    # prompt = f'Add {size} text that reads "{short_name}" at the top of this image in a style that matches its aesthetic. The resulting image should not need to be exact — you must interweave the text in a natural way into the image so that it doesnt just feel like a title, but rather is woven thoughtfully. As a hard requirement, the text should never be blocked or covered by anything in the image.'
    prompt = f'Create a cohesive poster for a story called "{short_name}". Use the provided image as the main illustration and add poster text "{short_name}" in the approariate spot, blending in with the surrounding elements. The resulting image should not need to be exact — you must interweave the text in a natural way into the image so that it doesnt just feel like a title, but rather is woven thoughtfully. As a hard requirement, the text should never be blocked or covered by anything in the image.'
    print(f"Cover art for {full['name']}: using panel 8, prompt: {prompt}")

    result = generate_nanobanana(prompt, image_urls=[panel_image_url], aspect_ratio="3:4", model="nanobanana")
    print(f"Nanobanana result for {full['name']}: {result}")

    asset_id = result["data"]["asset_id"]
    update_result = update_gift_template_image(gift_template_id, asset_id)
    print(f"Updated cover art for {full['name']}")
    return update_result

def process_variation(variation: dict, param_types: dict[str, str] | None = None) -> str:
    """Process one variation end-to-end: story prompts, visual tag, create template, panels, cover art.

    param_types: optional dict mapping question name to type ("image" or "text"). Defaults to all "image".
    variation["questions"] can be either:
      - list of strings: ["Photo of yourself?", ...] — referrers auto-generated
      - list of dicts: [{"name": "...", "referrer": "{me}"}, ...] — referrers explicit
    """
    # Normalize questions to list of dicts with name + referrer
    questions = []
    for q in variation["questions"]:
        if isinstance(q, dict):
            questions.append(q)
        else:
            referrer = "{" + re.sub(r"[^a-z0-9]+", "_", q.lower()).strip("_") + "}"
            questions.append({"name": q, "referrer": referrer})

    if param_types is None:
        param_types = {}

    # Build prompt with referrer info for story generation
    prompt_lines = [
        f"Title: {variation['title']}",
        f"Blurb: {variation['blurb']}",
        "Parameters:",
    ]
    for q in questions:
        ptype = param_types.get(q["name"], "image")
        prompt_lines.append(f"- {q['name']} (type: {ptype}, referrer: {q['referrer']})")
    variation_prompt = "\n".join(prompt_lines)

    # Step 1: generate story prompts
    story_prompts = generate_story_prompts(variation_prompt)

    # Step 2: pick random visual tag
    visual_tag_id = random.choice(list(VISUAL_TAGS.keys()))

    # Step 3: create template in backend
    config_params = []
    for j, q in enumerate(questions):
        ptype = param_types.get(q["name"], "image")
        param = {
            "referrer": q["referrer"],
            "type": ptype,
            "name": q["name"],
            "position": j,
            "required": True,
        }
        config_params.append(param)

    parameters = [
        {"name": q["name"], "type": param_types.get(q["name"], "image"), "required": True, "position": j}
        for j, q in enumerate(questions)
    ]

    config = {
        "version": 4,
        "num_panels": len(story_prompts),
        "system_prompt": "Create the following scene in a {aesthetic} style:",
        "parameters": config_params,
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

# NOTE text param backfilling
def generate_text_params(gift_template_id: str) -> list[dict]:
    """Add 2 text params to a template: 'Their Name?' (first) and 'Write a personal message' (last)."""

    # "Their Name?" always first (position 0)
    result_1 = add_text_param(
        gift_template_id,
        name="Their Name?",
        referrer="{their_name}",
        position=0,
    )
    # "Write a personal message" always last
    result_2 = add_text_param(
        gift_template_id,
        name="Write a personal message",
        referrer="{personal_message}",
        description="Max 4 words",
    )

    return [result_1, result_2]

def regenerate_with_text_params(gift_template_id: str) -> dict:
    """End-to-end: add text params, regenerate story prompts with them, update config."""

    # Step 1: Add text params to the template (skip if already exist / 400)
    try:
        generate_text_params(gift_template_id)
        print(f"Added text params for {gift_template_id}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            print(f"Skipping text params for {gift_template_id} (400: likely already exist)")
        else:
            raise

    # Step 2: Re-fetch template (now has new text params) and regenerate story prompts
    full = get_gift_template(gift_template_id)["data"]
    config = full["config"]

    questions = [
        f"{p['name']} (referrer: {p['referrer']})" for p in full["parameters"]
    ]
    prompt = (
        f"Title: {full['name']}\n"
        f"Blurb: {full['blurb']}\n"
        f"Questions: {questions}\n\n"
    )
    print("Prompt:")
    print(prompt)
    print(f"Regenerating story prompts for: {full['name']}")

    story_prompts = generate_story_prompts(prompt)
    print(story_prompts)

    # Update prompts in-place on the fetched config
    config["num_panels"] = len(story_prompts)
    config["prompts"] = [
        {"position": str(j), "prompt": p}
        for j, p in enumerate(story_prompts)
    ]

    print("Config to send:")
    print(json.dumps(config, indent=2))

    result = update_gift_template(gift_template_id, config=config)
    print(f"Updated config for {gift_template_id}")

    # Step 3: Regenerate panels with text param values
    preview_name = pick_preview_name(full["name"], full["blurb"])
    regen_result = regenerate_template_previews(
        gift_template_id,
        extra_referrers={
            "{their_name}": preview_name,
            "{personal_message}": "Keep rocking!",
        },
    )
    print(f"Regenerated panels for {gift_template_id}")

    regenerate_cover_art(gift_template_id)
    print(f"Cover art done for {gift_template_id}")

    return regen_result

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

CONFESSION_TEMPLATE_IDS = [
    "61c21e6e-4a9f-4e7c-bb25-7d8af39c362d",
    "82c6be74-36d0-4dd2-8b4e-e92234cfeaaf",
    "3b4d6cf8-d567-4b49-993b-802f6b81de2c",
    "a73d4bd7-c541-457a-81e8-f90450a27d7a",
    "6bd3a451-6300-4501-a595-e4aec648d5c4",
    "ce5c614f-5c6f-47ce-8fe7-71b186196fec",
    "81975d2e-b64f-4aa8-bcb5-d7033e9a59e3",
    "8dfbb123-521d-4d5e-8aef-b4386c646121",
    "2c714c4d-0ef1-4f76-8335-3684479ca945",
    "4b3e4d29-b2d2-467b-a641-fcf5163df74e",
    "ed6565c4-18aa-43f4-8e85-978b78cdd6e4",
    "0cde13bb-e7b4-4eeb-a66e-ec2ccdb603fb",
    "715fe749-17b9-41a6-a2da-d2419326b8a7",
    "0b831a85-7d16-4a43-a785-3a5a2062e722",
    "93b98849-47ca-4ed7-ae9f-4a078f859081",
    "0b4f5847-af58-49be-a5d1-a4e217570982",
    "fb9fdc43-1af6-48ad-8500-2ecc03bce72f",
    "fedd71a3-e5c6-420e-b1ef-44e4b2fb5a0a",
    "f0b62c15-7cf6-4095-ab55-da9b72b5d100",
    "59cecab9-b981-4129-92db-864f5dc80d74",
]

MISSING_YOU_TEMPLATE_IDS = [
    "88e73482-3456-4804-8314-19f43fefd58e",
    "3e133976-0f34-4da4-831f-3f4634880af9",
    "38c4ab46-9d35-48df-bfdf-376d5d1763ca",
    "8692c770-cd72-4241-90c5-2a728bc741b9",
    "4b8c48d4-b520-4ef0-934f-32b8e29c6112",
    "f4408d31-f802-4596-991b-d5f1ff3618de",
    "e4fad91c-1fa9-4881-ac65-127e595b93d1",
    "5938aa04-5083-4e2c-9fb3-5c2c33e9d7df",
    "6dbb8b36-3654-49f4-a42b-465171c7b7c3",
    "88c89333-c429-4228-bd16-cc13fffa68eb",
    "72a9714c-87bd-4625-a2e9-9b592bb89d65",
    "cfe4a509-9766-4d47-9abf-353a1cac80b6",
    "d0e4a896-b965-40ca-b67c-3b0933b21b08",
    "9096e700-0f3d-4633-a4ac-7d3b7fa808db",
    "11802bd3-35e6-40e2-a069-5b5054382834",
    "e10b1439-9f98-4074-ab49-f5266a9b7e14",
    "2c7c2210-757c-4311-8a74-fc34787d29f9",
    "705fdc9a-e580-4ae2-a3aa-086088614929",
    "67b7bbf8-17bb-445a-8ec1-fb91a15c9df6",
]

ANNIVERSARIES_TEMPLATE_IDS = [
    "570766d8-fc45-41ed-acb8-9f206029c700",
    "a6ec4f04-f094-41fc-a632-5a07c5dc5dde",
    "15d22b44-e41d-4ed9-b7fb-48df629874ca",
    "cb0ec69c-a637-4640-9fae-7b8f9af20a27",
    "4bf7e5c7-193e-4059-a222-9271bc556796",
    "eb32775f-33ac-4280-b004-36e723747721",
    "4e68c512-cfbc-4c6b-b411-307c6bd2da9d",
    "35a40ecb-ca95-49f2-b637-4b25c10fd85d",
    "f2529d40-a05f-43e0-8def-6cf797322fa0",
    "c8f6388b-1fc7-4e67-a391-89dc3cac03cc",
    "6e0ad0da-8591-4b07-86ae-23ce4f9a6f06",
    "8cb5fc81-f71f-4bf5-b785-5774bdf02c18",
    "407dee79-7d8f-4e7a-a2dc-4e819ce3738e",
    "f755f2d9-e4e9-408a-8067-a8cc3a697cbb",
    "c51fd5fe-ddd8-4648-9061-c31e59bf9a10",
    "7d87264d-b076-488a-a162-85d51cc2e1bf",
]

GET_WELL_SOON_TEMPLATE_IDS = [
    "43c541c7-f35a-446b-bd3c-b2f1dfbe90d1",
    "881cd100-ac44-441d-882c-3f88565123c1",
    "a6fd2c80-f492-46b5-8d73-406abebde891",
    "ce479899-6345-42e1-850e-c901a5586234",
    "153cb0fd-8e28-40a8-aaed-ef016aa82524",
    "fee6c98e-7299-48b6-8a17-1bcb8044677e",
    "b1e2a60f-f959-434f-8a48-b5edc16d9758",
    "ff5e3d70-c6b1-420c-97d2-554cdb02d84b",
    "f069b0a1-9f83-4644-b37f-648101650aad",
    "34052fc9-f15a-4fed-8f42-9f00f46fe023",
    "0e185274-564a-4afe-b8d0-5b456b8d7089",
    "a3403495-6084-4af5-9dea-75ed0f70bccb",
    "ed7e07d7-d62c-4f0a-98a1-120645c49504",
    "d7982ccc-71e5-45cf-a316-1f11e36b12cc",
    "c1e8f49e-f106-4f13-bf5d-21cf1d293d2d",
    "32d513f0-cd3d-4c6b-8c1d-d4692e54fb8c",
    "ae370b99-f24f-4d1d-9393-8d0f52dc3958",
    "c13eeca4-86f1-47df-8058-6929e0574888",
    "b7e6dfec-7a56-4fdf-a387-d25046fb4d67",
    "775193af-5f27-4b25-9c83-e6ff8d538198",
    "250e6e5d-aade-4368-be12-61ba13cbcf5d",
    "86be29c2-590f-4200-b1da-d04479047d43",
    "15ccb1e3-10a2-4256-8595-452b32f66a22",
    "e07c4367-5ca4-46c0-bd96-5ab094d61d5e",
    "b835810a-dc7b-47b2-8c5a-dd4d6743da6d",
    "5dbc1558-bbe9-4a44-ad0d-6d728840c36f",
    "5d531292-1baa-4be0-a785-9290194ce9cb",
    "a3c3c30c-b230-4acd-8f32-c2727df0f8c2",
    "339461a3-11c0-4755-a5a7-5b838dba3587",
    "b7d248a1-3e26-4a0d-afeb-f8a845e4c004",
    "0c79efd0-c8ee-4c4d-8aa3-d9ce33f8a9d9",
    "7727e85c-fdbb-4981-abab-fdf6e303850b",
    "43b96b40-0df3-4919-82f6-b936961723fc",
    "39a543b6-97a7-4be3-aaab-08095846f59e",
    "e9cc9d18-b5e0-4734-b248-e919a95f3674",
    "8dbde835-0767-4bba-89b9-8fe9a4a09000",
    "211402c8-2d0d-4df3-8128-3297422cbee5",
    "19e55771-ecec-4947-af95-487a2a79872c",
    "264f0ca4-af3a-47b4-ac5e-21da27ada275",
    "ae1b608f-7bc6-40b9-aa7f-2127c9450ce0",
    "e84df649-8dab-44f7-b7bc-bb45e44b4124",
    "e3cc34bd-09b7-473c-8da4-3c2a97a71cec",
    "5096ae69-c3bb-4a70-b123-8f7227141470",
]

GOOD_MORNING_TEMPLATE_IDS = [
    "f6c7a979-17cd-4fe2-a9cc-62b17a13eed7",
    "c44b62cf-9a8b-4b58-932e-1712722ff374",
    "ecd46a0c-dc86-4519-95ce-c79226bbfb68",
    "4e520a41-8bed-4f9e-bc94-fd14b04a99b7",
    "84ad3af5-7bdb-4fa5-9ffb-105784550052",
    "8ed18050-4d0d-49a2-a332-aa1be01c0a7b",
    "b65e4ea5-b5eb-4ee9-a04e-00abf7383f70",
    "8eab473b-8c7c-4ae5-94f4-bf0df451d990",
    "2cf549da-7f1a-4c92-8964-873fb321ea6c",
    "43c6371c-98c5-420c-8962-c90449e6c7ce",
    "46ffac73-ab53-45c0-98ad-5b291189e451",
    "8817c011-1cd6-4434-8012-76e1ea56717e",
    "60645369-a8b2-49e7-9cac-6a311b0c4b18",
    "d4fbc326-2e55-4e78-8604-05e06205ab01",
    "17fd47df-3743-4aca-aa02-13622fe7b6e6",
    "7e60772f-7b6c-4cbd-8a86-a82c0516f769",
    "8de43223-2b3a-4ca5-9e4c-4c08b189c95c",
    "e230ff2e-93d5-46dd-942f-7e4d2f38bdf6",
    "f79c634d-5d84-49e1-a046-8f739877559e",
    "7a1e27bd-3982-43d8-b1db-e73c81247ed0",
    "a6104897-0d9c-4c78-ac89-68ebf3c19c7f",
    "83be6537-1e71-4bff-9267-c2c536705ed3",
    "34267d7d-d242-4883-874d-338f4a99caed",
    "812e7965-9f85-44a1-ac46-045a1ccf7dec",
    "36e06985-94f4-4ee6-ac5d-c9482c17862f",
    "8ddd3c18-2a1b-4053-9296-20c18d1c3a6a",
    "d225836f-fc22-4256-8ec1-749609ac66e6",
    "8a9914be-2156-48a6-9620-b184fb2bc753",
    "c626e80c-5e19-4f3a-8277-aafc5ebacca3",
    "f83a750b-5f29-4890-b383-dd52263772f6",
    "798a95ad-7292-4e51-b05f-a4aa61cc1882",
    "ece3802e-8ee8-466f-b36b-060e9b8f357a",
    "b9176502-a0eb-4bdb-8a7c-a3b9e286ef2f",
    "7cebaca8-6bc2-433d-beb9-6d7da995e6c4",
]

WEDDING_TEMPLATE_IDS = [
    "5a115edf-3586-4d99-973b-624f0158828e",
    "f913bdf4-296e-4fef-b52f-cba3427f78fc",
    "d5b3ca41-e991-446f-8498-68fee994210e",
    "c1a54e47-47f1-4920-adf7-257b2fbea204",
    "3aef5302-789b-4933-8df0-fef7a7d9e58c",
    "1d4eebe7-d76b-45be-885d-f037a886f3e7",
    "6e6e58f0-5e4f-4478-8c53-70fc5f9c8f9b",
    "089436a1-cb71-4609-b144-c2de0df5d5f9",
    "ddcd1914-fd6a-4ee1-809d-73c1b4b1a05d",
    "f75f01e7-0b77-4738-96ac-5515d8c41a3c",
    "b7305fb8-b209-41e5-8708-9a0335775428",
    "ecf22a95-988e-48f8-a987-b89d9dc22cb5",
    "6d2a34ad-561d-4baf-81f2-801af054d927",
    "dff5bd41-4808-4210-ac48-defe5cd67336",
    "e9d46e41-fee7-42e5-b345-f48bafdf723b",
    "7df221c0-fa5f-43c5-a7da-632c49903331",
    "c8bd88c9-6b0f-4aa6-9e30-289c0946ce63",
    "958e1315-a636-4b6e-8353-d356628e2925",
    "e511a3b6-b7b1-47b1-a6c3-41e3b077b114",
    "e37ea5d6-36f5-48a3-ae45-1f3ef585bbc6",
    "fcf9770a-4c3e-46d4-b63f-770963a6a53d",
    "1c5a45c6-bd6b-4449-ada6-320b9e76ca80",
    "0f7b8dba-37dc-4ecf-89dc-cb855cd3e506",
    "4a1b6c54-8e28-4ea2-8c0e-9fa4aa9b4fd0",
    "da32102e-ef42-49c7-88e0-5f05bd2999f4",
    "9220289a-7fe9-4024-8fc0-901d4e0b3c10",
    "1288d22b-a03b-4356-9f58-c418bc0c367d",
    "1ec43965-65e9-4035-9f24-88013f8d6d20",
    "0cbe0dde-74d2-4f64-b291-307ba5f044b4",
    "cd39acb5-1194-41b4-b9ce-09822ada8bce",
    "ad218bd2-5067-455c-8a8a-251e24b98999",
    "cf710551-1df4-42d6-a8a7-a5cc8059958b",
    "1e83615f-609c-4093-aafd-d828fda7fb12",
    "eeddb822-82e1-404f-8c1a-47111ceb4bcf",
    "cc18c509-32e5-489a-b7d7-2141c1c305da",
    "9eec34fc-3b13-42f7-accd-252bee96d8ef",
    "3a9e7745-f312-4938-a133-583da29d26ff",
    "e2a40333-a6c2-4f6e-908b-1a122266c070",
    "79924731-9399-4425-825a-d68fbb13ae67",
    "59babfe6-186e-430b-b9c9-0bf4eddabe20",
    "d019555b-dd9c-4c41-8b19-e5409180830e",
    "fb84d7ca-5ae5-41f2-9121-2bc93622bd4c",
    "93d818d3-b934-4dfb-b3d8-6fc6ede0f699",
    "63105f93-0b40-43cb-92d9-5d24ab50e3ab",
    "4d90f35b-4659-4e94-85b5-8530a7ba71ea",
    "93e59895-b21a-4c48-b889-3dc3abbe9e23",
    "2e0f891d-8bb9-4b02-943e-624492942031",
    "fb24603d-5336-4824-9404-9e17d2ddba06",
    "70192cda-ff83-43d4-907f-0d59e35a3bd7",
    "6e0d415f-443d-47d9-b6cf-b0f8a3e22774",
    "1c3c6f58-6f71-4137-bd96-9a2aae8c88c6",
    "85b1cb4c-5100-4559-a725-bff904d98d9d",
    "465749f5-eb83-48c5-872a-ca153b4733cd",
    "d46823b8-a03d-4243-b9f6-88a9eb5b419b",
    "133c8d71-541c-462a-b879-b921376eee63",
    "1f7e3837-72fb-4a1c-b404-0a80181f05b2",
    "e7a8ad07-21ef-42c4-80ba-7b326737ae65",
    "cce726c7-48a5-4b8a-a204-a37d6cb41362",
    "2caa6d91-fca8-48b7-8d5e-8a4ddb02e3ec",
    "6e549a76-9d9e-444d-b52e-f5c78770d597",
    "22a9d7ed-221f-41f3-82b4-639de99403c8",
    "2982b40b-6e0b-46a6-9857-db199361a770",
    "684cdcb6-b700-46e0-9b4e-ae0979078844",
    "f1a4083b-75f7-4d66-850c-5d326a6920e7",
    "a0198ffd-0ac6-41a1-85c0-a1ee46d3e5aa",
    "c7e1649b-cbe1-4c57-bc4c-ae58866643aa",
    "82dc0e63-404b-454b-a8d9-a0f53a8d9d37",
    "5dcc247a-d047-42cf-8a7d-0b1384f7afa9",
    "db261741-b8e9-478e-b0fe-54bd3fa4ac3c",
    "60fc477a-ea25-4012-94eb-90749224644d",
    "a23793e0-db41-49c3-bad8-9c5d96d9ba19",
    "e8f9a12a-e982-4056-a242-24120e34c70c",
    "8e4889b4-dfd4-4cb1-9a18-b767999cf5cc",
    "8783cde7-a987-40b9-88ec-3b20cf537b57",
    "8682e6ef-bb4a-4e2b-8bb3-aad03af25868",
    "b27ed2f6-cf52-4b00-ae55-d133494c5faf",
    "fa014ae3-fd1c-4d22-a694-ed152f1bcd50",
    "1d8ab63b-d694-4464-bd2a-85f45f143d42",
    "d4b491ed-0532-44ff-8943-9d98f09777a6",
    "b6f011a9-2504-4345-9eea-59537d84399a",
    "38819dd1-fdf4-4566-b130-59dad7e2caa6",
]

TRADITIONAL_WEDDING_TEMPLATE_IDS = [
    "70192cda-ff83-43d4-907f-0d59e35a3bd7",
    "1f7e3837-72fb-4a1c-b404-0a80181f05b2",
    "3aef5302-789b-4933-8df0-fef7a7d9e58c",
    "1c5a45c6-bd6b-4449-ada6-320b9e76ca80",
    "93e59895-b21a-4c48-b889-3dc3abbe9e23",
    "8783cde7-a987-40b9-88ec-3b20cf537b57",
    "c1a54e47-47f1-4920-adf7-257b2fbea204",
    "ad218bd2-5067-455c-8a8a-251e24b98999",
    "4a1b6c54-8e28-4ea2-8c0e-9fa4aa9b4fd0",
    "fcf9770a-4c3e-46d4-b63f-770963a6a53d",
    "cd39acb5-1194-41b4-b9ce-09822ada8bce",
    "38819dd1-fdf4-4566-b130-59dad7e2caa6",
    "6e6e58f0-5e4f-4478-8c53-70fc5f9c8f9b",
    "59babfe6-186e-430b-b9c9-0bf4eddabe20",
]

EXAM_TEMPLATE_IDS = [
    "c98f7757-b864-4eeb-a7eb-6dc41e506159",
    "3a7ef5d5-a49a-4182-9539-4693812e905a",
    "210321a0-7da8-4046-9d70-40a83149c279",
    "b50a3f16-2862-4cd6-a68d-b88848be2d5c",
    "02d1149b-ac54-4984-bc78-96157d8eb9d4",
    "1fbe6f97-a8a5-448f-8f0d-d03dd9bf40b8",
    "4bb6e203-e90b-4037-a903-fc2847e95b3a",
    "52ab30b5-57cf-489e-8422-5b3b012336c5",
    "fbaf0cef-8436-4c42-98f4-674cd4b99b45",
    "5eace0ed-178a-4fbf-93b3-04056af54b8b",
    "19c3647a-d390-469a-8771-a2aaa7257999",
    "c905ec33-c58e-4755-9f7c-bfe8da2e694d",
    "3cab5137-87b0-46f9-921d-ef49670982b4",
    "a3fb4063-5410-4684-8b64-e1bd1659736f",
    "f9761e71-0890-4f66-9e82-b76e807400f4",
    "02232970-acda-4e05-aa72-e50dc3c3f32e",
    "f310b356-15dc-4468-ad80-8d370609a6be",
    "14556f43-07ba-41f6-b527-0d00897e3293",
    "e0cf6d47-f920-4fe3-8066-97e4e1161776",
    "3da2dde1-5737-49f1-b89d-f81188ecd61d",
    "75df7ece-86a7-4202-9260-eba49b547b63",
    "d4d7e730-cba5-4e4b-9e84-a8c2a343f675",
    "ef38e4ca-7c5d-4de6-a812-22915848c950",
    "ea2e50bc-086e-48c8-a550-e79fccd2f3c1",
    "2c8580c7-0221-4be0-af66-37d572c2003b",
    "7ddd51ec-697e-413e-a65c-6980463fc15a",
    "be5a596e-8183-4d03-9780-a2e89d5d20e7",
    "e6588261-56b9-4d0e-97c7-b1c327769ca2",
    "a77c958c-2590-416b-a56a-b01757701114",
]

ASTROLOGY_TEMPLATE_IDS = [
    "0ef531ff-3c60-4544-b60b-03ebf648e428",
    "f591bf28-3e9a-4cf8-ba77-1ba3eaac3ccc",
    "849d0e64-ae0c-45fb-a35e-a38962b44c2a",
    "92f03bcc-21e2-4d10-8357-80e24e00f3e0",
    "4e5c81f9-9813-4541-b94f-c580d8dfd448",
    "0b55c62f-2876-413e-b693-bd8ea756c55d",
    "bd0c3d2f-4ba8-4de6-b904-5468ae2592b3",
    "6c087711-cd0c-4327-bd89-e469ecf08f3d",
    "2ad3bda7-7b1a-4032-b2cd-06999e7006c5",
    "ed475285-2300-433f-9ae3-5beddf0dff83",
    "f2972e7d-0c74-45f5-97b6-9d54dc4754eb",
    "2bf57fcc-0328-4df0-a4cc-8d1ca450407f",
    "ec705d86-8181-45da-ab30-8204a0a21006",
]

# with ThreadPoolExecutor(max_workers=5) as executor:
#     futures = {executor.submit(regenerate_with_text_params, tid): tid for tid in ASTROLOGY_TEMPLATE_IDS}
#     for future in as_completed(futures):
#         tid = futures[future]
#         try:
#             future.result()
#         except Exception as e:
#             print(f"Failed for {tid}: {e}")


IPL_TEMPLATES = [
    {
        "title": "💛 CSK Cheer!",
        "blurb": "Cheer on Chennai Super Kings this season",
    },
    {
        "title": "💙 MI Cheer!",
        "blurb": "Cheer on Mumbai Indians this season",
    },
    {
        "title": "🔴 RCB Cheer!",
        "blurb": "Cheer on Royal Challengers Bengaluru this season",
    },
    {
        "title": "💜 KKR Cheer!",
        "blurb": "Cheer on Kolkata Knight Riders this season",
    },
    {
        "title": "🧡 SRH Cheer!",
        "blurb": "Cheer on Sunrisers Hyderabad this season",
    },
]

IPL_QUESTIONS = [
    {"name": "Your favorite player?", "referrer": "{favorite_player}"},
    {"name": "Photo of yourself?", "referrer": "{me}"},
    {"name": "Write a cheer for the team!", "referrer": "{personal_message}"},
]

IPL_PARAM_TYPES = {
    "Your favorite player?": "text",
    "Photo of yourself?": "image",
    "Write a cheer for the team!": "text",
}

regenerate_template_previews("539811e4-a4e8-4d6d-a424-1171b462fe93", extra_referrers={
    "{favorite_player}": "Rohit Sharma",
    "{me}": "https://db.goriff.com/storage/v1/object/public/logo/aihuman/indian-man.jpg",
    "{personal_message}": "Let's go MI!",
})
