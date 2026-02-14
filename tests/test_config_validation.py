"""
Test suite for config validation with clear error messages.

Verifies that config errors are clear, show examples, and help users fix problems.
"""

import pytest
import tempfile
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import Config


class TestConfigValidation:
    """Test config validation error messages."""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file."""
        temp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        temp.close()  # Close handle so Windows can delete it
        temp_path = Path(temp.name)
        yield temp_path
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    def test_valid_config_loads_successfully(self, temp_config_file):
        """Test that valid config loads without errors."""
        valid_config = {
            'min_sample_size_mb': 100,
            'min_music_files': 20
        }

        with open(temp_config_file, 'w') as f:
            json.dump(valid_config, f)

        config = Config(temp_config_file)
        assert config.get('min_sample_size_mb') == 100
        assert config.get('min_music_files') == 20

    def test_invalid_type_shows_clear_error(self, temp_config_file, capsys):
        """Test that wrong type shows clear error with example."""
        invalid_config = {
            'min_sample_size_mb': "fifty"  # Should be int
        }

        with open(temp_config_file, 'w') as f:
            json.dump(invalid_config, f)

        config = Config(temp_config_file)

        # Should fall back to default
        assert config.get('min_sample_size_mb') == 50  # Default value

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
            'min_sample_size_mb': 99999  # Out of range
        }

        with open(temp_config_file, 'w') as f:
            json.dump(invalid_config, f)

        config = Config(temp_config_file)

        # Should fall back to default
        assert config.get('min_sample_size_mb') == 50

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
            'video_extensions': ".mp4"  # Should be list
        }

        with open(temp_config_file, 'w') as f:
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
            'video_extensions': ["mp4", "mkv"]  # Missing dots
        }

        with open(temp_config_file, 'w') as f:
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
        with open(temp_config_file, 'w') as f:
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
        invalid_config = {
            'min_sample_size_mb': "bad"
        }

        with open(temp_config_file, 'w') as f:
            json.dump(invalid_config, f)

        _ = Config(temp_config_file)

        # Check that absolute path is shown
        captured = capsys.readouterr()
        assert "Config file:" in captured.out
        assert str(temp_config_file.absolute()) in captured.out


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
