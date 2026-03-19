from app.memory.embeddings import format_embedding


def test_format_embedding_basic():
    """format_embedding should produce pgvector-compatible string."""
    result = format_embedding([0.1, 0.2, 0.3])
    assert result == "[0.1,0.2,0.3]"


def test_format_embedding_empty():
    """format_embedding with empty list should return empty brackets."""
    result = format_embedding([])
    assert result == "[]"


def test_format_embedding_single():
    """format_embedding with single value."""
    result = format_embedding([1.0])
    assert result == "[1.0]"
