from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from opsguard_api.config import Settings, get_settings
from opsguard_api.db import get_db
from opsguard_api.dependencies import get_embedding_client
from opsguard_api.schemas import SemanticSearchRequest, SemanticSearchResponse
from opsguard_api.services import search as search_service
from opsguard_api.services.embeddings import EmbeddingClient

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SemanticSearchResponse)
def semantic_search(
    search_in: SemanticSearchRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
) -> search_service.SemanticSearchResponseData:
    try:
        return search_service.semantic_search(
            db=db,
            search_in=search_in,
            settings=settings,
            embedding_client=embedding_client,
        )
    except search_service.SemanticSearchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
