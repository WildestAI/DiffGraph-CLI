# Tests

This directory contains tests for the DiffGraph CLI tool.

## Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared pytest fixtures
├── README.md                      # This file
├── test_cli.py                    # CLI integration tests
└── processing_modes/
    ├── __init__.py
    ├── test_base.py              # Base processor tests
    ├── test_registry.py          # Registry and factory tests
    └── test_openai_agents.py     # OpenAI processor tests
```

## Running Tests

### Install pytest

```bash
pip install pytest pytest-cov
```

### Run all tests

```bash
pytest
```

### Run with coverage

```bash
pytest --cov=diffgraph --cov-report=html
```

### Run specific test file

```bash
pytest tests/test_cli.py
```

### Run specific test function

```bash
pytest tests/processing_modes/test_registry.py::test_list_available_modes
```

### Run with verbose output

```bash
pytest -v
```

## Test Categories

### Unit Tests
- `processing_modes/test_base.py` - Base processor interface
- `processing_modes/test_registry.py` - Registry and factory pattern
- `processing_modes/test_openai_agents.py` - OpenAI processor specifics

### Integration Tests
- `test_cli.py` - CLI command integration

## Adding New Tests

When adding a new processing mode, create a corresponding test file:

```bash
tests/processing_modes/test_your_mode.py
```

Example:
```python
"""Tests for your new processor."""
import pytest
from diffgraph.processing_modes import get_processor

def test_your_processor_initialization():
    """Test your processor can be initialized."""
    processor = get_processor("your-mode-name", config="value")
    assert processor.name == "your-mode-name"
    
def test_your_processor_analyze():
    """Test analysis functionality."""
    processor = get_processor("your-mode-name", config="value")
    result = processor.analyze_changes([...])
    assert result.summary
    assert result.mermaid_diagram
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines. Make sure:
- All tests pass before committing
- New features include tests
- Test coverage stays high
