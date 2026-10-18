import os
import re
import json
import uuid
import base64
import binascii
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from fastapi import HTTPException, status

from app.core.config import get_settings

settings = get_settings()


def get_upload_dir() -> Path:
    """Returns the resolved uploads directory, ensuring it exists."""
    upload_path = Path(settings.UPLOAD_DIR).resolve()
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


def sanitize_filename(filename: str) -> str:
    """
    Sanitizes filename by stripping directory separators, dangerous characters,
    null bytes, and hidden file prefixes to prevent path traversal attacks.
    """
    if not filename or not filename.strip():
        return "document.pdf"

    # Extract basename only
    base = Path(filename).name
    base = os.path.basename(base)

    # Remove null bytes and control chars
    base = base.replace("\0", "").strip()

    # Retain only safe alphanumeric characters, dots, underscores, and dashes
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "_", base)

    # Strip leading dots to prevent hidden files or traversal sequences
    cleaned = cleaned.lstrip(".")

    if not cleaned:
        return "document.pdf"

    return cleaned


def validate_attachment_extension(filename: str) -> str:
    """Validates that file extension is among allowed types."""
    ext = Path(filename).suffix.lower()
    if not ext or ext not in settings.ALLOWED_ATTACHMENT_EXTENSIONS:
        allowed = ", ".join(settings.ALLOWED_ATTACHMENT_EXTENSIONS)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Allowed extensions: {allowed}",
        )
    return ext


def validate_attachment_content(content: bytes, filename: str, content_type: Optional[str] = None) -> None:
    """
    Validates file content size, empty files, and magic bytes (e.g. PDF headers).
    """
    max_bytes = settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Attachment '{filename}' is empty (0 bytes).",
        )

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE if hasattr(status, "HTTP_413_CONTENT_TOO_LARGE") else 413,
            detail=f"Attachment '{filename}' size ({len(content)} bytes) exceeds the maximum allowed limit of {settings.MAX_ATTACHMENT_SIZE_MB}MB.",
        )

    ext = Path(filename).suffix.lower()

    # Magic byte verification for PDF files
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Attachment '{filename}' has invalid PDF structure (missing %PDF- header).",
            )


def save_uploaded_attachment(filename: str, content: bytes, content_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Persists an uploaded attachment to an isolated sandbox directory.
    Returns metadata including unique attachment_id.
    """
    sanitized_name = sanitize_filename(filename)
    validate_attachment_extension(sanitized_name)
    validate_attachment_content(content, sanitized_name, content_type)

    attachment_id = f"att_{uuid.uuid4().hex}"
    upload_root = get_upload_dir()
    att_dir = (upload_root / attachment_id).resolve()

    # Path traversal assertion
    if not att_dir.is_relative_to(upload_root):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path traversal violation detected.",
        )

    att_dir.mkdir(parents=True, exist_ok=True)
    file_path = att_dir / sanitized_name

    with open(file_path, "wb") as f:
        f.write(content)

    resolved_content_type = content_type or "application/pdf" if sanitized_name.lower().endswith(".pdf") else "application/octet-stream"

    metadata = {
        "attachment_id": attachment_id,
        "filename": sanitized_name,
        "content_type": resolved_content_type,
        "size_bytes": len(content),
        "file_path": str(file_path),
    }

    with open(att_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return metadata


def load_attachment_by_id(attachment_id: str) -> Dict[str, Any]:
    """
    Loads attachment content and metadata securely by attachment_id reference.
    Prevents directory traversal and unauthorized filesystem access.
    """
    if not attachment_id or not re.match(r"^att_[a-zA-Z0-9_-]+$", attachment_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid attachment ID format: '{attachment_id}'",
        )

    upload_root = get_upload_dir()
    att_dir = (upload_root / attachment_id).resolve()

    # Path traversal assertion
    if not att_dir.is_relative_to(upload_root) or not att_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attachment reference '{attachment_id}' not found or unauthorized.",
        )

    metadata_path = att_dir / "metadata.json"
    if not metadata_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metadata missing for attachment '{attachment_id}'.",
        )

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    file_path = Path(metadata["file_path"]).resolve()
    if not file_path.is_relative_to(upload_root) or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stored file for attachment '{attachment_id}' is missing.",
        )

    with open(file_path, "rb") as f:
        content_bytes = f.read()

    return {
        "attachment_id": attachment_id,
        "filename": metadata["filename"],
        "content": content_bytes,
        "mime_type": metadata.get("content_type", "application/octet-stream"),
        "size_bytes": len(content_bytes),
    }


def decode_base64_attachment(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates and decodes base64-encoded file content passed directly in API / MCP payloads.
    """
    raw_filename = payload.get("filename", "attachment.pdf")
    sanitized_name = sanitize_filename(raw_filename)
    validate_attachment_extension(sanitized_name)

    content_base64 = payload.get("content_base64")
    if not content_base64 or not isinstance(content_base64, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Attachment '{sanitized_name}' is missing valid content_base64.",
        )

    # Strip potential data URL prefix (e.g. data:application/pdf;base64,...)
    if "," in content_base64:
        content_base64 = content_base64.split(",", 1)[1]

    try:
        content_bytes = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid base64 encoding for attachment '{sanitized_name}': {str(err)}",
        )

    content_type = payload.get("content_type") or ("application/pdf" if sanitized_name.lower().endswith(".pdf") else "application/octet-stream")
    validate_attachment_content(content_bytes, sanitized_name, content_type)

    return {
        "attachment_id": None,
        "filename": sanitized_name,
        "content": content_bytes,
        "mime_type": content_type,
        "size_bytes": len(content_bytes),
    }


