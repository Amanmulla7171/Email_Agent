from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Security, UploadFile, File, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.core.attachments import save_uploaded_attachment, load_attachment_by_id
from app.schemas.email import (
    DraftEmailRequest,
    DraftEmailResponse,
    SendEmailRequest,
    SendEmailResponse,
    ApplyEmailRequest,
    AttachmentUploadResponse,
    AttachmentInfo,
)
from app.services.email_agent_service import EmailAgentService, email_service

router = APIRouter(prefix="/email", tags=["Email Agent"])

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_auth_if_configured(
    api_key: Optional[str] = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Validates API key for production deployments if API_SECRET_KEY is configured.
    In local development (when API_SECRET_KEY is empty), allows unauthenticated access.
    """
    if settings.API_SECRET_KEY:
        if not api_key or api_key != settings.API_SECRET_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key (X-API-Key header required).",
            )


@router.post(
    "/attachments/upload",
    response_model=AttachmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an Email Attachment",
    description="Uploads and validates a document (PDF, DOCX, TXT), checking size, MIME type, and magic bytes. Returns a secure attachment reference ID.",
)
async def upload_attachment_endpoint(
    file: UploadFile = File(..., description="Document file to upload (preferably PDF)"),
    _auth: None = Depends(verify_auth_if_configured),
) -> AttachmentUploadResponse:
    """Safely saves an uploaded attachment and returns its secure reference ID."""
    content = await file.read()
    metadata = save_uploaded_attachment(
        filename=file.filename or "document.pdf",
        content=content,
        content_type=file.content_type,
    )
    return AttachmentUploadResponse(
        attachment_id=metadata["attachment_id"],
        filename=metadata["filename"],
        content_type=metadata["content_type"],
        size_bytes=metadata["size_bytes"],
    )


@router.get(
    "/attachments/available",
    response_model=list[AttachmentInfo],
    status_code=status.HTTP_200_OK,
    summary="List Available Attachments",
    description="Returns list of verified documents and resumes stored on the server available for email attachment.",
)
def list_available_attachments_endpoint(
    _auth: None = Depends(verify_auth_if_configured),
) -> list[AttachmentInfo]:
    """Returns list of available documents and resumes on the server."""
    from app.core.attachments import list_available_attachments
    raw_list = list_available_attachments()
    return [
        AttachmentInfo(
            attachment_id=item.get("attachment_id"),
            filename=item["filename"],
            content_type=item.get("content_type", "application/pdf"),
            size_bytes=item.get("size_bytes", 0),
        )
        for item in raw_list
    ]



@router.get(
    "/attachments/{attachment_id}",
    response_model=AttachmentInfo,
    status_code=status.HTTP_200_OK,
    summary="Get Attachment Metadata",
    description="Inspects the metadata of an uploaded attachment reference without exposing file execution or arbitrary downloads.",
)
def get_attachment_info_endpoint(
    attachment_id: str,
    _auth: None = Depends(verify_auth_if_configured),
) -> AttachmentInfo:
    """Returns validated metadata for an attachment ID."""
    metadata = load_attachment_by_id(attachment_id)
    return AttachmentInfo(
        attachment_id=metadata["attachment_id"],
        filename=metadata["filename"],
        content_type=metadata.get("mime_type", "application/pdf"),
        size_bytes=metadata.get("size_bytes", 0),
    )


@router.post(
    "/draft",
    response_model=DraftEmailResponse,
    status_code=status.HTTP_200_OK,
    summary="Draft an Email",
    description="Invokes the existing LangGraph agent to generate a draft email from instructions and context without sending it.",
)
def draft_email_endpoint(
    request: DraftEmailRequest,
    service: EmailAgentService = Depends(lambda: email_service),
) -> DraftEmailResponse:
    """Generates a professional email draft using the existing LangGraph workflow."""
    return service.generate_draft(
        recipient_email=str(request.recipient_email),
        instruction=request.instruction,
        recipient_name=request.recipient_name,
        job_description=request.job_description,
        applicant_context=request.applicant_context,
        thread_id=request.thread_id,
        attachment_ids=request.attachment_ids,
        attachments=request.attachments,
        include_default_attachment=request.include_default_attachment,
    )


@router.post(
    "/send",
    response_model=SendEmailResponse,
    status_code=status.HTTP_200_OK,
    summary="Send Approved Email",
    description="Validates explicit approval, resolves attachments, and dispatches email using the existing mailer integration. Never sends without explicit approval.",
)
def send_email_endpoint(
    request: SendEmailRequest,
    service: EmailAgentService = Depends(lambda: email_service),
    _auth: None = Depends(verify_auth_if_configured),
) -> SendEmailResponse:
    """Dispatches the validated email and attached documents after explicit user confirmation."""
    return service.send_email(
        recipient_email=str(request.recipient_email),
        subject=request.subject,
        body=request.body,
        recipient_name=request.recipient_name,
        approved=request.approved,
        thread_id=request.thread_id,
        attachment_ids=request.attachment_ids,
        attachments=request.attachments,
        include_default_attachment=request.include_default_attachment,
    )


@router.post(
    "/apply",
    response_model=DraftEmailResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete Application Workflow Draft",
    description="Accepts job description, recipient email, applicant context, and optional attachments, returning a tailored draft for review without sending.",
)
def apply_email_endpoint(
    request: ApplyEmailRequest,
    service: EmailAgentService = Depends(lambda: email_service),
) -> DraftEmailResponse:
    """Prepares an application email draft tailored to the job requirements and applicant background."""
    return service.generate_draft(
        recipient_email=str(request.recipient_email),
        instruction=request.instruction,
        recipient_name=request.recipient_name,
        job_description=request.job_description,
        applicant_context=request.applicant_context,
        thread_id=request.thread_id,
        attachment_ids=request.attachment_ids,
        attachments=request.attachments,
        include_default_attachment=request.include_default_attachment,
    )
