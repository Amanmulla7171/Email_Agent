import os
import sys

# Ensure UTF-8 console output on Windows so emojis do not crash print statements
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from typing import Optional, Literal
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

# Load environment variables
load_dotenv()

# Initialize Groq LLM
groq_api_key = os.environ.get("groq_api_key") or os.environ.get("GROQ_API_KEY")
llm = ChatGroq(
    model_name="qwen/qwen3.8-27b",
    groq_api_key=groq_api_key,
    temperature=0.6,
    max_tokens=900,
)



def load_default_attachments() -> list:
    """Loads default resume attachment from disk if present."""
    default_candidates = [
        os.path.join("storage", "default_attachments", "Aman_Mulla_Resume.pdf"),
        os.path.join(os.path.dirname(__file__), "..", "storage", "default_attachments", "Aman_Mulla_Resume.pdf"),
        os.environ.get("DEFAULT_ATTACHMENT_PATH", "storage/default_attachments/Aman_Mulla_Resume.pdf"),
    ]
    for p in default_candidates:
        if p and os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    content_bytes = f.read()
                filename = os.path.basename(p)
                return [{
                    "attachment_id": "default_resume",
                    "filename": filename,
                    "content": content_bytes,
                    "mime_type": "application/pdf" if filename.lower().endswith(".pdf") else "application/octet-stream",
                    "size_bytes": len(content_bytes),
                    "is_default": True
                }]
            except Exception as e:
                print(f"[ATTACHMENT WARNING] Failed to read {p}: {e}")
    return []


# ----------------- State & Schemas -----------------

class EmailState(BaseModel):
    """Overall state for the email assistant workflow."""
    Question: Optional[str] = Field(default=None, description="The user's initial prompt or instructions")
    mail_reason: Optional[str] = Field(default=None, description="The reason / intent of the mail")
    recipient_name: Optional[str] = Field(default=None, description="Name of the recipient")
    recipient_email: Optional[str] = Field(default=None, description="Email address of the recipient")
    subject: Optional[str] = Field(default=None, description="Subject line of the email")
    body: Optional[str] = Field(default=None, description="Body content of the email")
    feedback: Optional[str] = Field(default=None, description="Human reviewer feedback or approval")
    feedback_count: int = Field(default=0, description="Counter for rewrite cycles")
    attachments: Optional[list] = Field(default=None, description="List of validated attachment files or metadata")
    has_attachments: bool = Field(default=False, description="Explicit checkpoint flag indicating if attachments are attached")
    attachment_names: list = Field(default_factory=list, description="List of attachment filenames in checkpoint")
    response: Optional[str] = Field(default=None, description="Final status message of the workflow")


class useroutput(BaseModel):
    """Structured extraction of user input details."""
    mail_reason: Optional[str] = Field(default=None, description="The reason for sending the mail")
    recipient_name: Optional[str] = Field(default=None, description="The name of the recipient")
    recipient_email: Optional[str] = Field(default=None, description="The email address of the recipient")


class draft_Email(BaseModel):
    """Structured draft output for subject and body."""
    subject: str = Field(description="Subject of the email")
    body: str = Field(description="Body of the email")


# ----------------- Nodes -----------------

def retriver(state: EmailState) -> dict:
    """Extracts recipient details and intent from user prompt, interrupting if info is missing."""
    llm_extractor = llm.with_structured_output(useroutput)
    prompt = (
        f"Extract recipient name, recipient email, and email reason from the request.\n"
        f"Request: {state.Question}"
    )
    details: useroutput = llm_extractor.invoke(prompt)

    missing = []
    if not details.recipient_name:
        missing.append("recipient_name")
    if not details.recipient_email:
        missing.append("recipient_email")
    if not details.mail_reason:
        missing.append("mail_reason")

    if missing:
        user_input = interrupt({
            "message": f"Missing information ({', '.join(missing)}). Please provide the missing details:",
            "missing": missing
        })
        followup_prompt = (
            f"Original request: {state.Question}\n"
            f"Additional user input: {user_input}\n"
            f"Extract recipient name, recipient email, and email reason."
        )
        details = llm_extractor.invoke(followup_prompt)

    return {
        "mail_reason": details.mail_reason,
        "recipient_name": details.recipient_name,
        "recipient_email": details.recipient_email,
    }


import random

