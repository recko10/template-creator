import os
import random
from typing import Optional

import httpx
import dotenv

dotenv.load_dotenv()

BACKEND_ENDPOINT = os.environ["BACKEND_ENDPOINT"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

def get_gift_template(gift_template_id: str, *, timeout: int = 30) -> dict:
    response = httpx.get(
        f"{BACKEND_ENDPOINT}/api/gift-template/get/id",
        params={"id": gift_template_id},
        timeout=timeout,
    )
    if not response.is_success:
        print(f"Error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()

def create_gift_template(
    name: str,
    *,
    blurb: Optional[str] = None,
    tag_ids: Optional[list[str]] = None,
    parameters: Optional[list[dict]] = None,
    config: Optional[dict] = None,
    timeout: int = 30,
) -> dict:
    body: dict = {"name": name}

    if blurb is not None:
        body["blurb"] = blurb

    if tag_ids is not None:
        body["tagIds"] = tag_ids

    if parameters is not None:
        body["parameters"] = [
            {
                "name": p["name"],
                **({"type": p["type"]} if "type" in p else {}),
                **({"description": p["description"]} if "description" in p else {}),
                **({"required": p["required"]} if "required" in p else {}),
                **({"position": p["position"]} if "position" in p else {}),
            }
            for p in parameters
        ]

    if config is not None:
        body["config"] = config

    response = httpx.post(
        f"{BACKEND_ENDPOINT}/api/admin/gift-template/create",
        params={"adminPassword": ADMIN_PASSWORD},
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    if not response.is_success:
        print(f"Error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()


def update_gift_template(
    gift_template_id: str,
    *,
    name: Optional[str] = None,
    blurb: Optional[str] = None,
    parameters: Optional[list[dict]] = None,
    config: Optional[dict] = None,
    timeout: int = 30,
) -> dict:
    body: dict = {"giftTemplateId": gift_template_id}

    if name is not None:
        body["name"] = name

    if blurb is not None:
        body["blurb"] = blurb

    if parameters is not None:
        body["parameters"] = [
            {
                "name": p["name"],
                **({"type": p["type"]} if "type" in p else {}),
                **({"description": p["description"]} if "description" in p else {}),
                **({"required": p["required"]} if "required" in p else {}),
                **({"position": p["position"]} if "position" in p else {}),
            }
            for p in parameters
        ]

    if config is not None:
        body["config"] = config

    response = httpx.post(
        f"{BACKEND_ENDPOINT}/api/admin/gift-template/update",
        params={"adminPassword": ADMIN_PASSWORD},
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    if not response.is_success:
        print(f"Error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()


def regenerate_panels(
    gift_template_id: str,
    *,
    aesthetic: str = "pixel art",
    person_one_image_url: str,
    person_two_image_url: str,
    timeout: int = 120,
) -> dict:
    body = {
        "giftTemplateId": gift_template_id,
        "aesthetic": aesthetic,
        "personOneImageUrl": person_one_image_url,
        "personTwoImageUrl": person_two_image_url,
    }

    response = httpx.post(
        f"{BACKEND_ENDPOINT}/api/admin/gift-template/regenerate-panels",
        params={"adminPassword": ADMIN_PASSWORD},
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    if not response.is_success:
        print(f"Error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()


def update_gift_template_image(
    gift_template_id: str,
    image_asset_id: str,
    *,
    timeout: int = 30,
) -> dict:
    body = {
        "giftTemplateId": gift_template_id,
        "imageAssetId": image_asset_id,
    }

    response = httpx.post(
        f"{BACKEND_ENDPOINT}/api/admin/gift-template/update-image",
        params={"adminPassword": ADMIN_PASSWORD},
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    if not response.is_success:
        print(f"Error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()


def backfill_gift_template_music(
    gift_template_ids: list[str],
    *,
    timeout: int = 300,
) -> dict:
    body = {"giftTemplateIds": gift_template_ids}

    response = httpx.post(
        f"{BACKEND_ENDPOINT}/api/admin/backfill-gift-template-music",
        params={"adminPassword": ADMIN_PASSWORD},
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    if not response.is_success:
        print(f"Error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()


def generate_nanobanana(
    prompt: str,
    *,
    image_urls: list[str],
    aspect_ratio: str = "9:16",
    pro: bool = False,
    model: Optional[str] = None,
    timeout: int = 120,
) -> dict:
    body = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "image_urls": image_urls,
        "pro": pro,
    }

    if model is not None:
        body["model"] = model

    response = httpx.post(
        f"{BACKEND_ENDPOINT}/api/admin/nanobanana",
        params={"adminPassword": ADMIN_PASSWORD},
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    if not response.is_success:
        print(f"Error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()


def add_templates(
    variations: list[dict],
    story_prompts: list[list[str]],
    *,
    visual_tag_ids: Optional[list[str]] = None,
) -> list[dict]:
    results = []
    for i, variation in enumerate(variations):
        parameters = [
            {"name": q, "type": "image", "required": True, "position": j}
            for j, q in enumerate(variation["questions"])
        ]
        config = {
            "version": 3,
            "num_subjects": len(variation["questions"]),
            "num_panels": len(story_prompts[i]),
            "system_prompt": "Create the following scene in a {aesthetic} style:",
            "prompts": [
                {"position": str(j), "prompt": prompt}
                for j, prompt in enumerate(story_prompts[i])
            ],
        }
        tag_id = visual_tag_ids[i] if visual_tag_ids else random.choice([
            "04f82724-5532-4409-b308-3170151e1dec",
            "0d037ca2-6e6e-4ac4-9803-52f6d771c8e6",
            "1c4f6bb3-35c5-49d1-b3b2-773f6b3ea859",
            "1ef914c7-1e6e-4dc2-873e-b128894a6189",
            "3b1c8bb1-251a-441d-b77b-921b493910f4",
            "3cd9e793-3982-4862-aee6-d17f80290f8c",
            "42be0fce-1121-4f3c-b7af-e8a4157860af",
            "565e41ce-e43a-4581-904f-2969bafa0bc7",
            "5e4c30ec-ab71-4617-b28b-c15ac001e32d",
            "60206eb2-bf52-4b46-ac2b-6aa696a23914",
            "63bfe536-adfc-46e2-a029-30cf22b96fbe",
            "758c2081-582c-4924-80cb-4699a90314f0",
            "9355145d-4291-4378-afb7-56d8891c86aa",
            "c545bc6c-2c9a-4be9-b590-dcd58760dc85",
            "c9f52b23-a3fd-4495-bac5-cae05581c4ce",
            "fee44934-cf07-4c6d-809e-8f523d59730e",
        ])
        print(config)
        result = create_gift_template(
            variation["title"],
            blurb=variation["blurb"],
            tag_ids=[tag_id],
            parameters=parameters,
            config=config,
        )
        results.append(result)
    return results


def add_text_param(
    gift_template_id: str,
    *,
    name: str,
    referrer: str,
    position: Optional[int] = None,
    description: Optional[str] = None,
    timeout: int = 30,
) -> dict:
    template = get_gift_template(gift_template_id, timeout=timeout)
    config = template["data"]["config"]

    params = config["parameters"]
    if position is None:
        position = len(params)

    # Bump positions of existing params at or after the insertion point
    for p in params:
        if p["position"] >= position:
            p["position"] += 1

    param = {
        "referrer": referrer,
        "type": "text",
        "name": name,
        "position": position,
        "required": True,
    }
    if description is not None:
        param["description"] = description

    params.append(param)

    return update_gift_template(gift_template_id, config=config, timeout=timeout)

