import re

from schemas.capacity import CapacityDocument


PROJECT_AGREEMENT_SUFFIXES = (
    "项目合资协议",
    "项目投资协议",
    "项目建设协议",
)


def capacity_empty_retry_reason(
    document: CapacityDocument,
    pages: list[dict],
) -> str | None:
    if document.events:
        return None

    full_text = "\n".join(page["text"] for page in pages)
    compact_text = re.sub(r"\s+", "", full_text)

    agreement_titles = re.findall(
        r"签署《([^》]{1,200})》",
        compact_text,
    )

    for title in agreement_titles:
        is_project_agreement = title.endswith(
            PROJECT_AGREEMENT_SUFFIXES
        )
        has_capacity = bool(re.search(
            r"(?:年产|产能|生产规模).{0,30}"
            r"\d+(?:\.\d+)?(?:万)?吨",
            title,
        ))
        if is_project_agreement and has_capacity:
            return "binding_project_agreement_with_capacity"

    return None