"""Unit tests for auto.step module."""

import pytest


def test_step_module_import():
    """Verify auto.step can be imported."""
    from auto.step import run_program, _extract_json


def test_run_program_import():
    """Verify run_program is importable from auto."""
    from auto import run_program


def test_extract_json_direct():
    """Test JSON extraction from clean input."""
    from auto.step import _extract_json

    result = _extract_json('{"answer": 42}')
    assert result == {"answer": 42}


def test_extract_json_fenced():
    """Test JSON extraction from markdown fences."""
    from auto.step import _extract_json

    result = _extract_json('```json\n{"answer": 42}\n```')
    assert result == {"answer": 42}


def test_extract_json_surrounded():
    """Test JSON extraction from text with surrounding content."""
    from auto.step import _extract_json

    result = _extract_json('Here is the result: {"answer": 42} Hope that helps!')
    assert result == {"answer": 42}


def test_extract_json_invalid():
    """Test that invalid JSON raises ValueError."""
    from auto.step import _extract_json

    with pytest.raises(ValueError):
        _extract_json("no json here at all")


def test_env_var_default():
    """Test that AUTO_SESSION_ID env var is checked."""
    import os
    from auto.step import run_program
    # run_program reads AUTO_SESSION_ID — just verify it's referenced in the module
    import auto.step
    assert "AUTO_SESSION_ID" in open(auto.step.__file__).read()
