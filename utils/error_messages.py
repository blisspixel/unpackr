"""
Clear, actionable error message formatting.

Foundation Layer: Better Error Messages

All error messages follow the pattern:
  ERROR: [What failed]
    Reason: [Why it failed]
    Action: [What user should do]
    Location: [Where the problem is]
"""

import logging
from pathlib import Path
from typing import Optional


def format_error(
    what_failed: str,
    reason: str,
    action: str,
    location: Optional[Path] = None,
    details: Optional[str] = None
) -> str:
    """
    Format a clear, actionable error message.

    Args:
        what_failed: What operation failed (e.g., "Failed to extract archive")
        reason: Why it failed (e.g., "Disk full (need 2.5GB, have 500MB)")
        action: What user should do (e.g., "Free up space or skip this file")
        location: Where the problem occurred (file path, directory, etc.)
        details: Optional additional details

    Returns:
        Formatted error message
    """
    lines = [f"ERROR: {what_failed}"]
    lines.append(f"  Reason: {reason}")
    lines.append(f"  Action: {action}")

    if location:
        lines.append(f"  Location: {location}")

    if details:
        lines.append(f"  Details: {details}")

    return "\n".join(lines)


def log_error(
    what_failed: str,
    reason: str,
    action: str,
    location: Optional[Path] = None,
    details: Optional[str] = None
):
    """
    Log a clear, actionable error message.

    Same parameters as format_error, but logs it directly.
    """
    message = format_error(what_failed, reason, action, location, details)
    logging.error(message)


def format_disk_space_error(path: Path, needed_mb: int, available_mb: int) -> str:
    """Format disk space error with clear numbers."""
    needed_gb = needed_mb / 1024
    available_gb = available_mb / 1024

    return format_error(
        what_failed="Insufficient disk space",
        reason=f"Need {needed_mb}MB ({needed_gb:.2f}GB), have {available_mb}MB ({available_gb:.2f}GB)",
        action="Free up space or skip this operation",
        location=path
    )


def format_extraction_error(archive: Path, reason: str, stderr: Optional[str] = None) -> str:
    """Format archive extraction error."""
    details = None
    if stderr:
        # Truncate stderr if too long
        details = stderr[:500] + "..." if len(stderr) > 500 else stderr

    return format_error(
        what_failed=f"Failed to extract {archive.name}",
        reason=reason,
        action="Check if archive is corrupted or password-protected",
        location=archive.parent,
        details=details
    )


def format_validation_error(file: Path, reason: str) -> str:
    """Format file validation error."""
    return format_error(
        what_failed=f"File validation failed: {file.name}",
        reason=reason,
        action="File may be corrupted or incomplete",
        location=file.parent
    )


def format_timeout_error(operation: str, timeout_seconds: int, file_size_mb: float = None) -> str:
    """Format timeout error."""
    reason = f"Operation exceeded {timeout_seconds}s timeout"
    if file_size_mb:
        reason += f" (file size: {file_size_mb:.1f}MB)"

    return format_error(
        what_failed=f"Timeout during {operation}",
        reason=reason,
        action="File may be extremely large or disk is very slow. Check system resources."
    )
