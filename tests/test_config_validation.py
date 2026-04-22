"""
Test suite for config validation with clear error messages.

Verifies that config errors are clear, show examples, and help users fix problems.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import Config


class TestConfigValidation:
    """Test config validation error messages."""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file."""
        temp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        temp.close()  # Close handle so Windows can delete it
        temp_path = Path(temp.name)
        yield temp_path
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    def test_valid_config_loads_successfully(self, temp_config_file):
        """Test that valid config loads without errors."""
        valid_config = {"min_sample_size_mb": 100, "min_music_files": 20}

        with open(temp_config_file, "w") as f:
            json.dump(valid_config, f)

        config = Config(temp_config_file)
        assert config.get("min_sample_size_mb") == 100
        assert config.get("min_music_files") == 20

    def test_invalid_type_shows_clear_error(self, temp_config_file, capsys):
        """Test that wrong type shows clear error with example."""
        invalid_config = {
            "min_sample_size_mb": "fifty"  # Should be int
        }

        with open(temp_config_file, "w") as f:
            json.dump(invalid_config, f)

        config = Config(temp_config_file)

        # Should fall back to default
        assert config.get("min_sample_size_mb") == 50  # Default value

        # Check error message
        captured = capsys.readouterr()
        assert "ERROR: Invalid config value" in captured.out
        assert "Field: min_sample_size_mb" in captured.out
        assert "Value: 'fifty' (str)" in captured.out
        assert "Expected: number (integer)" in captured.out
        assert "Example: 50" in captured.out

    def test_out_of_range_shows_clear_error(self, temp_config_file, capsys):
        """Test that out-of-range value shows clear error."""
        invalid_config = {
            "min_sample_size_mb": 99999  # Out of range
        }

        with open(temp_config_file, "w") as f:
            json.dump(invalid_config, f)

        config = Config(temp_config_file)

        # Should fall back to default
        assert config.get("min_sample_size_mb") == 50

        # Check error message
        captured = capsys.readouterr()
        assert "ERROR: Invalid config value" in captured.out
        assert "Field: min_sample_size_mb" in captured.out
        assert "Value: 99999" in captured.out
        assert "Expected: number between 1 and 10000" in captured.out
        assert "Example: 50" in captured.out

    def test_invalid_list_type_shows_clear_error(self, temp_config_file, capsys):
        """Test that wrong list type shows clear error."""
        invalid_config = {
            "video_extensions": ".mp4"  # Should be list
        }

        with open(temp_config_file, "w") as f:
            json.dump(invalid_config, f)

        _ = Config(temp_config_file)

        # Check error message
        captured = capsys.readouterr()
        assert "ERROR: Invalid config value" in captured.out
        assert "Field: video_extensions" in captured.out
        assert "Expected: list of strings" in captured.out
        assert "Example:" in captured.out
        assert ".mp4" in captured.out

    def test_missing_dot_in_extension_shows_clear_error(self, temp_config_file, capsys):
        """Test that extension without dot shows clear error."""
        invalid_config = {
            "video_extensions": ["mp4", "mkv"]  # Missing dots
        }

        with open(temp_config_file, "w") as f:
            json.dump(invalid_config, f)

        _ = Config(temp_config_file)

        # Check error message
        captured = capsys.readouterr()
        assert "ERROR: Invalid config value" in captured.out
        assert "Field: video_extensions" in captured.out
        assert "Extensions must start with '.'" in captured.out
        assert "note the dots" in captured.out

    def test_invalid_json_shows_clear_error(self, temp_config_file, capsys):
        """Test that invalid JSON shows clear error with line number."""
        # Write invalid JSON
        with open(temp_config_file, "w") as f:
            f.write('{\n  "min_sample_size_mb": 50,\n  "broken": \n}')

        _ = Config(temp_config_file)

        # Check error message
        captured = capsys.readouterr()
        assert "ERROR: Invalid JSON in config file" in captured.out
        assert "Config file:" in captured.out
        assert "Problem:" in captured.out
        assert "Line:" in captured.out
        assert "Fix the JSON syntax" in captured.out

    def test_config_file_path_shown_in_errors(self, temp_config_file, capsys):
        """Test that config file path is shown in error messages."""
        invalid_config = {"min_sample_size_mb": "bad"}

        with open(temp_config_file, "w") as f:
            json.dump(invalid_config, f)

        _ = Config(temp_config_file)

        # Check that absolute path is shown
        captured = capsys.readouterr()
        assert "Config file:" in captured.out
        assert str(temp_config_file.absolute()) in captured.out

    def test_top_level_json_array_is_rejected(self, temp_config_file, capsys):
        with open(temp_config_file, "w") as f:
            json.dump(["not", "a", "dict"], f)

        config = Config(temp_config_file)

        assert config.get("min_sample_size_mb") == 50
        captured = capsys.readouterr()
        assert "JSON object at top level" in captured.out

    def test_generic_load_error_falls_back_to_defaults(self, temp_config_file, capsys):
        with patch("builtins.open", side_effect=OSError("boom")):
            config = Config(temp_config_file)

        assert config.get("max_log_files") == 5
        captured = capsys.readouterr()
        assert "ERROR: Could not load config file" in captured.out
        assert "boom" in captured.out

    def test_save_config_reports_write_errors(self, temp_config_file, capsys):
        config = Config()
        mocked_open = mock_open()
        mocked_open.side_effect = OSError("disk full")

        with patch("builtins.open", mocked_open):
            config.save_config(temp_config_file)

        captured = capsys.readouterr()
        assert "Error saving config" in captured.out
        assert "disk full" in captured.out

    def test_invalid_list_entry_type_is_rejected(self, temp_config_file, capsys):
        invalid_config = {"video_extensions": [".mp4", 123]}

        with open(temp_config_file, "w") as f:
            json.dump(invalid_config, f)

        _ = Config(temp_config_file)

        captured = capsys.readouterr()
        assert "List contains non-string values" in captured.out

    def test_invalid_tool_paths_and_log_folder_errors_are_reported(self):
        config = Config()
        is_valid, errors = config._validate_config(
            {
                "tool_paths": {
                    "ffmpeg": "bad",
                    "par2": ["ok", 7],
                },
                "log_folder": 42,
            }
        )

        assert is_valid is False
        assert "tool_paths['ffmpeg'] must be a list of paths" in errors
        assert "tool_paths['par2'] must contain only strings" in errors
        assert "log_folder must be a string" in errors[-1]

    def test_validate_tool_paths_requires_dictionary(self):
        config = Config()
        config.set("tool_paths", "bad")

        assert config.validate_tool_paths() == (False, ["tool_paths must be a dictionary"])

    def test_validate_tool_paths_flags_unsafe_relative_path(self):
        config = Config()
        config.set("tool_paths", {"ffmpeg": [".\\bin\\ffmpeg.exe"]})

        valid, errors = config.validate_tool_paths()

        assert valid is False
        assert "unsafe relative executable path" in errors[0]

    def test_validate_tool_paths_reports_missing_command(self, monkeypatch):
        config = Config()
        config.set("tool_paths", {"ffmpeg": ["ffmpeg-custom"]})
        monkeypatch.setattr("core.config.shutil.which", lambda *_: None)

        valid, errors = config.validate_tool_paths()

        assert valid is False
        assert "Paths tried: ffmpeg-custom" in errors[0]

    def test_validate_tool_paths_accepts_existing_absolute_path(self, tmp_path):
        tool = tmp_path / "ffmpeg.exe"
        tool.write_text("ok", encoding="utf-8")
        config = Config()
        config.set("tool_paths", {"ffmpeg": [str(tool)]})

        assert config.validate_tool_paths() == (True, [])

    def test_validate_tool_paths_accepts_path_command_lookup(self, monkeypatch):
        config = Config()
        config.set("tool_paths", {"ffmpeg": ["ffmpeg"]})
        monkeypatch.setattr("core.config.shutil.which", lambda value: "/usr/bin/ffmpeg" if value == "ffmpeg" else None)

        assert config.validate_tool_paths() == (True, [])

    def test_validate_tool_paths_skips_non_list_entries(self):
        config = Config()
        config.set("tool_paths", {"ffmpeg": "not-a-list"})

        assert config.validate_tool_paths() == (True, [])

    def test_property_getters_fall_back_to_defaults_for_invalid_values(self):
        config = Config()
        config.set("video_extensions", [".mp4", 123])
        config.set("max_runtime_hours", "bad")
        config.set("max_videos_per_folder", None)
        config.set("max_subfolder_depth", "bad")
        config.set("stuck_timeout_hours", [])

        assert config.video_extensions == Config.DEFAULT_CONFIG["video_extensions"]
        assert config.max_runtime_hours == 12
        assert config.max_videos_per_folder == 200
        assert config.max_subfolder_depth == 15
        assert config.stuck_timeout_hours == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
