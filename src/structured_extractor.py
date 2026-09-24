"""Generic LLM extraction for tasks that need no task-specific retry logic."""
import json
from pathlib import Path
from typing import Type

from dotenv import load_dotenv
from openai import OpenAI
import re

from pydantic import BaseModel, ValidationError

from src.llm_extractor import PROJECT_ROOT, require_env


def format_pages(pages: list[dict]) -> str:
    return "\n\n".join(
        f"===== PAGE {page['page']} =====\n{page['text']}"
        for page in pages
    )


def extract_structured(
    pages: list[dict],
    prompt_path: Path,
    document_model: Type[BaseModel],
    instruction: str,
) -> tuple[BaseModel, str, list[dict]]:
    load_dotenv(PROJECT_ROOT / ".env")
    system_prompt = Path(prompt_path).read_text(encoding="utf-8")
    schema = document_model.model_json_schema()
    user_prompt = (
        f"{instruction}\n\n"
        f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"公告文本:\n{format_pages(pages)}"
    )
    client = OpenAI(
        api_key=require_env("LLM_API_KEY"),
        base_url=require_env("LLM_BASE_URL"),
    )
    response = client.chat.completions.create(
        model=require_env("LLM_MODEL"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("The model returned an empty response.")
    document, repairs = validate_with_repair(document_model, json.loads(content))
    return document, content, repairs


def validate_with_repair(document_model: Type[BaseModel], payload: dict) -> tuple[BaseModel, list[dict]]:
    """Validate; if a category field is a near miss of exactly one allowed value
    ("s sister_company" -> "sister_company"), repair it, log it and validate again.
    Anything else still raises, so real schema problems are never hidden."""
    try:
        return document_model.model_validate(payload), []
    except ValidationError as error:
        repairs = []
        for item in error.errors():
            if item.get("type") != "literal_error" or not isinstance(item.get("input"), str):
                raise
            allowed = re.findall(r"'([^']+)'", str(item.get("ctx", {}).get("expected", "")))
            value = item["input"].strip()
            matches = [a for a in allowed if a in value]
            if len(matches) != 1:
                raise
            parent = payload
            for key in item["loc"][:-1]:
                parent = parent[key]
            parent[item["loc"][-1]] = matches[0]
            repairs.append({"action": "repair_category_value", "field": ".".join(map(str, item["loc"])),
                            "original": item["input"], "repaired": matches[0]})
        return document_model.model_validate(payload), repairs
