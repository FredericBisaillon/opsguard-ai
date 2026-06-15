from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from opsguard_api.config import Settings, get_settings
from opsguard_api.db import get_db
from opsguard_api.dependencies import get_embedding_client, get_llm_client
from opsguard_api.schemas import AnswerRequest, AnswerResponse
from opsguard_api.services import answer as answer_service
from opsguard_api.services.embeddings import EmbeddingClient
from opsguard_api.services.llm import LLMClient

router = APIRouter(tags=["answer"])


@router.post("/answer", response_model=AnswerResponse)
def answer_question(
    answer_in: AnswerRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    llm_client: LLMClient = Depends(get_llm_client),
) -> answer_service.AnswerResponseData:
    try:
        return answer_service.answer_question(
            db=db,
            answer_in=answer_in,
            settings=settings,
            embedding_client=embedding_client,
            llm_client=llm_client,
        )
    except answer_service.AnswerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
