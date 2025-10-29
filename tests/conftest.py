"""
Pytest configuration and shared fixtures.
"""
import pytest
import os


@pytest.fixture
def mock_api_key():
    """Provide a mock API key for testing."""
    return "test-api-key-12345"


@pytest.fixture
def sample_file_changes():
    """Provide sample file changes for testing."""
    return [
        {
            "path": "test.py",
            "status": "modified",
            "content": "def hello():\n    print('Hello, world!')\n"
        },
        {
            "path": "new_file.py",
            "status": "untracked",
            "content": "class MyClass:\n    pass\n"
        }
    ]