DRAFTING_STRATEGIES = [
    {
        "style": "Project-Led & Tangible Impact",
        "instruction": (
            "- Open by spotlighting a concrete technical system you built (e.g. an automated WhatsApp AI platform or a production RAG pipeline using FastAPI).\n"
            "- Connect how your experience shipping production tools helps their team execute faster.\n"
            "- Tone: Practical builder, proactive and concise."
        )
    },
    {
        "style": "Direct Technical Match",
        "instruction": (
            "- Start directly with your technical identity (AI/Backend engineer experienced in Python, FastAPI, and LangGraph agentic systems).\n"
            "- Emphasize having 3 prior internships and being ready to contribute production-ready code immediately.\n"
            "- Tone: Direct, punchy, respectful of their time (under 140 words)."
        )
    },
    {
        "style": "Problem-Solving & Value-First",
        "instruction": (
            "- Open with a focus on solving engineering bottlenecks (e.g. automated issue triage like BugImpact AI, API optimization, or intelligent workflows).\n"
            "- Explain why their engineering challenges excite you and how you can support their roadmap.\n"
            "- Tone: Analytical, solution-oriented, collaborative."
        )
    },
    {
        "style": "Architecture & Scalability",
        "instruction": (
            "- Focus on modern AI backend architecture: combining FastAPI REST APIs with LLM agents and vector retrieval.\n"
            "- Highlight your passion for clean design, reliability, and fast iteration.\n"
            "- Tone: Confident, technically sharp."
        )
    }
]


def draft_node(state: EmailState) -> dict:
    """Drafts or rewrites the email based on details and any feedback received."""
    llm_drafter = llm.with_structured_output(draft_Email)

    strategy = random.choice(DRAFTING_STRATEGIES)

    revision_context = ""
    if state.feedback and state.feedback.lower() != "approved":
        revision_context = (
            f"\n\nUser Revision Request: {state.feedback}\n"
            f"Previous Subject: {state.subject}\n"
            f"Previous Body: {state.body}\n"
            "Please revise the email according to the user's feedback."
        )

    prompt = (
        f"Please draft a professional, concise, and authentic job application email to {state.recipient_name} at {state.recipient_email}.\n"
        f"To: {state.recipient_name} ({state.recipient_email})\n"
        f"Request/Reason: {state.mail_reason}\n"
        f"{revision_context}\n\n"
        "TARGET EMAIL FORMAT & STYLE (Follow this exact structure):\n"
        "Dear [Recipient Name or Hiring Team],\n"
        "I’m Aman Mulla, a B.Tech CSE (AI-ML) student at DKTE, graduating in 2027. I’m looking for internship opportunities in AI/ML, Generative AI, or Software Engineering.\n\n"
        "I have hands-on experience with Python, LLMs, RAG, AI agents, LangChain, LangGraph, FastAPI, and workflow automation. I've also built AI-powered applications, including Project Mor, a multi-tenant AI agent and WhatsApp automation platform.\n\n"
        "I’d love to contribute my skills to your team and work on real-world problems. I’ve attached my resume for your consideration.\n\n"
        "Thank you for your time!\n\n"
        "Best regards,\n"
        "Aman Mulla\n"
        "📧 amanmulla4020@gmail.com\n"
        "📱 +91 9730971586\n"
        "LinkedIn: https://www.linkedin.com/in/aman-mulla\n"
        "GitHub: https://github.com/amanmulla\n\n"
        "Formatting & Quality Requirements:\n"
        "- Tailor naturally to the specific role or company if mentioned in Request/Reason, but preserve this crisp, direct, student-first style.\n"
        "- Keep the email under 130 words with clean paragraph breaks (double newlines).\n"
        "- CRITICAL GUARDRAIL: Under NO circumstances should placeholder brackets like [Applicant Name], [Your Name], [Phone Number], [LinkedIn Profile], or [Date] be output.\n"
        "- Sign-off and signature block MUST include the emojis 📧 and 📱 as shown above."
    )
    draft_res: draft_Email = llm_drafter.invoke(prompt)



    clean_body = draft_res.body
    try:
        from app.core.guardrails import enforce_email_guardrails, APPLICANT_SIGNATURE_BLOCK
        clean_body, _ = enforce_email_guardrails(clean_body, recipient_name=state.recipient_name, auto_heal=True, strict_raise=False)

        cta_block = "I’d love to contribute my skills to your team and work on real-world problems. I’ve attached my resume for your consideration.\n\nThank you for your time!"

        # Normalize and complete call-to-action if cut off
        if "Best regards" in clean_body:
            body_prefix, _ = clean_body.split("Best regards", 1)
            if "I’d love to contribute" in body_prefix and "attached my resume" not in body_prefix:
                idx = body_prefix.find("I’d love to contribute")
                body_prefix = body_prefix[:idx].strip() + "\n\n" + cta_block
            elif "attached my resume" not in body_prefix:
                body_prefix = body_prefix.strip() + "\n\n" + cta_block
            clean_body = body_prefix.strip() + "\n\nBest regards,\n" + APPLICANT_SIGNATURE_BLOCK
        else:
            if "I’d love to contribute" in clean_body and "attached my resume" not in clean_body:
                idx = clean_body.find("I’d love to contribute")
                clean_body = clean_body[:idx].strip() + "\n\n" + cta_block
            elif "attached my resume" not in clean_body:
                clean_body = clean_body.strip() + "\n\n" + cta_block
            clean_body = clean_body.strip() + "\n\nBest regards,\n" + APPLICANT_SIGNATURE_BLOCK
    except Exception:
        pass



    attachments = state.attachments if state.attachments is not None else load_default_attachments()
    att_names = [a.get("filename") if isinstance(a, dict) else str(a) for a in (attachments or [])]
    has_att = bool(attachments)

    return {
        "subject": draft_res.subject,
        "body": clean_body,
        "attachments": attachments,
        "has_attachments": has_att,
        "attachment_names": att_names,
    }


