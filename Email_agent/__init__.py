"""Email Agent package exposing the LangGraph workflow and mailer."""
from Email_agent.agent import workflow, EmailState
from Email_agent.mailer import send_email_via_smtp

__all__ = ["workflow", "EmailState", "send_email_via_smtp"]
