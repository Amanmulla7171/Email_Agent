import os
import logging
import uuid
from typing import Optional, Dict, Any, Tuple, List
from fastapi import HTTPException, status
from langgraph.types import Command

from Email_agent.agent import workflow
from Email_agent.mailer import send_email_via_smtp
from app.schemas.email import DraftEmailResponse, SendEmailResponse, AttachmentInfo
from app.core.attachments import resolve_all_attachments, load_attachment_by_id

logger = logging.getLogger("email_agent.service")


class EmailAgentService:
    """Service layer that orchestrates the LangGraph agent and email sending."""

    def __init__(self, agent_workflow=None, mailer_fn=None):
        self._workflow = agent_workflow
        self._mailer_fn = mailer_fn

    @property
    def workflow(self):
        return self._workflow if self._workflow is not None else workflow

    @workflow.setter
    def workflow(self, val):
        self._workflow = val

    @property
    def mailer_fn(self):
        return self._mailer_fn if self._mailer_fn is not None else send_email_via_smtp

    @mailer_fn.setter
    def mailer_fn(self, val):
        self._mailer_fn = val

    def _compose_prompt(
        self,
        instruction: Optional[str],
        recipient_email: str,
        recipient_name: Optional[str] = None,
        job_description: Optional[str] = None,
        applicant_context: Optional[str] = None,
        attachment_names: Optional[List[str]] = None,
    ) -> str:
        """Composes a natural-language request containing all context for retriever and drafter."""
        contact_name = recipient_name.strip() if recipient_name and recipient_name.strip() else "Hiring Team"

        default_profile_elements = (
            "Candidate: Aman Mulla, B.Tech CSE (AI-ML) student at DKTE, graduating in 2027.\n"
            "Target: Internship opportunities in AI/ML, Generative AI, or Software Engineering.\n"
            "Core Expertise: Python, LLMs, RAG, AI agents, LangChain, LangGraph, FastAPI, and workflow automation.\n"
            "Flagship Project: Project Mor, a multi-tenant AI agent and WhatsApp automation platform.\n"
            "Goal: Eager to contribute skills to real-world problems and ship production-ready features."
        )

        signature_block = (
            "Aman Mulla\n"
            "📧 amanmulla4020@gmail.com\n"
            "📱 +91 9730971586\n"
            "LinkedIn: https://www.linkedin.com/in/aman-mulla\n"
            "GitHub: https://github.com/amanmulla"
        )

        reasons = []
        if instruction and instruction.strip():
            reasons.append(f"Directive: {instruction.strip()}")
        if job_description and job_description.strip():
            reasons.append(f"Target Role / Company Details:\n{job_description.strip()}")

        active_applicant = applicant_context.strip() if applicant_context and applicant_context.strip() else default_profile_elements
        reasons.append(f"Applicant Details:\n{active_applicant}")

        if attachment_names:
            reasons.append(f"Attachments: {', '.join(attachment_names)} (attached for consideration).")

        combined_reason = "\n\n".join(reasons)

        prompt = (
            f"Draft a clean, direct, and compelling job application email to {contact_name} at {recipient_email}.\n"
            f"Recipient: {contact_name} <{recipient_email}>\n\n"
            f"Details & Context:\n{combined_reason}\n\n"
            "DESIRED EMAIL STYLE (Follow this proven, authentic structure):\n"
            "Paragraph 1: State clearly who you are: 'I’m Aman Mulla, a B.Tech CSE (AI-ML) student at DKTE, graduating in 2027. I’m looking for internship opportunities in AI/ML, Generative AI, or Software Engineering [tailor to role/company if specified].'\n"
            "Paragraph 2: Highlight hands-on experience: 'I have hands-on experience with Python, LLMs, RAG, AI agents, LangChain, LangGraph, FastAPI, and workflow automation. I've also built AI-powered applications, including Project Mor, a multi-tenant AI agent and WhatsApp automation platform.'\n"
            "Paragraph 3: Clear, humble call-to-action: 'I’d love to contribute my skills to your team and work on real-world problems. I’ve attached my resume for your consideration.'\n"
            "Paragraph 4: 'Thank you for your time!'\n\n"
            "RULES:\n"
            "- Keep the tone genuine, concise, and student-first (under 130 words).\n"
            "- NO placeholder brackets like [Applicant Name] or [Phone Number].\n"
            f"- Sign off exactly with:\nBest regards,\n{signature_block}"
        )
        return prompt



    def generate_draft(
        self,
        recipient_email: str,
        instruction: Optional[str] = None,
        recipient_name: Optional[str] = None,
        job_description: Optional[str] = None,
        applicant_context: Optional[str] = None,
        thread_id: Optional[str] = None,
        attachment_ids: Optional[List[str]] = None,
        attachments: Optional[List[Any]] = None,
        include_default_attachment: bool = True,
    ) -> DraftEmailResponse:
        """
        Invokes the existing LangGraph agent to generate a draft email.
        The workflow pauses at review_node with an interrupt, preventing automatic sending.
        """
        active_thread_id = thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": active_thread_id}}

        # Inspect and validate any attached documents (including default resume) to acknowledge in the draft
        resolved_attachments: List[Dict[str, Any]] = resolve_all_attachments(
            attachment_ids=attachment_ids,
            direct_attachments=attachments,
            include_default=include_default_attachment,
        )
        attachment_info_list: List[AttachmentInfo] = [
            AttachmentInfo(
                attachment_id=att.get("attachment_id"),
                filename=att["filename"],
                content_type=att.get("mime_type", "application/pdf"),
                size_bytes=att.get("size_bytes", 0),
            )
            for att in resolved_attachments
        ]

        attachment_names = [att["filename"] for att in resolved_attachments] if resolved_attachments else None

        question_prompt = self._compose_prompt(
            instruction=instruction,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            job_description=job_description,
            applicant_context=applicant_context,
            attachment_names=attachment_names,
        )

        try:
            # Initial invocation of the graph with Question and attachments in checkpoint
            initial_input = {
                "Question": question_prompt,
                "attachments": resolved_attachments,
                "has_attachments": bool(resolved_attachments),
                "attachment_names": [att["filename"] for att in resolved_attachments],
            }
            result = self.workflow.invoke(initial_input, config=config)

            # Check if interrupted
            interrupts = result.get("__interrupt__") if isinstance(result, dict) else None

            # Handle case where retriever node might have interrupted for missing info
            if interrupts and isinstance(interrupts, (list, tuple)) and len(interrupts) > 0:
                interrupt_val = getattr(interrupts[0], "value", interrupts[0])
                if isinstance(interrupt_val, dict) and "missing" in interrupt_val:
                    # Provide missing details to resume through retriever
                    resume_input = f"Recipient Name: {recipient_name or 'Hiring Team'}, Recipient Email: {recipient_email}, Reason: {instruction or 'Job Application'}"
                    result = self.workflow.invoke(Command(resume=resume_input), config=config)
                    interrupts = result.get("__interrupt__") if isinstance(result, dict) else None

            # Inspect state after drafting
            state_snapshot = self.workflow.get_state(config)
            state_values = state_snapshot.values if hasattr(state_snapshot, "values") else {}

            subject = state_values.get("subject")
            body = state_values.get("body")

            # Fallback to interrupt payload if state_values are empty
            if (not subject or not body) and interrupts:
                interrupt_val = getattr(interrupts[0], "value", interrupts[0])
                if isinstance(interrupt_val, dict):
                    subject = subject or interrupt_val.get("subject")
                    body = body or interrupt_val.get("body")

            if not subject or not body:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Agent workflow executed but failed to produce a valid subject and body.",
                )

            # Strict guardrail check: auto-heal any placeholders in drafted body
            from app.core.guardrails import enforce_email_guardrails
            body, _ = enforce_email_guardrails(body, recipient_name=recipient_name, auto_heal=True, strict_raise=False)

            return DraftEmailResponse(
                status="draft_created",
                recipient_email=recipient_email,
                recipient_name=recipient_name or state_values.get("recipient_name"),
                subject=subject,
                body=body,
                requires_approval=True,
                thread_id=active_thread_id,
                attachments=attachment_info_list,
            )

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("LangGraph agent execution error: %s", str(exc), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error executing agent workflow: {str(exc)}",
            )

    def send_email(
        self,
        recipient_email: str,
        subject: str,
        body: str,
        recipient_name: Optional[str] = None,
        approved: bool = False,
        thread_id: Optional[str] = None,
        attachment_ids: Optional[List[str]] = None,
        attachments: Optional[List[Any]] = None,
        include_default_attachment: bool = True,
    ) -> SendEmailResponse:
        """
        Validates approval, resolves attachments, and dispatches email using existing mailer.
        Never sends an email if approved is False.
        """
        if not approved:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Explicit approval is required before sending an email. Set approved=true.",
            )

        if not subject or not subject.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email subject cannot be empty.",
            )

        if not body or not body.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email body cannot be empty.",
            )

        # STRICT GUARDRAIL: Auto-heal known placeholders and reject unresolved ones
        from app.core.guardrails import enforce_email_guardrails
        try:
            body, guardrail_subs = enforce_email_guardrails(
                body=body,
                recipient_name=recipient_name,
                auto_heal=True,
                strict_raise=True
            )
            if guardrail_subs:
                logger.info("Guardrails auto-healed placeholders in outgoing email: %s", ", ".join(guardrail_subs))
        except ValueError as ve:
            logger.error("Email send blocked by strict guardrail: %s", str(ve))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(ve),
            )

        # Resolve attachments securely (including default resume by default)
        resolved_attachments: List[Dict[str, Any]] = resolve_all_attachments(
            attachment_ids=attachment_ids,
            direct_attachments=attachments,
            include_default=include_default_attachment,
        )

        attachment_info_list = [
            AttachmentInfo(
                attachment_id=a.get("attachment_id"),
                filename=a["filename"],
                content_type=a.get("mime_type", "application/pdf"),
                size_bytes=a.get("size_bytes", 0),
            )
            for a in resolved_attachments
        ]

        smtp_server_str = f"{os.environ.get('SMTP_SERVER', 'smtp.gmail.com')}:{os.environ.get('SMTP_PORT', 587)}"
        # If a thread_id was provided and checkpoint has paused state, resume the LangGraph workflow
        if thread_id:
            try:
                config = {"configurable": {"thread_id": thread_id}}
                state_snapshot = self.workflow.get_state(config)
                if state_snapshot and state_snapshot.next:
                    # Workflow is waiting at review_node interrupt, update attachments in state and resume
                    if resolved_attachments:
                        self.workflow.update_state(config, {
                            "attachments": resolved_attachments,
                            "has_attachments": bool(resolved_attachments),
                            "attachment_names": [a["filename"] for a in resolved_attachments],
                        })
                    resume_result = self.workflow.invoke(Command(resume="approve"), config=config)
                    final_response = resume_result.get("response", "") if isinstance(resume_result, dict) else ""
                    if "failed" in final_response.lower():
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Email delivery failed: {final_response}",
                        )
                    return SendEmailResponse(
                        status="sent",
                        delivery_scope="smtp_relay_accepted",
                        smtp_server=smtp_server_str,
                        message=final_response or f"Email successfully sent to {recipient_email}",
                        recipient_email=recipient_email,
                        recipient_name=recipient_name,
                        attachments=attachment_info_list,
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning("Attempt to resume graph thread %s failed (%s). Falling back to direct mailer.", thread_id, str(e))

        # Direct dispatch via existing mailer function
        try:
            success, message = self.mailer_fn(
                to_email=recipient_email,
                subject=subject.strip(),
                body=body.strip(),
                recipient_name=recipient_name,
                attachments=resolved_attachments if resolved_attachments else None,
            )
        except Exception as exc:
            logger.error("Mailer exception occurred: %s", str(exc), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to communicate with mail service: {str(exc)}",
            )

        if not success:
            logger.error("Mailer returned failure: %s", message)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Email delivery failed: {message}",
            )

        return SendEmailResponse(
            status="sent",
            delivery_scope="smtp_relay_accepted",
            smtp_server=smtp_server_str,
            message=message,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            attachments=attachment_info_list,
        )


# Global singleton instance
email_service = EmailAgentService()
