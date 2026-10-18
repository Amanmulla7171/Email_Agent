from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check_endpoint():
    """Verify health check endpoint returns 200 and expected payload."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "email-agent-api"
    }


def test_draft_email_success():
    """Verify successful draft generation using a mocked LangGraph agent workflow."""
    mock_state = MagicMock()
    mock_state.values = {
        "subject": "Application for AI Engineer Internship",
        "body": "Dear Hiring Team,\n\nI am writing to express my strong interest in the AI Engineer Internship...",
        "recipient_name": "Hiring Team",
        "recipient_email": "hr@example.com",
    }

    with patch("app.services.email_agent_service.workflow.invoke") as mock_invoke, \
         patch("app.services.email_agent_service.workflow.get_state", return_value=mock_state):
        
        mock_invoke.return_value = {
            "__interrupt__": [
                MagicMock(value={
                    "subject": "Application for AI Engineer Internship",
                    "body": "Dear Hiring Team,\n\nI am writing to express my strong interest in the AI Engineer Internship...",
                })
            ]
        }

        payload = {
            "instruction": "Write an email applying for an AI Engineer internship.",
            "recipient_email": "hr@example.com",
            "job_description": "We are looking for an AI Engineer Intern skilled in Python and LangGraph.",
            "applicant_context": "My skills include Python, LangGraph, RAG and FastAPI."
        }

        response = client.post("/api/v1/email/draft", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "draft_created"
        assert data["recipient_email"] == "hr@example.com"
        assert data["subject"] == "Application for AI Engineer Internship"
        assert "Dear Hiring Team" in data["body"]
        assert data["requires_approval"] is True
        assert data["thread_id"] is not None


def test_apply_endpoint_success():
    """Verify /api/v1/email/apply workflow generates draft without sending."""
    mock_state = MagicMock()
    mock_state.values = {
        "subject": "Application for Senior Python Engineer",
        "body": "Dear Team,\n\nAttached is my background for the position...",
        "recipient_name": "Recruiter",
    }

    with patch("app.services.email_agent_service.workflow.invoke") as mock_invoke, \
         patch("app.services.email_agent_service.workflow.get_state", return_value=mock_state):

        mock_invoke.return_value = {
            "__interrupt__": [
                MagicMock(value={
                    "subject": "Application for Senior Python Engineer",
                    "body": "Dear Team,\n\nAttached is my background for the position...",
                })
            ]
        }

        payload = {
            "recipient_email": "recruiter@techcorp.com",
            "recipient_name": "Recruiter",
            "job_description": "We need an experienced Python and FastAPI engineer to lead backend architecture.",
            "applicant_context": "5 years of experience building Python services with FastAPI and LangGraph."
        }

        response = client.post("/api/v1/email/apply", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "draft_created"
        assert data["recipient_email"] == "recruiter@techcorp.com"
        assert data["requires_approval"] is True


def test_draft_missing_or_invalid_recipient():
    """Verify validation error when recipient_email is invalid or missing."""
    # Invalid email format
    response = client.post("/api/v1/email/draft", json={
        "instruction": "Say hello",
        "recipient_email": "not-an-email"
    })
    assert response.status_code == 422

    # Missing recipient_email
    response_missing = client.post("/api/v1/email/draft", json={
        "instruction": "Say hello"
    })
    assert response_missing.status_code == 422


def test_send_email_without_approval():
    """Verify that sending fails when approval is missing or false."""
    payload = {
        "recipient_email": "hr@example.com",
        "subject": "Application for AI Engineer Internship",
        "body": "Dear Hiring Team...",
        "approved": False
    }

    response = client.post("/api/v1/email/send", json=payload)
    assert response.status_code == 400
    assert "approval is required" in response.json()["detail"].lower()


def test_send_email_empty_subject_or_body():
    """Verify validation fails when subject or body is empty or whitespace."""
    # Blank subject
    resp1 = client.post("/api/v1/email/send", json={
        "recipient_email": "hr@example.com",
        "subject": "   ",
        "body": "Some body content",
        "approved": True
    })
    assert resp1.status_code == 422

    # Blank body
    resp2 = client.post("/api/v1/email/send", json={
        "recipient_email": "hr@example.com",
        "subject": "Valid Subject",
        "body": "   ",
        "approved": True
    })
    assert resp2.status_code == 422


def test_send_email_successful_mocked():
    """Verify sending works properly when approved and mailer succeeds, including default resume."""
    with patch("app.services.email_agent_service.send_email_via_smtp") as mock_smtp:
        mock_smtp.return_value = (True, "Email successfully sent to hr@example.com via smtp.gmail.com:587")

        payload = {
            "recipient_email": "hr@example.com",
            "subject": "Application for AI Engineer Internship",
            "body": "Dear Hiring Team,\n\nI am thrilled to apply...",
            "approved": True
        }

        response = client.post("/api/v1/email/send", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["recipient_email"] == "hr@example.com"
        assert len(data["attachments"]) == 1
        assert data["attachments"][0]["filename"] == "Aman_Mulla_Resume.pdf"
        assert data["attachments"][0]["attachment_id"] == "default_resume"
        mock_smtp.assert_called_once()
        _, kwargs = mock_smtp.call_args
        assert kwargs["attachments"] is not None
        assert kwargs["attachments"][0]["filename"] == "Aman_Mulla_Resume.pdf"


def test_send_email_provider_failure():
    """Verify that mailer failure returns HTTP 502 with clear error message."""
    with patch("app.services.email_agent_service.send_email_via_smtp") as mock_smtp:
        mock_smtp.return_value = (False, "SMTP Authentication Error: Bad credentials")

        payload = {
            "recipient_email": "hr@example.com",
            "subject": "Application for AI Engineer Internship",
            "body": "Dear Hiring Team...",
            "approved": True
        }

        response = client.post("/api/v1/email/send", json=payload)
        assert response.status_code == 502
        assert "SMTP Authentication Error" in response.json()["detail"]


def test_agent_execution_failure():
    """Verify clean 500 error when agent workflow fails unexpectedly."""
    with patch("app.services.email_agent_service.workflow.invoke", side_effect=Exception("Groq API Timeout")):
        payload = {
            "instruction": "Write an email applying for an internship.",
            "recipient_email": "hr@example.com",
        }

        response = client.post("/api/v1/email/draft", json=payload)
        assert response.status_code == 500
        assert "Error executing agent workflow" in response.json()["detail"]


def test_send_email_with_thread_id_resumes_workflow():
    """Verify that providing thread_id resumes paused LangGraph checkpoint."""
    mock_state = MagicMock()
    mock_state.next = ("review",)

    with patch("app.services.email_agent_service.workflow.get_state", return_value=mock_state), \
         patch("app.services.email_agent_service.workflow.invoke") as mock_invoke:

        mock_invoke.return_value = {
            "response": "Email sent successfully to Alex (hr@example.com) via SMTP."
        }

        payload = {
            "recipient_email": "hr@example.com",
            "subject": "Application for AI Engineer Internship",
            "body": "Dear Hiring Team...",
            "approved": True,
            "thread_id": "test-thread-1234"
        }

        response = client.post("/api/v1/email/send", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert "Email sent successfully" in data["message"]
        mock_invoke.assert_called_once()


def test_api_key_authentication_when_configured():
    """Verify endpoint enforces API key when API_SECRET_KEY is configured in settings."""
    from app.core.config import get_settings, Settings

    mock_settings = Settings(API_SECRET_KEY="super-secret-token")
    app.dependency_overrides[get_settings] = lambda: mock_settings

    try:
        with patch("app.services.email_agent_service.send_email_via_smtp", return_value=(True, "Success")):
            payload = {
                "recipient_email": "hr@example.com",
                "subject": "Application for AI Engineer",
                "body": "Dear Hiring Team...",
                "approved": True
            }

            # Request without header should be rejected
            unauth_resp = client.post("/api/v1/email/send", json=payload)
            assert unauth_resp.status_code == 401

            # Request with invalid header should be rejected
            invalid_resp = client.post("/api/v1/email/send", json=payload, headers={"X-API-Key": "wrong-key"})
            assert invalid_resp.status_code == 401

            # Request with valid header should proceed
            valid_resp = client.post("/api/v1/email/send", json=payload, headers={"X-API-Key": "super-secret-token"})
            assert valid_resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_upload_attachment_valid_pdf():
    """Verify uploading a valid PDF returns 201 with secure attachment_id."""
    import io
    pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    files = {"file": ("my_resume.pdf", io.BytesIO(pdf_content), "application/pdf")}
    response = client.post("/api/v1/email/attachments/upload", files=files)
    assert response.status_code == 201
    data = response.json()
    assert data["attachment_id"].startswith("att_")
    assert data["filename"] == "my_resume.pdf"
    assert data["content_type"] == "application/pdf"
    assert data["size_bytes"] == len(pdf_content)


def test_upload_attachment_invalid_extension():
    """Verify uploading forbidden file extensions returns 400 Bad Request."""
    import io
    bad_content = b"fake executable content"
    files = {"file": ("malicious.exe", io.BytesIO(bad_content), "application/octet-stream")}
    response = client.post("/api/v1/email/attachments/upload", files=files)
    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]


def test_upload_attachment_invalid_pdf_content():
    """Verify uploading non-PDF content with .pdf extension fails magic bytes check."""
    import io
    fake_content = b"Not a real PDF header"
    files = {"file": ("fake.pdf", io.BytesIO(fake_content), "application/pdf")}
    response = client.post("/api/v1/email/attachments/upload", files=files)
    assert response.status_code == 400
    assert "invalid PDF structure" in response.json()["detail"]


def test_upload_attachment_oversized():
    """Verify oversized attachment (>10MB) is rejected."""
    import io
    big_content = b"%PDF-1.4 " + (b"A" * (11 * 1024 * 1024))
    files = {"file": ("huge.pdf", io.BytesIO(big_content), "application/pdf")}
    response = client.post("/api/v1/email/attachments/upload", files=files)
    assert response.status_code == 413
    assert "exceeds the maximum allowed limit" in response.json()["detail"]


def test_upload_attachment_path_traversal_sanitized():
    """Verify path traversal sequences in filenames are safely sanitized."""
    import io
    pdf_content = b"%PDF-1.4\nsafe content"
    files = {"file": ("../../etc/passwd.pdf", io.BytesIO(pdf_content), "application/pdf")}
    response = client.post("/api/v1/email/attachments/upload", files=files)
    assert response.status_code == 201
    data = response.json()
    assert ".." not in data["filename"]
    assert "/" not in data["filename"]
    assert "\\" not in data["filename"]


def test_get_attachment_info():
    """Verify retrieving metadata for an existing attachment."""
    import io
    pdf_content = b"%PDF-1.4\ntest doc"
    files = {"file": ("portfolio.pdf", io.BytesIO(pdf_content), "application/pdf")}
    upload_resp = client.post("/api/v1/email/attachments/upload", files=files)
    att_id = upload_resp.json()["attachment_id"]

    get_resp = client.get(f"/api/v1/email/attachments/{att_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["attachment_id"] == att_id
    assert get_resp.json()["filename"] == "portfolio.pdf"


def test_get_attachment_info_not_found():
    """Verify 404 when attachment ID does not exist."""
    response = client.get("/api/v1/email/attachments/att_nonexistent12345")
    assert response.status_code == 404


def test_send_email_with_valid_uploaded_attachment():
    """Verify sending an email with an uploaded attachment passes it to the mailer."""
    import io
    pdf_content = b"%PDF-1.4\nresume payload"
    files = {"file": ("candidate_resume.pdf", io.BytesIO(pdf_content), "application/pdf")}
    upload_resp = client.post("/api/v1/email/attachments/upload", files=files)
    att_id = upload_resp.json()["attachment_id"]

    with patch("app.services.email_agent_service.send_email_via_smtp") as mock_smtp:
        mock_smtp.return_value = (True, "Email successfully sent to hr@example.com with attachments")

        payload = {
            "recipient_email": "hr@example.com",
            "subject": "Application with Resume Attached",
            "body": "Dear Hiring Team,\n\nPlease find my resume attached.",
            "approved": True,
            "attachment_ids": [att_id],
            "include_default_attachment": False,
        }

        response = client.post("/api/v1/email/send", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert len(data["attachments"]) == 1
        assert data["attachments"][0]["filename"] == "candidate_resume.pdf"

        # Verify mailer was called with attachments
        mock_smtp.assert_called_once()
        _, kwargs = mock_smtp.call_args
        assert kwargs["attachments"] is not None
        assert kwargs["attachments"][0]["filename"] == "candidate_resume.pdf"
        assert kwargs["attachments"][0]["content"] == pdf_content


def test_send_email_with_uploaded_and_default_resume():
    """Verify sending an email with an uploaded attachment also includes default resume when enabled."""
    import io
    pdf_content = b"%PDF-1.4\nportfolio payload"
    files = {"file": ("portfolio.pdf", io.BytesIO(pdf_content), "application/pdf")}
    upload_resp = client.post("/api/v1/email/attachments/upload", files=files)
    att_id = upload_resp.json()["attachment_id"]

    with patch("app.services.email_agent_service.send_email_via_smtp") as mock_smtp:
        mock_smtp.return_value = (True, "Email successfully sent with both attachments")

        payload = {
            "recipient_email": "hr@example.com",
            "subject": "Application with Portfolio and Resume",
            "body": "Dear Hiring Team,\n\nPlease find my portfolio and resume attached.",
            "approved": True,
            "attachment_ids": [att_id],
            "include_default_attachment": True,
        }

        response = client.post("/api/v1/email/send", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert len(data["attachments"]) == 2
        filenames = [a["filename"] for a in data["attachments"]]
        assert "portfolio.pdf" in filenames
        assert "Aman_Mulla_Resume.pdf" in filenames


def test_send_email_with_inline_base64_attachment():
    """Verify sending with inline base64 encoded document."""
    import base64
    raw_pdf = b"%PDF-1.4\nInline document test"
    b64_pdf = base64.b64encode(raw_pdf).decode()

    with patch("app.services.email_agent_service.send_email_via_smtp") as mock_smtp:
        mock_smtp.return_value = (True, "Email dispatched with base64 attachment")

        payload = {
            "recipient_email": "hr@example.com",
            "subject": "Application with Direct Base64",
            "body": "Dear Hiring Team...",
            "approved": True,
            "include_default_attachment": False,
            "attachments": [
                {
                    "filename": "cover_letter.pdf",
                    "content_base64": b64_pdf,
                    "content_type": "application/pdf"
                }
            ]
        }

        response = client.post("/api/v1/email/send", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data["attachments"]) == 1
        assert data["attachments"][0]["filename"] == "cover_letter.pdf"

        mock_smtp.assert_called_once()
        _, kwargs = mock_smtp.call_args
        assert kwargs["attachments"][0]["content"] == raw_pdf


def test_send_email_with_missing_attachment_id():
    """Verify sending fails with 404 when attachment ID does not exist."""
    payload = {
        "recipient_email": "hr@example.com",
        "subject": "Application with Bad Attachment",
        "body": "Dear Hiring Team...",
        "approved": True,
        "attachment_ids": ["att_invalidreference123"]
    }
    response = client.post("/api/v1/email/send", json=payload)
    assert response.status_code == 404
    assert "Attachment reference 'att_invalidreference123' not found" in response.json()["detail"]


def test_send_email_with_invalid_base64():
    """Verify sending fails with 400 when base64 is corrupt."""
    payload = {
        "recipient_email": "hr@example.com",
        "subject": "Application with Bad Base64",
        "body": "Dear Hiring Team...",
        "approved": True,
        "attachments": [
            {
                "filename": "corrupt.pdf",
                "content_base64": "!!!not_valid_base64!!!",
                "content_type": "application/pdf"
            }
        ]
    }
    response = client.post("/api/v1/email/send", json=payload)
    assert response.status_code == 400
    assert "Invalid base64 encoding" in response.json()["detail"]


def test_draft_includes_default_resume_by_default():
    """Verify drafting includes Aman_Mulla_Resume.pdf in attachments automatically."""
    mock_state = MagicMock()
    mock_state.values = {
        "subject": "Application for AI Engineer Role",
        "body": "Dear Hiring Manager, please find my resume attached.",
    }

    with patch("app.services.email_agent_service.workflow.invoke") as mock_invoke, \
         patch("app.services.email_agent_service.workflow.get_state", return_value=mock_state):

        mock_invoke.return_value = {
            "__interrupt__": [
                MagicMock(value={
                    "subject": "Application for AI Engineer Role",
                    "body": "Dear Hiring Manager, please find my resume attached.",
                })
            ]
        }

        payload = {
            "recipient_email": "recruiter@ai-startup.com",
            "instruction": "Draft job application email",
        }

        response = client.post("/api/v1/email/draft", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data["attachments"]) == 1
        assert data["attachments"][0]["filename"] == "Aman_Mulla_Resume.pdf"
        assert data["attachments"][0]["attachment_id"] == "default_resume"


def test_draft_excludes_default_resume_when_flag_false():
    """Verify drafting omits default resume when include_default_attachment is False."""
    mock_state = MagicMock()
    mock_state.values = {
        "subject": "Inquiry Email",
        "body": "Dear Team, quick inquiry without attachments.",
    }

    with patch("app.services.email_agent_service.workflow.invoke") as mock_invoke, \
         patch("app.services.email_agent_service.workflow.get_state", return_value=mock_state):

        mock_invoke.return_value = {
            "__interrupt__": [
                MagicMock(value={
                    "subject": "Inquiry Email",
                    "body": "Dear Team, quick inquiry without attachments.",
                })
            ]
        }

        payload = {
            "recipient_email": "info@example.com",
            "instruction": "Ask about opening",
            "include_default_attachment": False,
        }

        response = client.post("/api/v1/email/draft", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data["attachments"]) == 0


def test_workflow_checkpoint_records_attachment_status():
    """Verify review_node and sendnode properly track and report attachments in state."""
    from Email_agent.agent import EmailState, review_node, sendnode

    # State with attachments
    state_with_att = EmailState(
        recipient_name="KartAI Hiring Team",
        recipient_email="careers@kartai.com",
        subject="Internship Application",
        body="Please find my resume attached.",
        attachments=[{"filename": "Aman_Mulla_Resume.pdf", "content": b"%PDF-1.4 test"}],
        has_attachments=True,
        attachment_names=["Aman_Mulla_Resume.pdf"],
    )

    with patch("Email_agent.agent.interrupt") as mock_interrupt:
        mock_interrupt.return_value = "approve"
        res = review_node(state_with_att)
        assert res["feedback"] == "approved"
        # Verify interrupt was called with attachment checkpoint metadata
        interrupt_payload = mock_interrupt.call_args[0][0]
        assert interrupt_payload["has_attachments"] is True
        assert "Aman_Mulla_Resume.pdf" in interrupt_payload["attachment_names"]
        assert interrupt_payload["attachment_checkpoint_verified"] is True

    with patch("Email_agent.agent.send_email_via_smtp", return_value=(True, "Sent")) as mock_smtp:
        send_res = sendnode(state_with_att)
        assert send_res["has_attachments"] is True
        assert "Aman_Mulla_Resume.pdf" in send_res["attachment_names"]
        assert "Aman_Mulla_Resume.pdf" in send_res["response"]
        mock_smtp.assert_called_once()
        _, kwargs = mock_smtp.call_args
        assert kwargs["attachments"] is not None
        assert kwargs["attachments"][0]["filename"] == "Aman_Mulla_Resume.pdf"


def test_list_available_attachments_endpoint():
    """Verify GET /api/v1/email/attachments/available lists default resume and uploaded files."""
    response = client.get("/api/v1/email/attachments/available")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(item["filename"] == "Aman_Mulla_Resume.pdf" for item in data)
    default_item = next(item for item in data if item["filename"] == "Aman_Mulla_Resume.pdf")
    assert default_item["size_bytes"] == 316362
    assert default_item["content_type"] == "application/pdf"


def test_send_email_response_contains_delivery_scope_and_smtp_server():
    """Verify send response explicitly returns delivery_scope, smtp_server, and delivery_notice."""
    payload = {
        "recipient_email": "careers@4labsinc.com",
        "subject": "Application for Internship",
        "body": "Dear Hiring Team, please consider my application.",
        "approved": True,
        "include_default_attachment": True,
    }
    with patch("app.services.email_agent_service.send_email_via_smtp", return_value=(True, "Accepted by SMTP")):
        response = client.post("/api/v1/email/send", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["delivery_scope"] == "smtp_relay_accepted"
        assert "smtp.gmail.com" in data["smtp_server"]
        assert "SMTP confirms" in data["delivery_notice"]
        assert len(data["attachments"]) == 1
        assert data["attachments"][0]["filename"] == "Aman_Mulla_Resume.pdf"
