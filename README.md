# AI Email Agent - FastAPI Backend & MCP Server

A production-ready FastAPI backend and Model Context Protocol (MCP) server exposing an existing LangGraph-powered AI Email Agent. This service provides endpoints and AI agent tools for contextual email drafting, document attachments (e.g., resumes/CVs), human-in-the-loop review, and secure SMTP email dispatching.

---

## Architecture Overview

```text
email-agent/
├── app/
│   ├── main.py                  # FastAPI app entry point, CORS, and middleware
│   ├── api/
│   │   └── routes/
│   │       ├── health.py        # GET /health
│   │       └── email.py         # POST /api/v1/email/draft, /send, /apply, /attachments/upload
│   ├── core/
│   │   ├── config.py            # Pydantic-settings configuration from environment
│   │   └── attachments.py       # Secure attachment validation, magic bytes check & storage
│   ├── schemas/
│   │   └── email.py             # Pydantic v2 schemas for emails, attachments, and health
│   └── services/
│       └── email_agent_service.py # Service orchestrating LangGraph workflow, attachments & mailer
├── Email_agent/                 # Existing LangGraph agent & SMTP mailer integration
│   ├── agent.py                 # LangGraph state machine with human-in-the-loop review
│   └── mailer.py                # MIMEBase multipart/mixed SMTP mailer
├── storage/
│   └── uploads/                 # Sandboxed local storage for uploaded attachments (gitignored)
├── mcp_server.py                # Standalone MCP Server exposing tools over Streamable HTTP
├── tunnel.py                    # Automated ngrok tunnel script for public HTTPS exposure
├── tests/
│   ├── conftest.py              # Pytest setup and path configuration
│   ├── test_health.py           # Health check test
│   ├── test_email_api.py        # Automated test suite (FastAPI backend + attachments)
│   └── test_mcp_server.py       # Automated test suite (MCP server tools + attachments)
├── .env.example                 # Environment configuration template
├── .gitignore                   # Git ignore rules for secrets, uploads, and virtualenvs
├── requirements.txt             # Standard pip requirements
├── pyproject.toml               # uv / pip packaging specification
└── README.md                    # Project documentation
```

---

## 1. Local Development Setup (Windows CMD & PowerShell)

