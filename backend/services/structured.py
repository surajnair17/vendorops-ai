import json

from pydantic import ValidationError

from backend.config import settings
from backend.errors import AppError
from backend.examples import examples
from backend.schemas.business import BusinessDocument, issues_for, source_issues


class FixtureProvider:
    mode = "fixture"

    def extract(self, text: str, repair: bool = False) -> str:
        for example in examples():
            if text.strip() == example["text"]:
                return json.dumps(example["data"])
        raise AppError(
            422,
            "fixture_unavailable",
            "No fixture matches this text. Use generated samples or configure live AI.",
        )


def extract_structure(text: str, pages: list[str], provider=None) -> dict:
    if len(text) > settings.max_model_characters:
        raise AppError(413, "model_input_too_large", "Text exceeds the model input budget.")
    if not text.strip():
        raise AppError(422, "text_required", "Extract text or complete OCR before structuring.")
    if provider is None:
        if settings.provider == "fixture":
            provider = FixtureProvider()
        elif settings.provider == "bedrock":
            from backend.services.cloud import BedrockProvider

            provider = BedrockProvider()
        else:
            raise AppError(422, "invalid_provider", "Configure fixture or bedrock provider.")
    provider_text = (
        "\n\n".join(f"PAGE {i + 1}\n{page}" for i, page in enumerate(pages))
        if provider.mode == "bedrock"
        else text
    )
    for attempt in range(2):
        try:
            raw = provider.extract(provider_text, repair=bool(attempt))
            document = BusinessDocument.model_validate_json(raw)
            issues = issues_for(document) + source_issues(document, pages)
            return {
                "structured": document.model_dump(mode="json"),
                "issues": issues,
                "review_status": "needs_review" if issues else "ready",
                "provider": provider.mode,
                "attempts": attempt + 1,
                "schema_version": 1,
                "prompt_version": 1,
                "model_id": settings.model_id if provider.mode == "bedrock" else None,
            }
        except (ValidationError, json.JSONDecodeError):
            continue
        except TimeoutError as error:
            raise AppError(504, "provider_timeout", "The extraction provider timed out.") from error
    return {
        "structured": None,
        "issues": ["Provider output failed schema validation twice"],
        "review_status": "needs_review",
        "provider": provider.mode,
        "attempts": 2,
        "schema_version": 1,
        "prompt_version": 1,
        "model_id": settings.model_id if provider.mode == "bedrock" else None,
    }