def review_node(state: EmailState) -> dict:
    """Displays the draft email and interrupts for human approval or feedback, verifying attachment checkpoint status."""
    attachments = state.attachments if state.attachments is not None else load_default_attachments()
    att_list = state.attachment_names or [att.get("filename") if isinstance(att, dict) else str(att) for att in (attachments or [])]
    has_att = bool(att_list)

    print("\n" + "=" * 50)
    print(f"TO: {state.recipient_name} <{state.recipient_email}>")
    print(f"SUBJECT: {state.subject}")
    print(f"[CHECKPOINT] ATTACHMENTS ATTACHED: {'YES (' + ', '.join(att_list) + ')' if has_att else 'NO (None)'}")
    print("-" * 50)
    try:
        print(f"BODY:\n{state.body}")
    except Exception:
        print(f"BODY:\n{state.body.encode('ascii', errors='replace').decode('ascii')}")
    print("=" * 50 + "\n")


    user_decision = interrupt({
        "message": "Do you want to approve this or rewrite this email?",
        "subject": state.subject,
        "body": state.body,
        "has_attachments": has_att,
        "attachment_names": att_list,
        "attachment_checkpoint_verified": has_att,
        "attachments": att_list,
    })

    decision_str = str(user_decision).strip().lower()
    if decision_str == "approve":
        return {
            "feedback": "approved"
        }
    else:
        return {
            "feedback": str(user_decision),
            "feedback_count": state.feedback_count + 1,
        }


def router(state: EmailState) -> Literal["draft", "send", "cancel"]:
    """Routes based on human review approval or revision limits."""
    if state.feedback == "approved":
        return "send"
    if state.feedback_count > 2:
        return "cancel"
    return "draft"


try:
    from Email_agent.mailer import send_email_via_smtp
except ImportError:
    from Email_agent.mailer import send_email_via_smtp


def sendnode(state: EmailState) -> dict:
    """Finalizes sending the approved email using smtplib, verifying attachments at checkpoint."""
    attachments = state.attachments if state.attachments is not None else load_default_attachments()
    att_names = [a.get("filename") if isinstance(a, dict) else str(a) for a in (attachments or [])]
    has_att = bool(attachments)

    print(f"\n[SEND] Dispatching email to {state.recipient_name} <{state.recipient_email}> via smtplib...")
    print(f"[CHECKPOINT ATTACHMENT CHECK] Attachments attached: {'YES (' + ', '.join(att_names) + ')' if has_att else 'NO (0 attachments)'}")

    success, details = send_email_via_smtp(
        to_email=state.recipient_email,
        subject=state.subject,
        body=state.body,
        recipient_name=state.recipient_name,
        attachments=attachments if attachments else None,
    )

    if success:
        return {
            "has_attachments": has_att,
            "attachment_names": att_names,
            "response": f"Email sent successfully to {state.recipient_name} ({state.recipient_email}) via SMTP (Attachments: {', '.join(att_names) if has_att else 'None'})."
        }
    else:
        return {
            "response": f"Email approved, but SMTP sending failed: {details}"
        }


def cancelorder(state: EmailState) -> dict:
    """Handles cancellation when maximum revisions are exceeded."""
    print("\n[CANCEL] Email drafting cancelled due to revision limit.")
    return {
        "response": "Email cancelled (maximum revision count exceeded)"
    }


# Graph Definition 

graph = StateGraph(EmailState)

graph.add_node("retriver", retriver)
graph.add_node("draft", draft_node)
graph.add_node("review", review_node)
graph.add_node("send", sendnode)
graph.add_node("cancel", cancelorder)

graph.add_edge(START, "retriver")
graph.add_edge("retriver", "draft")
graph.add_edge("draft", "review")
graph.add_conditional_edges("review", router)
graph.add_edge("send", END)
graph.add_edge("cancel", END)

checkpointer = InMemorySaver()
workflow = graph.compile(checkpointer=checkpointer)
app = workflow
