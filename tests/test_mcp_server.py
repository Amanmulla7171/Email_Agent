import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from mcp_server import draft_application_email, send_application_email, list_available_attachments


@pytest.mark.anyio
async def test_mcp_draft_application_email_success():
    """Verify MCP draft tool calls FastAPI backend and formats draft response."""
    mock_backend_response = MagicMock()
    mock_backend_response.status_code = 200
    mock_backend_response.json.return_value = {
        "status": "draft_created",
        "recipient_email": "hr@example.com",
        "recipient_name": "Hiring Manager",
        "subject": "Application for AI Engineer Role",
        "body": "Dear Hiring Manager,\n\nI am applying for the position...",
        "requires_approval": True,
        "thread_id": "thread-abc-123"
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_backend_response

        raw_result = await draft_application_email(
            recipient_email="hr@example.com",
            instruction="Apply for the AI Engineer role",
            job_description="Seeking AI Engineer with Python and LangGraph experience.",
            applicant_context="Experienced in Python, FastAPI, and LangGraph.",
            recipient_name="Hiring Manager"
        )

        result = json.loads(raw_result)
        assert result["status"] == "draft_created"
        assert result["recipient_email"] == "hr@example.com"
        assert result["subject"] == "Application for AI Engineer Role"
        assert result["requires_approval"] is True
        assert result["thread_id"] == "thread-abc-123"
        mock_post.assert_called_once()


@pytest.mark.anyio
async def test_mcp_draft_connection_failure():
    """Verify MCP draft tool handles backend connection failure gracefully."""
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        raw_result = await draft_application_email(recipient_email="hr@example.com")
        result = json.loads(raw_result)
        assert "error" in result
        assert "Failed to connect" in result["error"]


@pytest.mark.anyio
async def test_mcp_send_aborts_without_explicit_approval():
    """Verify MCP send tool immediately blocks execution if approved is False."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        raw_result = await send_application_email(
            recipient_email="hr@example.com",
            subject="Application for AI Engineer",
            body="Dear Hiring Team...",
            approved=False  # Crucial safety check
        )

        result = json.loads(raw_result)
        assert result["status"] == "blocked"
        assert result["approved"] is False
        assert "SAFETY ABORT" in result["message"]
        # Ensure HTTP call is never made
        mock_post.assert_not_called()


@pytest.mark.anyio
async def test_mcp_send_success_when_approved():
    """Verify MCP send tool calls FastAPI backend when explicit approval is provided."""
    mock_backend_response = MagicMock()
    mock_backend_response.status_code = 200
    mock_backend_response.json.return_value = {
        "status": "sent",
        "recipient_email": "hr@example.com",
        "message": "Email successfully sent to hr@example.com via smtp.gmail.com:587"
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_backend_response

        raw_result = await send_application_email(
            recipient_email="hr@example.com",
            subject="Application for AI Engineer",
            body="Dear Hiring Team...",
            approved=True,
            thread_id="thread-abc-123"
        )

        result = json.loads(raw_result)
        assert result["status"] == "sent"
        assert "Email successfully sent" in result["message"]
        mock_post.assert_called_once()


@pytest.mark.anyio
async def test_mcp_send_backend_failure_reporting():
    """Verify MCP send tool reports backend delivery failure accurately."""
    mock_backend_response = MagicMock()
    mock_backend_response.status_code = 502
    mock_backend_response.text = "SMTP Authentication Error: Bad credentials"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_backend_response

        raw_result = await send_application_email(
            recipient_email="hr@example.com",
            subject="Application for AI Engineer",
            body="Dear Hiring Team...",
            approved=True
        )

        result = json.loads(raw_result)
        assert "error" in result
        assert result["status_code"] == 502


@pytest.mark.anyio
async def test_mcp_draft_with_attachment_references():
    """Verify MCP draft tool includes attachment references in the payload and response."""
    mock_backend_response = MagicMock()
    mock_backend_response.status_code = 200
    mock_backend_response.json.return_value = {
        "status": "draft_created",
        "recipient_email": "hr@example.com",
        "subject": "Application with Resume Attached",
        "body": "Dear Hiring Team, please see my attached resume.",
        "attachments": [
            {"filename": "my_resume.pdf", "attachment_id": "att_test123", "size_bytes": 1024}
        ],
        "requires_approval": True,
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_backend_response

        raw_result = await draft_application_email(
            recipient_email="hr@example.com",
            instruction="Apply with resume",
            attachment_ids=["att_test123"]
        )

        result = json.loads(raw_result)
        assert result["status"] == "draft_created"
        assert len(result["attachments"]) == 1
        assert result["attachments"][0]["filename"] == "my_resume.pdf"
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["attachment_ids"] == ["att_test123"]


@pytest.mark.anyio
async def test_mcp_send_aborts_and_shows_attachments_when_unapproved():
    """Verify MCP send tool includes attachment filenames in the approval review summary when blocked."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        raw_result = await send_application_email(
            recipient_email="hr@example.com",
            subject="Application for AI Engineer",
            body="Dear Hiring Team...",
            approved=False,
            attachment_ids=["att_123"],
            attachments=[{"filename": "resume.pdf", "content_base64": "dummy"}]
        )

        result = json.loads(raw_result)
        assert result["status"] == "blocked"
        assert result["approved"] is False
        assert "resume.pdf" in result["message"]
        mock_post.assert_not_called()


