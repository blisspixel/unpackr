from pathlib import Path

from utils import error_messages as em


def test_format_error_with_optional_fields():
    msg = em.format_error(
        what_failed="Operation failed",
        reason="Because reasons",
        action="Do the thing",
        location=Path("C:/tmp/file.txt"),
        details="More detail",
    )
    assert "ERROR: Operation failed" in msg
    assert "Reason: Because reasons" in msg
    assert "Action: Do the thing" in msg
    assert "Location: C:\\tmp\\file.txt" in msg or "Location: C:/tmp/file.txt" in msg
    assert "Details: More detail" in msg


def test_log_error_calls_logging_error(monkeypatch):
    seen = {"message": None}

    def _capture(message):
        seen["message"] = message

    monkeypatch.setattr(em.logging, "error", _capture)
    em.log_error("Bad", "Nope", "Fix it")
    assert seen["message"] is not None
    assert "ERROR: Bad" in seen["message"]


def test_format_disk_space_error_includes_mb_and_gb():
    out = em.format_disk_space_error(Path("C:/data"), needed_mb=2048, available_mb=1024)
    assert "Insufficient disk space" in out
    assert "Need 2048MB (2.00GB), have 1024MB (1.00GB)" in out


def test_format_extraction_error_truncates_stderr():
    stderr = "x" * 600
    out = em.format_extraction_error(Path("C:/archives/test.rar"), "bad archive", stderr=stderr)
    assert "Failed to extract test.rar" in out
    assert "Reason: bad archive" in out
    assert "Details:" in out
    assert "..." in out


def test_format_extraction_error_without_stderr_has_no_details():
    out = em.format_extraction_error(Path("C:/archives/test.rar"), "bad archive", stderr=None)
    assert "Failed to extract test.rar" in out
    assert "Details:" not in out


def test_format_validation_and_timeout_errors():
    validation = em.format_validation_error(Path("C:/videos/file.mkv"), "checksum mismatch")
    assert "File validation failed: file.mkv" in validation
    assert "checksum mismatch" in validation

    timeout_with_size = em.format_timeout_error("transcode", 30, file_size_mb=123.4)
    assert "Timeout during transcode" in timeout_with_size
    assert "Operation exceeded 30s timeout (file size: 123.4MB)" in timeout_with_size

    timeout_no_size = em.format_timeout_error("scan", 15, file_size_mb=None)
    assert "Operation exceeded 15s timeout" in timeout_no_size
    assert "file size:" not in timeout_no_size