### Prerequisites
- Python 3.10+ (Python 3.11+ recommended)
- [uv](https://github.com/astral-sh/uv) (recommended) or standard `pip` + `venv`

### Option A: Using `uv` (Recommended)

1. Navigate to the repository:
   ```cmd
   cd C:\Users\amanm\OneDrive\Desktop\Email_agent
   ```

2. Install dependencies:
   ```cmd
   uv sync
   ```

3. Start the FastAPI backend (Terminal 1):
   ```cmd
   uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

4. Start the MCP server (Terminal 2):
   ```cmd
   uv run python mcp_server.py
   ```

5. Expose public HTTPS tunnel via ngrok (Terminal 3):
   ```cmd
   uv run python tunnel.py --port 8001
   ```

### Option B: Running with Docker & Docker Compose (Containerized)

1. Ensure your `.env` is configured (copy from `.env.example`).

2. Build and start both the FastAPI backend and FastMCP server containers:
   ```cmd
   docker compose up --build -d
   ```

3. Check running containers and health status:
   ```cmd
   docker compose ps
   ```

4. View service logs:
   ```cmd
   docker compose logs -f
   ```

5. Stop all services:
   ```cmd
   docker compose down
   ```

---

## CI / CD Pipeline (GitHub Actions)

A comprehensive GitHub Actions workflow is located at `.github/workflows/ci.yml`. On every push and pull request to `main` and `master`, it:
1. Sets up Python 3.10 and caches dependencies.
2. Runs the full automated test suite (`pytest -v`).
3. Validates the Docker container build (`docker build`) to guarantee deployment reliability.

---

## 2. Configuration (`.env`)

Configure your credentials in `.env`:

```dotenv
# LLM Provider (Groq)
GROQ_API_KEY=your_groq_api_key_here

# SMTP Email Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password_here

# FastAPI Backend Configuration
ENVIRONMENT=development
PORT=8000
HOST=0.0.0.0

# File Attachment Security Settings
UPLOAD_DIR=storage/uploads
MAX_ATTACHMENT_SIZE_MB=10

# MCP Server Configuration
EMAIL_API_BASE_URL=http://127.0.0.1:8000
EMAIL_API_KEY=
MCP_HOST=0.0.0.0
MCP_PORT=8001
MCP_TRANSPORT=streamable-http
HTTP_TIMEOUT=60.0

# ngrok Tunnel Configuration (Get free auth token at https://dashboard.ngrok.com)
NGROK_AUTHTOKEN=your_ngrok_authtoken_here
```

---

## 3. Secure Attachment Handling & Transfer

### Supported Transfer Mechanisms

Because AI clients like ChatGPT cannot automatically access local files, this system provides two explicit and secure transfer mechanisms:

1. **Upload Reference (Recommended for Web/API)**:
   Upload a file via `POST /api/v1/email/attachments/upload` using `multipart/form-data`. The server returns a secure reference ID (`att_...`) that can be passed to draft and send endpoints.

2. **Direct Base64 Transfer (Recommended for MCP / AI Agents)**:
   Pass inline base64-encoded document content directly in the API or MCP payload:
   ```json
   {
     "filename": "My_Resume.pdf",
     "content_base64": "JVBERi0xLjQK...",
     "content_type": "application/pdf"
   }
   ```

### Security Defenses Implemented:
- **Strict Extension Whitelist:** `.pdf` (preferred), `.docx`, `.doc`, `.txt`. Executables (`.exe`, `.bat`, `.py`) are rejected (`400 Bad Request`).
- **Magic Byte Verification:** PDF files are checked for the `%PDF-` header. Spoofed files are rejected.
- **Path Traversal Defense:** Filenames are stripped of path components (`../`, `..\\`, null bytes). Files are stored in isolated UUID directories verified with `Path.is_relative_to()`.
- **Size Limits:** Enforces a maximum file size (default 10MB per file, 25MB total payload) to prevent denial-of-service (`413 Content Too Large`).
- **Private Storage:** Stored files are gitignored and cannot be downloaded arbitrarily through the public API.

---

## 4. API Endpoints Reference

### A. Health Check
`GET /health`
```json
{
  "status": "healthy",
  "service": "email-agent-api"
}
```

---

### B. Upload Document Attachment
`POST /api/v1/email/attachments/upload`

Uploads and validates a document (PDF, Word, Text).

**Sample Request (cURL):**
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/email/attachments/upload" \
  -F "file=@C:/path/to/my_resume.pdf"
```

**Sample Response (`201 Created`):**
```json
{
  "attachment_id": "att_9a8b7c6d5e4f",
  "filename": "my_resume.pdf",
  "content_type": "application/pdf",
  "size_bytes": 104850
}
```

---

### C. Draft Email (with Attachments)
`POST /api/v1/email/draft`

Prepares the email draft, acknowledging any attached documents, and halts at the review stage.

**Sample Request:**
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/email/draft" \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Apply for the AI Engineer role.",
    "recipient_email": "hr@company.com",
    "job_description": "We need a Python and LangGraph developer.",
    "applicant_context": "5 years experience with FastAPI and LangGraph.",
    "attachment_ids": ["att_9a8b7c6d5e4f"]
  }'
```

**Sample Response (`200 OK` - Not Sent):**
```json
{
  "status": "draft_created",
  "recipient_email": "hr@company.com",
  "recipient_name": "Hiring Team",
  "subject": "Application for AI Engineer Role - Aman",
  "body": "Dear Hiring Team,\n\nI am writing to express my strong interest in the AI Engineer role. Please find my resume attached for your review...",
  "requires_approval": true,
  "thread_id": "8f3e5b32-6a7c-473f-8461-9c32f2ef48c7",
  "attachments": [
    {
      "attachment_id": "att_9a8b7c6d5e4f",
      "filename": "my_resume.pdf",
      "content_type": "application/pdf",
      "size_bytes": 104850
    }
  ]
}
```

---

### D. Send Approved Email (with Attachments)
`POST /api/v1/email/send`

Dispatches the approved email and attaches documents using MIMEBase encoding.

**Sample Request:**
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/email/send" \
  -H "Content-Type: application/json" \
  -d '{
    "recipient_email": "hr@company.com",
    "subject": "Application for AI Engineer Role - Aman",
    "body": "Dear Hiring Team,\n\nPlease find my resume attached.",
    "approved": true,
    "attachment_ids": ["att_9a8b7c6d5e4f"]
  }'
```