@pytest.mark.anyio
async def test_mcp_send_with_attachments_succeeds_when_approved():
    """Verify MCP send tool dispatches attachments when approved=True."""
    mock_backend_response = MagicMock()
    mock_backend_response.status_code = 200
    mock_backend_response.json.return_value = {
        "status": "sent",
        "recipient_email": "hr@example.com",
        "attachments": [{"filename": "resume.pdf", "size_bytes": 2048}],
        "message": "Email sent with 1 attachment."
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_backend_response

        raw_result = await send_application_email(
            recipient_email="hr@example.com",
            subject="Application for AI Engineer",
            body="Dear Hiring Team...",
            approved=True,
            attachments=[{"filename": "resume.pdf", "content_base64": "dummy", "content_type": "application/pdf"}]
        )

        result = json.loads(raw_result)
        assert result["status"] == "sent"
        assert len(result["attachments"]) == 1
        assert result["attachments"][0]["filename"] == "resume.pdf"
        mock_post.assert_called_once()


@pytest.mark.anyio
async def test_mcp_send_shows_default_resume_in_unapproved_safety_message():
    """Verify MCP send tool shows Aman_Mulla_Resume.pdf in review message by default."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        raw_result = await send_application_email(
            recipient_email="hr@example.com",
            subject="Job Application",
            body="Dear Hiring Team...",
            approved=False,
            include_default_attachment=True,
        )

        result = json.loads(raw_result)
        assert result["status"] == "blocked"
        assert result["approved"] is False
        assert "Aman_Mulla_Resume.pdf" in result["message"]
        assert any("Aman_Mulla_Resume.pdf" in a for a in result["review"]["attachments"])
        assert "smtp_relay" in result["review"]
        mock_post.assert_not_called()


@pytest.mark.anyio
async def test_mcp_list_available_attachments_success():
    """Verify list_available_attachments tool queries backend endpoint and returns attachments."""
    mock_backend_response = MagicMock()
    mock_backend_response.status_code = 200
    mock_backend_response.json.return_value = [
        {
            "filename": "Aman_Mulla_Resume.pdf",
            "content_type": "application/pdf",
            "size_bytes": 316362,
            "attachment_id": None
        }
    ]

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_backend_response
        raw_result = await list_available_attachments()
        result = json.loads(raw_result)
        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["available_attachments"][0]["filename"] == "Aman_Mulla_Resume.pdf"
        mock_get.assert_called_once()


@pytest.mark.anyio
async def test_mcp_list_available_attachments_connection_fallback():
    """Verify list_available_attachments returns fallback with default resume if backend is unreachable."""
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")):
        raw_result = await list_available_attachments()
        result = json.loads(raw_result)
        assert result["status"] == "fallback"
        assert result["count"] == 1
        assert result["available_attachments"][0]["filename"] == "Aman_Mulla_Resume.pdf"


@pytest.mark.anyio
async def test_mcp_send_auto_heals_known_placeholders():
    """Verify MCP send tool automatically replaces [Applicant Name] and [Phone Number] with Aman Mulla's data."""
    mock_backend_response = MagicMock()
    mock_backend_response.status_code = 200
    mock_backend_response.json.return_value = {
        "status": "sent",
        "recipient_email": "hr@innovyq.com",
        "attachments": [{"filename": "Aman_Mulla_Resume.pdf", "size_bytes": 316362}],
        "message": "Email sent."
    }

    raw_body = "Dear Team,\n\nI want to apply.\n\nBest regards,\n[Applicant Name]\n[Phone Number]"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_backend_response
        raw_result = await send_application_email(
            recipient_email="hr@innovyq.com",
            subject="Job Application",
            body=raw_body,
            approved=True,
        )
        result = json.loads(raw_result)
        assert result["status"] == "sent"
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        sent_body = kwargs["json"]["body"]
        assert "Aman Mulla" in sent_body
        assert "+91 9730971586" in sent_body
        assert "[Applicant Name]" not in sent_body


@pytest.mark.anyio
async def test_mcp_send_blocks_unresolved_placeholder():
    """Verify MCP send tool immediately blocks execution if unresolvable bracket placeholders are present."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        raw_result = await send_application_email(
            recipient_email="hr@innovyq.com",
            subject="Job Application",
            body="I will join on [Start Date].",
            approved=True,
        )
        result = json.loads(raw_result)
        assert result["status"] == "guardrail_blocked"
        assert result["approved"] is False
        assert "GUARDRAIL VIOLATION" in result["error"]
        assert "[Start Date]" in result["error"]
        mock_post.assert_not_called()
