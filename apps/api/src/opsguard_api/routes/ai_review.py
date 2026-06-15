from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from opsguard_api.config import Settings, get_settings
from opsguard_api.db import get_db
from opsguard_api.dependencies import get_embedding_client, get_llm_client
from opsguard_api.schemas import (
    ReviewTaskSuggestionRequest,
    ReviewTaskSuggestionResponse,
)
from opsguard_api.services import ai_review as ai_review_service
from opsguard_api.services.embeddings import EmbeddingClient
from opsguard_api.services.llm import LLMClient

router = APIRouter(prefix="/ai/review-tasks", tags=["ai-review"])


@router.post("/suggest", response_model=ReviewTaskSuggestionResponse)
def suggest_review_task(
    suggestion_in: ReviewTaskSuggestionRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    llm_client: LLMClient = Depends(get_llm_client),
) -> ai_review_service.ReviewTaskSuggestionResponseData:
    try:
        return ai_review_service.suggest_review_task(
            db=db,
            suggestion_in=suggestion_in,
            settings=settings,
            embedding_client=embedding_client,
            llm_client=llm_client,
        )
    except ai_review_service.AIReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
