from typing import Literal

from pydantic import BaseModel


class ExtractionResponse(BaseModel):
    filename: str
    page_count: int
    extracted_text: str
    character_count: int
    extraction_status: Literal["success", "no_text"]
    message: str
