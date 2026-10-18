"""
MCP Server for LangGraph AI Email Agent.

Exposes tools to AI clients (ChatGPT, Claude, Cursor, Antigravity) via Model Context Protocol (MCP)
using Streamable HTTP transport, with secure attachment handling.
"""

import os
import sys
import json
import logging
from typing import Optional, Dict, Any, List
import httpx
from dotenv import load_dotenv

# Compatibility import for FastMCP across MCP SDK versions
try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.mcpserver import MCPServer as FastMCP

load_dotenv()

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mcp_server")

# Configuration from environment
EMAIL_API_BASE_URL = os.environ.get("EMAIL_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
EMAIL_API_KEY = os.environ.get("EMAIL_API_KEY") or os.environ.get("API_SECRET_KEY")
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", 8001))
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "streamable-http")
REQUEST_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", 60.0))

# Initialize FastMCP / MCPServer instance
mcp = FastMCP("Email-Agent-MCP")


def _get_api_headers() -> Dict[str, str]:
    """Prepares HTTP headers including optional authorization token."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    if EMAIL_API_KEY:
        headers["X-API-Key"] = EMAIL_API_KEY
    return headers


@mcp.tool(
    name="draft_application_email",
    description=(
        "Drafts an authentic, high-impact job application email using the LangGraph AI Email Agent. "
        "Returns the generated subject, body, attachment references, and thread_id for human review.\n\n"
        "APPLICANT PROFILE & TARGET FORMAT:\n"
        "- Candidate: Aman Mulla, B.Tech CSE (AI-ML) student at DKTE, graduating in 2027.\n"
        "- Target Roles: Internship opportunities in AI/ML, Generative AI, or Software Engineering.\n"
        "- Hands-on Experience: Python, LLMs, RAG, AI agents, LangChain, LangGraph, FastAPI, and workflow automation.\n"
        "- Flagship Project: Project Mor, a multi-tenant AI agent and WhatsApp automation platform.\n"
        "- Standard Structure:\n"
        "  Dear [Hiring Team / Recruiter Name],\n"
        "  I’m Aman Mulla, a B.Tech CSE (AI-ML) student at DKTE, graduating in 2027. I’m looking for internship opportunities in AI/ML, Generative AI, or Software Engineering.\n"
        "  I have hands-on experience with Python, LLMs, RAG, AI agents, LangChain, LangGraph, FastAPI, and workflow automation. I've also built AI-powered applications, including Project Mor, a multi-tenant AI agent and WhatsApp automation platform.\n"
        "  I’d love to contribute my skills to your team and work on real-world problems. I’ve attached my resume for your consideration.\n"
        "  Thank you for your time!\n\n"
        "  Best regards,\n"
        "  Aman Mulla\n"
        "  📧 amanmulla4020@gmail.com\n"
        "  📱 +91 9730971586\n"
        "  LinkedIn: https://www.linkedin.com/in/aman-mulla\n"
        "  GitHub: https://github.com/amanmulla\n\n"
        "ATTACHMENT SUPPORT: Aman Mulla's resume PDF ('Aman_Mulla_Resume.pdf') is attached by default.\n"
        "STRICT CONTENT GUARDRAIL: Under NO circumstances should placeholder brackets like [Applicant Name], [Phone Number], or [Your Name] be output.\n"
        "CRITICAL: This tool NEVER sends the email. It only creates a draft for human review and approval."
    )
)

async def draft_application_email(
    recipient_email: str,
    instruction: Optional[str] = "Write a tailored application email for the role.",
    job_description: Optional[str] = None,
    applicant_context: Optional[str] = None,
    recipient_name: Optional[str] = None,
    attachment: Optional[str] = None,
    attachments: Optional[Any] = None,
    attachment_ids: Optional[List[str]] = None,
    attach_resume: bool = True,
    include_default_attachment: bool = True,
) -> str:

    """
    Drafts an email via the FastAPI backend without sending.

    Args:
        recipient_email: Destination email address (e.g. hr@company.com).
        instruction: Natural language directive describing tone, intent, or specific points.
        job_description: Job description, requirements, or vacancy text.
        applicant_context: Candidate background, key skills, experience, or resume highlights.
        recipient_name: Optional recruiter or hiring manager name.
        attachment: Optional single attachment filename (e.g. 'Aman_Mulla_Resume.pdf') or attachment reference ID.
        attachments: Optional list or dictionary of attachments.
        attachment_ids: Optional list of previously uploaded attachment IDs.
        attach_resume: Whether to attach Aman Mulla's resume PDF. Defaults to True.
        include_default_attachment: Whether to attach default resume. Defaults to True.

    Returns:
        JSON string containing the drafted subject, body, attachments, and requires_approval status.
    """
    attach_default = include_default_attachment and attach_resume
    resolved_attachment_ids = list(attachment_ids) if attachment_ids else []

    if attachment:
        if attachment.strip().lower() in ("aman_mulla_resume.pdf", "resume.pdf", "resume", "default_resume"):
            attach_default = True
        else:
            resolved_attachment_ids.append(attachment.strip())

    if attachments:
        if isinstance(attachments, str):
            if attachments.strip().lower() in ("aman_mulla_resume.pdf", "resume.pdf", "resume", "default_resume"):
                attach_default = True
            else:
                resolved_attachment_ids.append(attachments.strip())
        elif isinstance(attachments, list):
            for item in attachments:
                if isinstance(item, str):
                    if item.strip().lower() in ("aman_mulla_resume.pdf", "resume.pdf", "resume", "default_resume"):
                        attach_default = True
                    else:
                        resolved_attachment_ids.append(item.strip())

    url = f"{EMAIL_API_BASE_URL}/api/v1/email/draft"
    payload = {
        "recipient_email": recipient_email.strip(),
        "instruction": instruction.strip() if instruction else None,
        "job_description": job_description.strip() if job_description else None,
        "applicant_context": applicant_context.strip() if applicant_context else None,
        "recipient_name": recipient_name.strip() if recipient_name else None,
        "attachment_ids": resolved_attachment_ids if resolved_attachment_ids else None,
        "include_default_attachment": attach_default,
    }

    logger.info("Calling FastAPI backend to draft email for %s...", recipient_email)
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=_get_api_headers())

            if response.status_code == 200:
                data = response.json()
                logger.info("Draft successfully created for %s", recipient_email)
                return json.dumps({
                    "status": data.get("status", "draft_created"),
                    "recipient_email": data.get("recipient_email"),
                    "recipient_name": data.get("recipient_name"),
                    "subject": data.get("subject"),
                    "body": data.get("body"),
                    "attachments": data.get("attachments", []),
                    "requires_approval": True,
                    "thread_id": data.get("thread_id"),
                    "notice": "Draft prepared. User must explicitly confirm approval before send_application_email is called."
                }, indent=2)

            error_msg = f"FastAPI backend returned HTTP {response.status_code}: {response.text}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg, "status_code": response.status_code})

    except httpx.ConnectError:
        err = f"Failed to connect to Email Agent API at {url}. Ensure the FastAPI server is running."
        logger.error(err)
        return json.dumps({"error": err})
    except httpx.TimeoutException:
        err = "Request timed out while waiting for LangGraph agent response."
        logger.error(err)
        return json.dumps({"error": err})
    except Exception as exc:
        err = f"Unexpected error while drafting email: {str(exc)}"
        logger.error(err, exc_info=True)
        return json.dumps({"error": err})


@mcp.tool(
    name="list_available_attachments",
    description=(
        "Lists all verified documents and resumes stored on the server available for email attachment. "
        "Returns filenames (e.g. 'Aman_Mulla_Resume.pdf'), file sizes in bytes, and MIME types. "
        "Use this tool to inspect available files and obtain exact filenames before drafting or sending."
    )
)
async def list_available_attachments() -> str:
    """
    Fetches the list of verified attachments available on the server.

    Returns:
        JSON string containing the list of available attachments with filename, size, and content type.
    """
    url = f"{EMAIL_API_BASE_URL}/api/v1/email/attachments/available"
    logger.info("Calling FastAPI backend to list available attachments...")
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(url, headers=_get_api_headers())
            if response.status_code == 200:
                data = response.json()
                return json.dumps({
                    "status": "success",
                    "available_attachments": data,
                    "count": len(data),
                    "default_resume": "Aman_Mulla_Resume.pdf",
                    "instruction": "You can explicitly pass any of these filenames to 'draft_application_email' or 'send_application_email' via the 'attachment' or 'attachments' parameters."
                }, indent=2)

            error_msg = f"FastAPI backend returned HTTP {response.status_code}: {response.text}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg, "status_code": response.status_code})

    except httpx.ConnectError:
        # Graceful fallback if backend connection drops
        logger.warning("Could not reach backend /attachments/available, returning local verified default.")
        return json.dumps({
            "status": "fallback",
            "available_attachments": [
                {
                    "filename": "Aman_Mulla_Resume.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 316362,
                    "is_default": True
                }
            ],
            "count": 1,
            "instruction": "Aman_Mulla_Resume.pdf is available on the server."
        }, indent=2)
    except Exception as exc:
        err = f"Unexpected error while listing attachments: {str(exc)}"
        logger.error(err, exc_info=True)
        return json.dumps({"error": err})


@mcp.tool(
    name="send_application_email",
    description=(
        "Sends an approved email with PDF attachments (such as Aman Mulla's resume) to the recipient via SMTP through the Email Agent backend.\n"
        "MANDATORY FORMAT: All emails sent on behalf of Aman Mulla must adhere to this concise, student-first format:\n"
        "Dear [Hiring Team / Recruiter Name],\n"
        "I’m Aman Mulla, a B.Tech CSE (AI-ML) student at DKTE, graduating in 2027. I’m looking for internship opportunities in AI/ML, Generative AI, or Software Engineering.\n"
        "I have hands-on experience with Python, LLMs, RAG, AI agents, LangChain, LangGraph, FastAPI, and workflow automation. I've also built AI-powered applications, including Project Mor, a multi-tenant AI agent and WhatsApp automation platform.\n"
        "I’d love to contribute my skills to your team and work on real-world problems. I’ve attached my resume for your consideration.\n"
        "Thank you for your time!\n\n"
        "Best regards,\n"
        "Aman Mulla\n"
        "📧 amanmulla4020@gmail.com\n"
        "📱 +91 9730971586\n"
        "LinkedIn: https://www.linkedin.com/in/aman-mulla\n"
        "GitHub: https://github.com/amanmulla\n\n"
        "ATTACHMENTS FULLY SUPPORTED: Supports 'attachment', 'attachments', and 'attach_resume'. "
        "By default, the applicant's resume PDF ('Aman_Mulla_Resume.pdf', 316,362 bytes) is attached via SMTP. "
        "STRICT CONTENT GUARDRAIL: Outgoing emails must NEVER contain placeholder brackets like [Applicant Name], "
        "[Phone Number], [LinkedIn Profile], etc. All applicant details must be real and concrete: Aman Mulla, "
        "amanmulla4020@gmail.com, +91 9730971586, LinkedIn: https://www.linkedin.com/in/aman-mulla. "
        "Server guardrails will automatically heal recognized placeholders and reject any unresolved ones. "
        "SAFETY REQUIREMENT: You MUST ask the human user for explicit approval and present the "
        "recipient, subject, body, and attached files before calling this tool. "
        "The parameter 'approved' must be explicitly True, or sending will be aborted."
    )
)
async def send_application_email(
    recipient_email: str,
    subject: str,
    body: str,
    approved: bool = False,
    recipient_name: Optional[str] = None,
    thread_id: Optional[str] = None,
    attachment: Optional[str] = None,
    attachments: Optional[Any] = None,
    attachment_ids: Optional[List[str]] = None,
    attach_resume: bool = True,
    include_default_attachment: bool = True,
) -> str:
    """
    Sends an email after explicit user confirmation.

    Args:
        recipient_email: Destination email address.
        subject: Final email subject line.
        body: Final email body text.
        approved: Must be explicitly True. If False, sending is aborted immediately.
        recipient_name: Optional recipient name.
        thread_id: Optional LangGraph checkpoint thread ID from the draft step.
        attachment: Optional single attachment filename (e.g. 'Aman_Mulla_Resume.pdf'), path, or attachment ID.
        attachments: Optional list of attachment filenames, IDs, or base64 dicts.
        attachment_ids: Optional list of validated attachment IDs previously uploaded.
        attach_resume: Whether to attach Aman Mulla's resume PDF (Aman_Mulla_Resume.pdf). Defaults to True.
        include_default_attachment: Whether to attach default resume. Defaults to True.

    Returns:
        JSON string confirming delivery status or reporting an error.
    """
    # STRICT GUARDRAIL: Auto-heal known placeholders and reject unresolved ones
    try:
        from app.core.guardrails import enforce_email_guardrails
        body, guardrail_actions = enforce_email_guardrails(
            body=body,
            recipient_name=recipient_name,
            auto_heal=True,
            strict_raise=True
        )
        if guardrail_actions:
            logger.info("Guardrails applied to email body: %s", ", ".join(guardrail_actions))
    except ValueError as ve:
        logger.warning("Email rejected by guardrails: %s", str(ve))
        return json.dumps({
            "status": "guardrail_blocked",
            "approved": False,
            "error": str(ve),
            "instruction": "Email rejected because it contains unpopulated placeholder brackets. Populate all real applicant details before sending."
        }, indent=2)

    attach_default = include_default_attachment and attach_resume
    resolved_attachment_ids = list(attachment_ids) if attachment_ids else []
    resolved_attachments_payload = []

    if attachment:
        if attachment.strip().lower() in ("aman_mulla_resume.pdf", "resume.pdf", "resume", "default_resume"):
            attach_default = True

        else:
            resolved_attachment_ids.append(attachment.strip())

    if attachments:
        if isinstance(attachments, str):
            if attachments.strip().lower() in ("aman_mulla_resume.pdf", "resume.pdf", "resume", "default_resume"):
                attach_default = True
            else:
                resolved_attachment_ids.append(attachments.strip())
        elif isinstance(attachments, list):
            for item in attachments:
                if isinstance(item, str):
                    if item.strip().lower() in ("aman_mulla_resume.pdf", "resume.pdf", "resume", "default_resume"):
                        attach_default = True
                    else:
                        resolved_attachment_ids.append(item.strip())
                elif isinstance(item, dict):
                    resolved_attachments_payload.append(item)

    # Collect attachment filenames and details for review
    att_filenames = []
    att_details = []
    if resolved_attachment_ids:
        for aid in resolved_attachment_ids:
            att_filenames.append(aid)
            att_details.append({"filename": aid, "reference": aid})
    if resolved_attachments_payload:
        for att in resolved_attachments_payload:
            if isinstance(att, dict) and "filename" in att:
                att_filenames.append(att["filename"])
                att_details.append({
                    "filename": att["filename"],
                    "content_type": att.get("content_type", "application/pdf")
                })
    if attach_default and not any("Aman_Mulla_Resume.pdf" in f for f in att_filenames):
        att_filenames.append("Aman_Mulla_Resume.pdf (default resume)")
        att_details.append({
            "filename": "Aman_Mulla_Resume.pdf",
            "size_bytes": 316362,
            "content_type": "application/pdf",
            "is_default_resume": True
        })

    smtp_server_label = os.environ.get("SMTP_SERVER", "smtp.gmail.com") + ":" + str(os.environ.get("SMTP_PORT", 587))

    if not approved:
        att_list_str = ", ".join(att_filenames) if att_filenames else "None"
        msg = (
            "SAFETY ABORT: Email was NOT sent because 'approved' is False or missing. "
            "Please review the details below with the user and obtain explicit confirmation before proceeding:\n"
            f"- To: {recipient_email}\n"
            f"- Subject: {subject}\n"
            f"- Attachments: {att_list_str}\n"
            f"- SMTP Relay: {smtp_server_label}\n"
            f"- Body snippet: {body[:150]}..."
        )
        logger.warning("Send blocked: approval is false for %s", recipient_email)
        return json.dumps({
            "status": "blocked",
            "message": msg,
            "approved": False,
            "review": {
                "recipient": recipient_email,
                "recipient_name": recipient_name,
                "subject": subject,
                "attachments": att_filenames,
                "attachment_details": att_details,
                "smtp_relay": smtp_server_label,
                "body_preview": body[:300] + ("..." if len(body) > 300 else ""),
            },
            "instruction": "Present the recipient, subject, attachments, and body preview to the user. Do NOT call send_application_email with approved=True until the user explicitly agrees."
        }, indent=2)

    url = f"{EMAIL_API_BASE_URL}/api/v1/email/send"
    payload = {
        "recipient_email": recipient_email.strip(),
        "subject": subject.strip(),
        "body": body.strip(),
        "approved": True,
        "recipient_name": recipient_name.strip() if recipient_name else None,
        "thread_id": thread_id,
        "attachment_ids": resolved_attachment_ids if resolved_attachment_ids else None,
        "attachments": resolved_attachments_payload if resolved_attachments_payload else None,
        "include_default_attachment": attach_default,
    }

    logger.info("Calling FastAPI backend to send email to %s (attachments: %d)...", recipient_email, len(att_filenames))
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=_get_api_headers())

            if response.status_code == 200:
                data = response.json()
                logger.info("Email dispatched successfully to %s", recipient_email)
                return json.dumps({
                    "status": "sent",
                    "delivery_scope": data.get("delivery_scope", "smtp_relay_accepted"),
                    "smtp_server": data.get("smtp_server", smtp_server_label),
                    "recipient_email": data.get("recipient_email"),
                    "recipient_name": data.get("recipient_name"),
                    "subject": subject,
                    "reported_attachments": data.get("attachments", []),
                    "attachments": data.get("attachments", []),
                    "message": data.get("message", "Email successfully accepted by SMTP server."),
                    "delivery_notice": data.get(
                        "delivery_notice",
                        f"Email accepted by SMTP relay ({smtp_server_label}). SMTP confirms transmission to relay; final inbox placement depends on recipient mail server policies."
                    ),
                }, indent=2)

            error_msg = f"FastAPI backend failed to send email (HTTP {response.status_code}): {response.text}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg, "status_code": response.status_code})

    except httpx.ConnectError:
        err = f"Failed to connect to Email Agent API at {url}. Ensure the FastAPI server is running."
        logger.error(err)
        return json.dumps({"error": err})
    except httpx.TimeoutException:
        err = "Request timed out while connecting to SMTP mail service."
        logger.error(err)
        return json.dumps({"error": err})
    except Exception as exc:
        err = f"Unexpected error while sending email: {str(exc)}"
        logger.error(err, exc_info=True)
        return json.dumps({"error": err})



def run_server():
    """Runs the MCP server with the configured transport."""
    transport = MCP_TRANSPORT.lower()

    # Allow command line overrides (e.g. python mcp_server.py --transport stdio)
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1].lower()

    logger.info("Starting Email Agent MCP Server on %s:%d using '%s' transport...", MCP_HOST, MCP_PORT, transport)
    logger.info("Connecting to FastAPI backend at: %s", EMAIL_API_BASE_URL)

    if transport == "streamable-http":
        mcp.run(transport="streamable-http", host=MCP_HOST, port=MCP_PORT)
    elif transport == "sse":
        mcp.run(transport="sse", host=MCP_HOST, port=MCP_PORT)
    elif transport == "stdio":
        mcp.run(transport="stdio")
    else:
        logger.error("Unknown transport: %s. Expected 'streamable-http', 'sse', or 'stdio'.", transport)
        sys.exit(1)


if __name__ == "__main__":
    run_server()
