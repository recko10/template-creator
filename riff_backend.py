import os
from typing import Optional

import httpx
import dotenv

dotenv.load_dotenv()

BACKEND_ENDPOINT = os.environ["BACKEND_ENDPOINT"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]


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


def add_templates(variations: list[dict], story_prompts: list[list[str]]) -> list[dict]:
    results = []
    for i, variation in enumerate(variations):
        parameters = [
            {"name": q, "type": "image", "required": True, "position": j}
            for j, q in enumerate(variation["questions"])
        ]
        config = {
            "version": 2,
            "num_subjects": len(variation["questions"]),
            "num_panels": len(story_prompts[i]),
            "prompts": [
                {"position": str(j), "prompt": prompt}
                for j, prompt in enumerate(story_prompts[i])
            ],
        }
        print(config)
        result = create_gift_template(
            variation["title"],
            blurb=variation["blurb"],
            parameters=parameters,
            config=config,
        )
        results.append(result)
    return results