def get_default_attachment() -> Optional[Dict[str, Any]]:
    """
    Loads the default resume / document attachment (e.g. Aman_Mulla_Resume.pdf)
    if configured and present on disk.
    """
    default_path_str = getattr(settings, "DEFAULT_ATTACHMENT_PATH", "storage/default_attachments/Aman_Mulla_Resume.pdf")
    if not default_path_str:
        return None

    default_path = Path(default_path_str).resolve()
    if not default_path.exists() or not default_path.is_file():
        return None

    filename = default_path.name
    with open(default_path, "rb") as f:
        content_bytes = f.read()

    return {
        "attachment_id": "default_resume",
        "filename": filename,
        "content": content_bytes,
        "mime_type": "application/pdf" if filename.lower().endswith(".pdf") else "application/octet-stream",
        "size_bytes": len(content_bytes),
        "is_default": True,
    }


def list_available_attachments() -> List[Dict[str, Any]]:
    """
    Returns a catalog of verified attachments and default resumes stored on the server.
    """
    available: List[Dict[str, Any]] = []
    default_att = get_default_attachment()
    if default_att:
        available.append({
            "attachment_id": default_att["attachment_id"],
            "filename": default_att["filename"],
            "content_type": default_att["mime_type"],
            "size_bytes": default_att["size_bytes"],
            "is_default": True,
        })

    upload_root = get_upload_dir()
    for meta_file in upload_root.glob("*/metadata.json"):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
                available.append({
                    "attachment_id": meta.get("attachment_id"),
                    "filename": meta.get("filename"),
                    "content_type": meta.get("content_type", "application/pdf"),
                    "size_bytes": meta.get("size_bytes", 0),
                    "is_default": False,
                })
        except Exception:
            pass
    return available



def resolve_all_attachments(
    attachment_ids: Optional[List[str]] = None,
    direct_attachments: Optional[List[Dict[str, Any]]] = None,
    include_default: bool = True,
) -> List[Dict[str, Any]]:
    """
    Resolves uploaded attachment references, inline base64 attachments, and the default resume
    into a validated list of attachment dictionaries ready for dispatch.
    """
    resolved: List[Dict[str, Any]] = []

    # Resolve attachment IDs
    if attachment_ids:
        for att_id in attachment_ids:
            if att_id in ("default_resume", "Aman_Mulla_Resume.pdf", "resume.pdf", "resume"):
                default_att = get_default_attachment()
                if default_att:
                    if not any(a.get("filename") == default_att["filename"] for a in resolved):
                        resolved.append(default_att)
                    continue
            att_data = load_attachment_by_id(att_id)
            resolved.append(att_data)

    # Resolve inline base64 attachments
    if direct_attachments:
        for direct_att in direct_attachments:
            if isinstance(direct_att, dict):
                decoded = decode_base64_attachment(direct_att)
            else:
                decoded = decode_base64_attachment(direct_att.model_dump())
            resolved.append(decoded)

    # Include default resume if enabled and not already explicitly present
    if include_default and getattr(settings, "ATTACH_DEFAULT_BY_DEFAULT", True):
        default_att = get_default_attachment()
        if default_att:
            # Check if an attachment with the same filename or ID is already in the list
            already_included = any(
                a.get("filename") == default_att["filename"] or a.get("attachment_id") == "default_resume"
                for a in resolved
            )
            if not already_included:
                resolved.append(default_att)

    # Total size safeguard (max 25MB total payload)
    total_size = sum(a.get("size_bytes", 0) for a in resolved)
    if total_size > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE if hasattr(status, "HTTP_413_CONTENT_TOO_LARGE") else 413,
            detail=f"Total attachments size ({total_size} bytes) exceeds maximum allowable limit of 25MB.",
        )

    return resolved

