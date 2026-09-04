import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from schemas.pledge import PledgeDocument


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES_PATH = PROJECT_ROOT / "outputs" / "sample_pledge_pages.json"
PROMPT_PATH = PROJECT_ROOT / "prompts" / "pledge_extraction_v1.txt"
RAW_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "sample_pledge_llm_raw.json"
RESULT_PATH = PROJECT_ROOT / "outputs" / "sample_pledge_prediction.json"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def extract_pledge(
    pages: list[dict],
) -> tuple[PledgeDocument, str]:
    load_dotenv(PROJECT_ROOT / ".env")

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    schema = PledgeDocument.model_json_schema()

    page_text = "\n\n".join(
        f"===== PAGE {page['page']} =====\n{page['text']}"
        for page in pages
    )

    user_prompt = (
        "请根据下面的JSON Schema抽取股份质押信息。\n\n"
        f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"公告文本:\n{page_text}"
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

    document = PledgeDocument.model_validate(json.loads(content))
    return document, content


def main() -> None:
    pages = json.loads(PAGES_PATH.read_text(encoding="utf-8"))
    document, raw_content = extract_pledge(pages)

    RAW_OUTPUT_PATH.write_text(raw_content, encoding="utf-8")
    RESULT_PATH.write_text(
        document.model_dump_json(indent=2),
        encoding="utf-8",
    )

    print(f"Model: {require_env('LLM_MODEL')}")
    print(f"Validated result saved to: {RESULT_PATH}")


if __name__ == "__main__":
    main()