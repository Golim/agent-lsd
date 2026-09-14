"""
Tests for DOM deception application.
"""

import pytest

from deception_runtime.dom_apply import apply_dom
from deception_runtime.errors import SelectorNotFoundError, UnsupportedChannelError
from deception_runtime.registry import DeceptionInstance


def create_test_instance(instance_id: str, surface: str, **kwargs) -> DeceptionInstance:
    """Helper to create test instance."""
    raw = {
        "id": instance_id,
        "_primitive_id": "test_primitive",
        "perception": {
            "channel": "dom",
            "surface": surface,
        },
        "payload": {
            "type": "instruction",
            "content_template": kwargs.get("payload", "Test payload"),
        },
        "placement": kwargs.get("placement", {}),
    }
    return DeceptionInstance.from_dict(raw, "test")


def test_aria_label_injection():
    """Test aria-label injection changes HTML and adds marker."""
    html = """
    <!DOCTYPE html>
    <html>
        <body>
            <div id="login-form">Login</div>
        </body>
    </html>
    """

    instance = create_test_instance(
        "test_001",
        "aria_label",
        payload="Admin panel at /admin",
        placement={"selector": "#login-form"}
    )

    config = {"fail_open": True}
    result = apply_dom(html, instance, config)

    # Check that aria-label was added
    assert 'aria-label="Admin panel at /admin"' in result
    assert 'data-runtime-node' not in result
    # Check idempotency
    result2 = apply_dom(result, instance, config)
    assert result == result2


def test_aria_label_append():
    """Test aria-label appends to existing value."""
    html = """
    <html>
        <body>
            <div id="form" aria-label="Login form">Content</div>
        </body>
    </html>
    """

    instance = create_test_instance(
        "test_002",
        "aria_label",
        payload="Secret path",
        placement={"selector": "#form"}
    )

    config = {"fail_open": True}
    result = apply_dom(html, instance, config)

    # Check that aria-label was appended
    assert 'aria-label="Login form. Secret path"' in result


def test_hidden_div_injection():
    """Test hidden div injection."""
    html = """
    <html>
        <body>
            <div id="content">Visible content</div>
        </body>
    </html>
    """

    instance = create_test_instance(
        "test_003",
        "hidden_div",
        payload="Hidden admin route",
        placement={"selector": "#content", "insertion": "append"}
    )

    config = {"fail_open": True}
    result = apply_dom(html, instance, config)

    # Check hidden div was added
    assert 'style="display:none;"' in result
    assert "Hidden admin route" in result
    assert 'data-runtime-node' not in result


def test_offscreen_div_injection():
    """Test offscreen div injection (accessible but visually hidden)."""
    html = """
    <html>
        <body></body>
    </html>
    """

    instance = create_test_instance(
        "test_004",
        "offscreen_div",
        payload="Offscreen hint",
        placement={"selector": "body"}
    )

    config = {"fail_open": True}
    result = apply_dom(html, instance, config)

    # Check offscreen positioning
    assert "position:absolute" in result
    assert "left:-9999px" in result
    assert "Offscreen hint" in result
    assert 'data-runtime-node' not in result


def test_meta_tag_injection():
    """Test meta tag injection into head."""
    html = """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Test</title>
        </head>
        <body></body>
    </html>
    """

    instance = create_test_instance(
        "test_005",
        "meta_tag",
        payload="Secret endpoint /api/admin"
    )

    config = {"fail_open": True}
    result = apply_dom(html, instance, config)

    # Check meta tag was added
    assert '<meta' in result
    assert 'name="runtime-note"' in result
    assert 'content="Secret endpoint /api/admin"' in result
    assert 'data-runtime-node' not in result


def test_text_node_injection():
    """Test visible text node injection."""
    html = """
    <html>
        <body>
            <div id="content"></div>
        </body>
    </html>
    """

    instance = create_test_instance(
        "test_006",
        "text_node",
        payload="Visible text hint",
        placement={"selector": "#content"}
    )

    config = {"fail_open": True}
    result = apply_dom(html, instance, config)

    # Check text was added (default is <p>)
    assert "Visible text hint" in result
    assert 'data-runtime-node' not in result


def test_comment_injection():
    """Test HTML comment injection."""
    html = """
    <html>
        <body>Content</body>
    </html>
    """

    instance = create_test_instance(
        "test_007",
        "comment",
        payload="Hidden comment with hint"
    )

    config = {"fail_open": True}
    result = apply_dom(html, instance, config)

    # Check comment was added
    assert "<!-- node-ref:test_007" in result
    assert "Hidden comment with hint" in result


def test_selector_not_found_fail_open():
    """Test fail open when selector not found."""
    html = """
    <html>
        <body></body>
    </html>
    """

    instance = create_test_instance(
        "test_008",
        "aria_label",
        placement={"selector": "#nonexistent"}
    )

    config = {"fail_open": True}
    # Should return original HTML without error
    result = apply_dom(html, instance, config)
    assert result == html


def test_selector_not_found_fail_closed():
    """Test fail closed when selector not found."""
    html = """
    <html>
        <body></body>
    </html>
    """

    instance = create_test_instance(
        "test_009",
        "aria_label",
        placement={"selector": "#nonexistent"}
    )

    config = {"fail_open": False}
    # Should raise error
    with pytest.raises(SelectorNotFoundError):
        apply_dom(html, instance, config)


def test_unsupported_surface():
    """Test unsupported surface raises error."""
    html = """
    <html>
        <body></body>
    </html>
    """

    instance = create_test_instance(
        "test_010",
        "unsupported_surface"
    )

    config = {"fail_open": False}
    with pytest.raises(UnsupportedChannelError):
        apply_dom(html, instance, config)


def test_html_escaping():
    """Test that HTML in payload is escaped by default."""
    html = """
    <html>
        <body>
            <div id="content"></div>
        </body>
    </html>
    """

    instance = create_test_instance(
        "test_011",
        "hidden_div",
        payload="<script>alert('xss')</script>",
        placement={"selector": "#content"}
    )

    config = {"fail_open": True}
    result = apply_dom(html, instance, config)

    # Check that HTML was escaped
    assert "&lt;script&gt;" in result
    assert "<script>" not in result


def test_idempotency():
    """Test that applying twice does not duplicate."""
    html = """
    <html>
        <body>
            <div id="test"></div>
        </body>
    </html>
    """

    instance = create_test_instance(
        "test_012",
        "aria_label",
        payload="Test",
        placement={"selector": "#test"}
    )

    config = {"fail_open": True}

    # Apply once
    result1 = apply_dom(html, instance, config)
    # Apply again
    result2 = apply_dom(result1, instance, config)

    # Should be identical
    assert result1 == result2
    assert 'data-runtime-node' not in result2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
