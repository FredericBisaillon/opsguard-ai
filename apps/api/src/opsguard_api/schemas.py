from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opsguard_api.models import DocumentStatus


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    source_type: str = Field(min_length=1, max_length=50)
    source_path: str = Field(min_length=1)


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_type: str
    source_path: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