**Sample Response (`200 OK`):**
```json
{
  "status": "sent",
  "message": "Email successfully sent to hr@company.com via smtp.gmail.com:587",
  "recipient_email": "hr@company.com",
  "recipient_name": null,
  "attachments": [
    {
      "attachment_id": "att_9a8b7c6d5e4f",
      "filename": "my_resume.pdf",
      "content_type": "application/pdf",
      "size_bytes": 104850
    }
  ]
}
```

*Note: If `approved` is False or missing, sending is rejected with `400 Bad Request`.*

---

### E. Default Resume Attachment (`Aman_Mulla_Resume.pdf`)
The applicant's resume is stored securely in `storage/default_attachments/Aman_Mulla_Resume.pdf`.

- **Automatic Inclusion**: By default (`ATTACH_DEFAULT_BY_DEFAULT=true`), every email drafted or sent automatically attaches this resume.
- **Draft Awareness**: When drafting an email, the agent is made aware of the resume and mentions it naturally in the draft body.
- **Review Transparency**: The resume is clearly listed in draft outputs, unapproved approval prompts, and send responses.
- **Opt-Out Control**: If an email should NOT include the default resume (e.g. general inquiries), set `"include_default_attachment": false` in the request payload.

---

## 5. MCP Server & ChatGPT Integration

### Tools Available:

1. **`draft_application_email`**:
   - Prepares a draft and automatically references `Aman_Mulla_Resume.pdf` (or any custom attachments).
   - Shows recipient, subject, body, and attached filenames.
   - Accepts `include_default_attachment: bool = True` (defaults to True).

2. **`send_application_email`**:
   - Automatically attaches `Aman_Mulla_Resume.pdf` unless `include_default_attachment=False`.
   - Accepts custom `attachment_ids` and/or inline base64 `attachments`.
   - **Enforces explicit human approval**: If `approved` is not `True`, it aborts immediately and prints a review summary asking the user for explicit confirmation before sending.

### Running with ngrok & Connecting to ChatGPT:

1. Start services:
   ```cmd
   :: Terminal 1
   uv run uvicorn app.main:app --port 8000

   :: Terminal 2
   uv run python mcp_server.py

   :: Terminal 3
   uv run python tunnel.py --port 8001
   ```

2. Copy the public **`ChatGPT MCP URL`** printed by `tunnel.py`:
   ```text
   https://your-domain.ngrok-free.app/mcp
   ```

3. In ChatGPT: **Settings > Connected Apps / MCP > Add Custom Server**:
   - URL: `https://your-domain.ngrok-free.app/mcp`
   - Transport: `Streamable HTTP`

---

## 6. Automated Testing

Run the full automated test suite (35 tests covering FastAPI, LangGraph agent, MCP server, default resume attachment, and security with 100% mocked external calls):

```cmd
uv run pytest -v
```

**Test Coverage Summary:**
- Automatic inclusion of default resume (`Aman_Mulla_Resume.pdf`) in draft and send endpoints.
- Opt-out flag (`include_default_attachment: false`) handling.
- Attachment upload validation (PDF magic bytes, valid extensions).
- Path traversal defense and filename sanitization.
- Rejection of oversized files (>10MB per file, 25MB total).
- Rejection of invalid file extensions (`.exe`, `.bat`).
- Missing and unauthorized attachment ID handling (404).
- Safe base64 decoding and validation.
- Sending emails with MIMEBase attachments via mocked SMTP.
- SMTP provider failure reporting (502).
- Approval enforcement before dispatching.
- MCP tools drafting and sending with default and custom attachments.

