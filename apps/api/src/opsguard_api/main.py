from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from opsguard_api.db import init_database
from opsguard_api.routes.ai_review import router as ai_review_router
from opsguard_api.routes.answer import router as answer_router
from opsguard_api.routes.audit_events import router as audit_events_router
from opsguard_api.routes.documents import router as documents_router
from opsguard_api.routes.review_tasks import router as review_tasks_router
from opsguard_api.routes.search import router as search_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_database()
    yield


app = FastAPI(title="OpsGuard AI API", lifespan=lifespan)
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(answer_router)
app.include_router(review_tasks_router)
app.include_router(ai_review_router)
app.include_router(audit_events_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
