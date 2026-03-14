import json
import os
import random
import re

import dotenv
import httpx

from generate_story_prompts import generate_story_prompts
from generate_template_variation import generate_template_variation
from riff_backend import add_templates, get_gift_template, update_gift_template, regenerate_panels, generate_nanobanana, update_gift_template_image, backfill_gift_template_music
from concurrent.futures import ThreadPoolExecutor, as_completed

dotenv.load_dotenv()

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

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
        "version": 2,
        "num_subjects": sum(1 for p in full["parameters"] if p["type"] == "image"),
        "num_panels": len(story_prompts),
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
                        f'Shorten this greeting card title to 3 words max: "{template_name}"\n\n'
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
    prompt = f'Create a cohesive poster for a story called "{short_name}". Use the provided image as the main illustration and add poster text "{short_name}" in the approariate spot, blending in with the surrounding elements. The resulting image should not need to be exact — you must interweave the text in a natural way into the image so that it doesnt just feel like a title, but rather is woven thoughtfully. As a hard requirement, the text should never be blocked or covered by anything in the image.',
    print(f"Cover art for {full['name']}: using panel 8, prompt: {prompt}")

    result = generate_nanobanana(prompt, image_urls=[panel_image_url], aspect_ratio="3:4", model="nanobanana")
    print(f"Nanobanana result for {full['name']}: {result}")

    asset_id = result["data"]["asset_id"]
    update_result = update_gift_template_image(gift_template_id, asset_id)
    print(f"Updated cover art for {full['name']}")
    return update_result

# BIRTHDAY_IDS = [
#     "002958c4-d444-49c7-aa2e-cd20d7ea9fed",
#     "2b474138-4efe-490e-b4f6-68a7888c1bc3",
#     "2db19696-4491-4987-a040-c4f9d4dcd008",
#     "6236a818-76d6-4345-bde4-d27e0509831e",
#     "709bc1b9-5342-4adc-890f-bb608608df78",
#     "8930250c-84d1-4cb0-aca6-e0ed9faa48d3",
#     "93b6da56-97e2-4f79-8e3e-b34e84f4bb99",
#     "b8f5c0be-e2d6-4600-a4c2-234afedcec2f",
#     "e4d65df9-0795-4f06-a048-62ae4df3a8e0",
#     "e59515b9-9f4e-420d-8bbb-3123a54f2015",
#     "e78e0b18-844c-4a52-8b7f-1980188f3452",
#     "fcf585f8-d28f-4e08-adf1-8442c813b56b",
# ]

# with ThreadPoolExecutor(max_workers=1) as executor:
#     futures = {executor.submit(regenerate_cover_art, tid): tid for tid in PROD_IDS}
#     for future in as_completed(futures):
#         template_id = futures[future]
#         try:
#             future.result()
#             print(f"Cover art done for {template_id}")
#         except Exception as e:
#             print(f"Failed cover art for {template_id}: {e}")

def create_templates_full(greeting_card: dict) -> list[str]:
    # Step 1-2: Create variants, generate configs, and create templates in DB
    result = populate(greeting_card)
    template_ids = [r["data"]["id"] for r in result["results"]]
    print(f"Created {len(template_ids)} templates: {template_ids}")

    # Step 3-4: For each template, regenerate panels then create cover art
    def process_template(tid: str):
        print(f"Regenerating panels for {tid}...")
        regenerate_template_previews(tid)
        print(f"Creating cover art for {tid}...")
        regenerate_cover_art(tid)
        print(f"Fully processed {tid}")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_template, tid): tid for tid in template_ids}
        for future in as_completed(futures):
            template_id = futures[future]
            try:
                future.result()
                print(f"Done: {template_id}")
            except Exception as e:
                print(f"Failed: {template_id}: {e}")

    # Step 5: Backfill music for all templates
    # print(f"Backfilling music for {len(template_ids)} templates...")
    # music_result = backfill_gift_template_music(template_ids)
    # print(f"Music backfill result: {music_result}")

    return template_ids

create_templates_full({
    "title": "Birthday Wishes",
    "blurb": "To wish them the happiest of birthdays.",
    "questions": [
        "Photo of the birthday star?",
        "Photo of yourself?"
    ]
})