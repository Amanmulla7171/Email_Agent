from fastapi import APIRouter
from app.schemas.email import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Service Health Check")
def get_health() -> HealthResponse:
    """Returns simple status indicating whether the API service is active."""
    return HealthResponse(
        status="healthy",
        service="email-agent-api"
    )
