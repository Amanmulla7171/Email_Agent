from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr, field_validator


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(default="healthy", description="Current health status")
    service: str = Field(default="email-agent-api", description="Service identifier")


class AttachmentInfo(BaseModel):
    """Metadata describing an attached document."""
    attachment_id: Optional[str] = Field(default=None, description="Unique identifier for uploaded attachment reference")
    filename: str = Field(description="Sanitized name of the attached file")
    content_type: str = Field(default="application/pdf", description="MIME content type")
    size_bytes: Optional[int] = Field(default=None, description="File size in bytes")


class AttachmentPayload(BaseModel):
    """Inline base64-encoded attachment payload for direct transfers."""
    filename: str = Field(description="Name of the file including extension (e.g. resume.pdf)")
    content_base64: str = Field(description="Base64-encoded document content")
    content_type: Optional[str] = Field(default=None, description="MIME type (e.g. application/pdf)")


class AttachmentUploadResponse(BaseModel):
    """Response returned upon successful file upload."""
    attachment_id: str = Field(description="Secure reference ID for the uploaded attachment")
    filename: str = Field(description="Sanitized filename stored on server")
    content_type: str = Field(description="Detected MIME content type")
    size_bytes: int = Field(description="Total size in bytes")


class DraftEmailRequest(BaseModel):
    """Payload to generate a drafted email."""
    instruction: Optional[str] = Field(
        default=None,
        description="Natural-language instruction describing the email purpose",
        max_length=5000,
    )
    recipient_email: EmailStr = Field(
        description="Destination email address"
    )
    recipient_name: Optional[str] = Field(
        default=None,
        description="Name of the recipient or hiring contact",
        max_length=200,
    )
    job_description: Optional[str] = Field(
        default=None,
        description="Job post or vacancy details for contextualization",
        max_length=20000,
    )
    applicant_context: Optional[str] = Field(
        default=None,
        description="Applicant background, skills, or portfolio highlights",
        max_length=10000,
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Optional session or conversation thread identifier for LangGraph state checkpointing",
    )
    attachment_ids: Optional[List[str]] = Field(
        default=None,
        description="List of uploaded attachment IDs to reference in the draft",
    )
    attachments: Optional[List[AttachmentPayload]] = Field(
        default=None,
        description="List of inline base64 attachments to associate with the draft",
    )
    include_default_attachment: bool = Field(
        default=True,
        description="Whether to automatically attach the default resume (Aman_Mulla_Resume.pdf)",
    )

    @field_validator("instruction", "job_description", "applicant_context", mode="before")
    @classmethod
    def strip_optional_strings(cls, v):
        if isinstance(v, str):
            v_stripped = v.strip()
            return v_stripped if v_stripped else None
        return v

    @field_validator("recipient_email", mode="before")
    @classmethod
    def validate_email_not_empty(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Recipient email cannot be empty.")
        return v


class ApplyEmailRequest(BaseModel):
    """Payload to generate a tailored job application email draft."""
    recipient_email: EmailStr = Field(
        description="Recipient email address (e.g. hr@company.com)"
    )
    job_description: str = Field(
        min_length=10,
        max_length=20000,
        description="Job description or posting requirements",
    )
    applicant_context: str = Field(
        min_length=5,
        max_length=10000,
        description="Applicant profile, skills, experience, or resume summary",
    )
    recipient_name: Optional[str] = Field(
        default=None,
        description="Name of the recruiter or hiring manager",
        max_length=200,
    )
    instruction: Optional[str] = Field(
        default="Write a professional, compelling job application email tailored to the job description and applicant background.",
        description="Custom instruction for email drafting",
        max_length=5000,
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Optional session thread ID",
    )
    attachment_ids: Optional[List[str]] = Field(
        default=None,
        description="List of uploaded attachment IDs (e.g. uploaded resume)",
    )
    attachments: Optional[List[AttachmentPayload]] = Field(
        default=None,
        description="List of inline base64 attachments to associate with this application",
    )
    include_default_attachment: bool = Field(
        default=True,
        description="Whether to automatically attach the default resume (Aman_Mulla_Resume.pdf)",
    )

    @field_validator("job_description", "applicant_context", mode="before")
    @classmethod
    def validate_not_blank(cls, v):
        if isinstance(v, str) and not v.strip():
            raise ValueError("Field cannot be empty or blank whitespace.")
        return v


class DraftEmailResponse(BaseModel):
    """Response returned upon successful email draft generation."""
    status: str = Field(default="draft_created", description="Workflow draft status")
    recipient_email: str = Field(description="Target recipient email")
    recipient_name: Optional[str] = Field(default=None, description="Target recipient name")
    subject: str = Field(description="Generated email subject line")
    body: str = Field(description="Generated email body content")
    requires_approval: bool = Field(default=True, description="Indicates explicit approval is required before sending")
    thread_id: Optional[str] = Field(default=None, description="LangGraph thread ID holding the workflow state")
    attachments: List[AttachmentInfo] = Field(default_factory=list, description="List of attached documents included in the draft")


class SendEmailRequest(BaseModel):
    """Payload to send an approved email."""
    recipient_email: EmailStr = Field(
        description="Target recipient email address"
    )
    recipient_name: Optional[str] = Field(
        default=None,
        description="Optional recipient display name",
        max_length=200,
    )
    subject: str = Field(
        min_length=1,
        max_length=500,
        description="Subject of the email",
    )
    body: str = Field(
        min_length=1,
        max_length=50000,
        description="Body text of the email",
    )
    approved: bool = Field(
        default=False,
        description="Explicit user approval to send. Must be true to trigger dispatch.",
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Optional LangGraph thread ID if sending from an existing graph checkpoint",
    )
    attachment_ids: Optional[List[str]] = Field(
        default=None,
        description="List of validated attachment IDs to include as attachments",
    )
    attachments: Optional[List[AttachmentPayload]] = Field(
        default=None,
        description="List of direct base64-encoded attachments to include in the email",
    )
    include_default_attachment: bool = Field(
        default=True,
        description="Whether to automatically attach the default resume (Aman_Mulla_Resume.pdf)",
    )

    @field_validator("subject", "body", mode="before")
    @classmethod
    def check_not_blank(cls, v):
        if isinstance(v, str) and not v.strip():
            raise ValueError("Value cannot be blank whitespace.")
        return v


class SendEmailResponse(BaseModel):
    """Response returned when an email has been accepted and dispatched by the mailer."""
    status: str = Field(default="sent", description="Dispatch status")
    delivery_scope: str = Field(
        default="smtp_relay_accepted",
        description="Delivery level: confirms SMTP relay transmission, not guaranteed inbox delivery",
    )
    smtp_server: Optional[str] = Field(
        default="smtp.gmail.com:587",
        description="SMTP server and port that accepted the message",
    )
    message: str = Field(description="Confirmation message from email provider")
    recipient_email: str = Field(description="Recipient email address")
    recipient_name: Optional[str] = Field(default=None, description="Recipient name")
    attachments: List[AttachmentInfo] = Field(
        default_factory=list,
        description="List of attached documents successfully dispatched",
    )
    delivery_notice: str = Field(
        default="Email was accepted by the SMTP relay server. SMTP confirms successful transmission to the relay; final inbox placement depends on recipient mail server policies (spam filters, SPF/DKIM verification).",
        description="Notice distinguishing SMTP acceptance from end-user inbox placement",
    )

