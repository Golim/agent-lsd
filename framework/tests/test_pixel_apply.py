"""
Tests for pixel deception application.
"""

import base64

import pytest

from deception_runtime.pixel_apply import apply_pixel
from deception_runtime.registry import DeceptionInstance


def create_test_instance(instance_id: str, surface: str, **kwargs) -> DeceptionInstance:
    """Helper to create test instance."""
    raw = {
        "id": instance_id,
        "_primitive_id": "test_primitive",
        "perception": {
            "channel": "pixel",
            "surface": surface,
        },
        "payload": {
            "type": "instruction",
            "content_template": kwargs.get("payload", "Test pixel payload"),
        },
        "placement": kwargs.get("placement", {}),
    }
    return DeceptionInstance.from_dict(raw, "test")


def test_canvas_drawtext_injection():
    """Test canvas drawtext injection adds script and marker."""
    html = """
    <!DOCTYPE html>
    <html>
        <head><title>Test</title></head>
        <body>
            <div id="content">Content</div>
        </body>
    </html>
    """

    instance = create_test_instance(
        "test_pixel_001",
        "canvas_drawtext",
        payload="Secret admin path: /admin/secret",
        placement={
            "canvas_id": "test-canvas",
            "coordinates": {"x": 50, "y": 100},
            "opacity": 0.8,
            "font_size": "medium",
            "color": "#ff0000"
        }
    )

    config = {"fail_open": True}
    result = apply_pixel(html, instance, config)

    # Check canvas element was added
    assert '<canvas' in result
    assert 'id="test-canvas"' in result
    assert 'data-runtime-node' not in result

    # Check script was added
    assert '<script' in result
    assert "function drawOverlay()" in result or "drawOverlay" in result

    # Check payload is base64 encoded
    expected_b64 = base64.b64encode("Secret admin path: /admin/secret".encode()).decode()
    assert expected_b64 in result

    # Check canvas coordinates
    assert "50" in result  # x coordinate
    assert "100" in result  # y coordinate


def test_canvas_idempotency():
    """Test canvas injection is idempotent."""
    html = """
    <html>
        <body></body>
    </html>
    """

    instance = create_test_instance(
        "test_pixel_002",
        "canvas_drawtext",
        payload="Test",
        placement={"canvas_id": "my-canvas"}
    )

    config = {"fail_open": True}

    # Apply once
    result1 = apply_pixel(html, instance, config)
    # Apply again
    result2 = apply_pixel(result1, instance, config)

    # Should be identical
    assert result1 == result2


def test_canvas_default_values():
    """Test canvas uses default values when not specified."""
    html = """
    <html>
        <body></body>
    </html>
    """

    instance = create_test_instance(
        "test_pixel_003",
        "canvas_drawtext",
        payload="Default test"
    )

    config = {"fail_open": True}
    result = apply_pixel(html, instance, config)

    # Check default canvas_id
    assert 'id="runtime-canvas-test_pixel_003"' in result

    # Check default coordinates (10, 20)
    assert "10" in result
    assert "20" in result


def test_css_pseudo_element():
    """Test CSS pseudo-element injection."""
    html = """
    <html>
        <head></head>
        <body>
            <div class="target">Content</div>
        </body>
    </html>
    """

    instance = create_test_instance(
        "test_pixel_004",
        "css_pseudo_element",
        payload="Pseudo hint text",
        placement={
            "selector": ".target",
            "pseudo": "::after",
            "font_size": "large",
            "color": "#00ff00",
            "position": {"top": "20px", "left": "30px"}
        }
    )

    config = {"fail_open": True}
    result = apply_pixel(html, instance, config)

    # Check style tag was added
    assert '<style' in result
    assert 'data-runtime-node' not in result

    # Check CSS content
    assert '.target::after' in result
    assert 'content: "Pseudo hint text"' in result or "content: 'Pseudo hint text'" in result
    assert '24px' in result  # large font size
    assert '#00ff00' in result


def test_css_pseudo_default_values():
    """Test CSS pseudo-element uses defaults."""
    html = """
    <html>
        <head></head>
        <body></body>
    </html>
    """

    instance = create_test_instance(
        "test_pixel_005",
        "css_pseudo_element",
        payload="Default pseudo"
    )

    config = {"fail_open": True}
    result = apply_pixel(html, instance, config)

    # Check default selector and pseudo
    assert 'body::after' in result
    # Check default font size (medium = 18px)
    assert '18px' in result


def test_payload_not_in_plain_text():
    """Test that payload in canvas is base64 encoded (reduced leakage)."""
    html = """
    <html>
        <body></body>
    </html>
    """

    secret_payload = "SECRET_ADMIN_PATH_12345"
    instance = create_test_instance(
        "test_pixel_006",
        "canvas_drawtext",
        payload=secret_payload
    )

    config = {"fail_open": True}
    result = apply_pixel(html, instance, config)

    # Check payload is encoded
    expected_b64 = base64.b64encode(secret_payload.encode()).decode()
    assert expected_b64 in result


def test_unsupported_surface_fail_open():
    """Test unsupported surface with fail_open."""
    html = """
    <html>
        <body></body>
    </html>
    """

    instance = create_test_instance(
        "test_pixel_007",
        "unsupported_pixel_surface"
    )

    config = {"fail_open": True}
    # Should return original HTML
    result = apply_pixel(html, instance, config)
    assert result == html


def test_multiple_canvas_properties():
    """Test canvas with various properties."""
    html = """
    <html>
        <body></body>
    </html>
    """

    instance = create_test_instance(
        "test_pixel_008",
        "canvas_drawtext",
        payload="Test",
        placement={
            "coordinates": {"x": 100, "y": 200},
            "opacity": 0.5,
            "font_size": "small",
            "color": "#abcdef"
        }
    )

    config = {"fail_open": True}
    result = apply_pixel(html, instance, config)

    # Check all properties are in the script
    assert "100" in result  # x
    assert "200" in result  # y
    assert "0.5" in result  # opacity
    assert "14" in result  # small font size
    assert "#abcdef" in result  # color


def test_font_size_mapping():
    """Test font size mapping works correctly."""
    html = "<html><body></body></html>"

    test_cases = [
        ("micro", "10"),
        ("small", "14"),
        ("medium", "18"),
        ("large", "24"),
    ]

    for size_key, expected_px in test_cases:
        instance = create_test_instance(
            f"test_{size_key}",
            "canvas_drawtext",
            payload="Test",
            placement={"font_size": size_key}
        )

        config = {"fail_open": True}
        result = apply_pixel(html, instance, config)

        assert f"{expected_px}px" in result


def test_canvas_absolute_positioning():
    """Test that canvas is positioned absolutely."""
    html = """
    <html>
        <body></body>
    </html>
    """

    instance = create_test_instance(
        "test_pixel_009",
        "canvas_drawtext",
        payload="Test"
    )

    config = {"fail_open": True}
    result = apply_pixel(html, instance, config)

    # Check absolute positioning
    assert "position:absolute" in result
    assert "pointer-events:none" in result
    assert "z-index:9999" in result


def test_canvas_list_coordinates():
    """Test canvas with coordinates as list [x, y] format."""
    html = "<html><body></body></html>"

    instance = create_test_instance(
        "test_pixel_010",
        "canvas_drawtext",
        payload="Test",
        placement={
            "coordinates": [50, 24]  # List format like real instances
        }
    )

    config = {"fail_open": True}
    result = apply_pixel(html, instance, config)

    # Check coordinates are used correctly
    assert "50" in result  # x coordinate
    assert "24" in result  # y coordinate


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
