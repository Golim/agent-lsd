"""
Pixel-space deception application handlers.
"""

import base64
import json

from deception_runtime.errors import InvalidPlacementError, UnsupportedChannelError
from deception_runtime.html_tools import HTMLDocument, inject_before_closing_tag
from deception_runtime.logging import StructuredLogger
from deception_runtime.registry import DeceptionInstance

logger = StructuredLogger(__name__)

# Font size mapping
FONT_SIZE_MAP = {
    "micro": 10,
    "small": 14,
    "medium": 18,
    "large": 24,
}


def apply_pixel(html: str, instance: DeceptionInstance, config: dict) -> str:
    """
    Apply pixel-based deception to HTML.

    Args:
        html: Original HTML
        instance: Deception instance
        config: Configuration dict

    Returns:
        Modified HTML with injected canvas/script

    Raises:
        UnsupportedChannelError: If surface not supported
    """
    doc = HTMLDocument(html)

    surface = instance.surface
    placement = instance.placement or {}

    try:
        if surface == "canvas_drawtext":
            return _apply_canvas_drawtext(html, doc, instance, placement)
        elif surface == "css_pseudo_element":
            return _apply_css_pseudo(html, doc, instance, placement)
        elif surface == "low_contrast_overlay":
            return _apply_low_contrast_overlay(html, doc, instance, placement)
        elif surface == "background_image":
            return _apply_background_image(html, doc, instance, placement)
        elif surface == "svg_path_text":
            return _apply_svg_path_text(html, doc, instance, placement)
        else:
            raise UnsupportedChannelError(
                f"Unsupported pixel surface: {surface}",
                instance_id=instance.instance_id,
            )
    except Exception as e:
        if config.get("fail_open", True):
            logger.warning(
                "Pixel application failed, returning original HTML",
                instance_id=instance.instance_id,
                surface=surface,
                error=str(e),
            )
            return html
        else:
            raise


def _apply_canvas_drawtext(
    html: str, doc: HTMLDocument, instance: DeceptionInstance, placement: dict
) -> str:
    """Apply canvas drawtext deception."""
    payload = instance.payload_text or ""

    # Get placement details
    canvas_id = placement.get("canvas_id", f"runtime-canvas-{instance.instance_id}")
    coordinates = placement.get("coordinates", {"x": 10, "y": 20})

    # Handle coordinates as both list [x, y] and dict {"x": x, "y": y}
    if isinstance(coordinates, list):
        x = coordinates[0] if len(coordinates) > 0 else 10
        y = coordinates[1] if len(coordinates) > 1 else 20
    else:
        x = coordinates.get("x", 10)
        y = coordinates.get("y", 20)
    opacity = placement.get("opacity", 1.0)
    font_size_key = placement.get("font_size", "medium")
    font_size = FONT_SIZE_MAP.get(font_size_key, 18)
    color = placement.get("color", "#000000")

    # Encode payload to base64 to reduce DOM leakage
    payload_b64 = base64.b64encode(payload.encode()).decode()

    # Check if canvas already exists
    canvas_elem = doc.find_element(f"#{canvas_id}")

    if canvas_elem is None:
        # Create canvas element
        selector = placement.get("selector", "body")
        target = doc.find_element(selector)
        if target is None:
            logger.warning(f"Target selector '{selector}' not found, using body")
            target = doc.find_element("body")
            if target is None:
                raise InvalidPlacementError(
                    "No body element found", instance_id=instance.instance_id
                )

        # Create canvas with absolute positioning
        canvas = doc.create_element(
            "canvas",
            id=canvas_id,
            style=f"position:absolute;top:0;left:0;pointer-events:none;z-index:9999;",
        )
        doc.insert_element(canvas, target, "append")

    # Generate JavaScript to draw on canvas
    js_code = f"""
    <script>
    (function() {{
        function drawOverlay() {{
            var canvas = document.getElementById('{canvas_id}');
            if (!canvas) return;

            var ctx = canvas.getContext('2d');
            if (!ctx) return;

            // Set canvas size to window size
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;

            // Decode payload
            var payload = atob('{payload_b64}');

            // Set drawing properties
            ctx.globalAlpha = {opacity};
            ctx.font = '{font_size}px monospace';
            ctx.fillStyle = '{color}';
            ctx.textBaseline = 'top';

            // Draw text
            ctx.fillText(payload, {x}, {y});
        }}

        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', drawOverlay);
        }} else {{
            drawOverlay();
        }}
    }})();
    </script>
    """

    # Inject script before </body>
    modified_html = doc.to_string()
    return inject_before_closing_tag(modified_html, "body", js_code)


def _apply_css_pseudo(
    html: str, doc: HTMLDocument, instance: DeceptionInstance, placement: dict
) -> str:
    """Apply CSS pseudo-element deception."""
    payload = instance.payload_text or ""
    selector = placement.get("selector", "body")
    pseudo = placement.get("pseudo", "::after")
    font_size_key = placement.get("font_size", "medium")
    font_size = FONT_SIZE_MAP.get(font_size_key, 18)
    color = placement.get("color", "#000000")
    position = placement.get("position", {"top": "10px", "left": "10px"})

    # Escape payload for CSS content
    escaped_payload = payload.replace('"', '\\"').replace("'", "\\'")
    current_html = doc.to_string()
    if f'content: "{escaped_payload}"' in current_html and f"{selector}{pseudo}" in current_html:
        return current_html

    # Generate CSS
    css_code = f"""
    <style>
    {selector}{pseudo} {{
        content: "{escaped_payload}";
        position: absolute;
        top: {position.get("top", "10px")};
        left: {position.get("left", "10px")};
        font-size: {font_size}px;
        color: {color};
        pointer-events: none;
        z-index: 9999;
        display: block;
    }}
    </style>
    """

    # Inject before </head> or </body>
    modified_html = doc.to_string()
    if "<head>" in modified_html:
        return inject_before_closing_tag(modified_html, "head", css_code)
    else:
        return inject_before_closing_tag(modified_html, "body", css_code)


def _apply_low_contrast_overlay(
    html: str, doc: HTMLDocument, instance: DeceptionInstance, placement: dict
) -> str:
    """Apply a low-contrast overlay deception."""
    color = placement.get(
        "color", "rgba(255, 0, 0, 0.1)"
    )  # Default to a light red overlay
    selector = placement.get("selector", "body")
    current_html = doc.to_string()
    if f"{selector}::before" in current_html and f"background-color: {color}" in current_html:
        return current_html

    # Generate CSS for the overlay
    css_code = f"""
    <style>
    {selector}::before {{
        content: "";
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: {color};
        pointer-events: none;
        z-index: 9998;
        display: block !important;
    }}
    </style>
    """

    # Inject before </head> or </body>
    modified_html = doc.to_string()
    if "<head>" in modified_html:
        return inject_before_closing_tag(modified_html, "head", css_code)
    else:
        return inject_before_closing_tag(modified_html, "body", css_code)


def _apply_background_image(
    html: str, doc: HTMLDocument, instance: DeceptionInstance, placement: dict
) -> str:
    """Generate an image on the fly and set it as a background image."""
    payload = instance.payload_text or ""
    selector = placement.get("selector", "body")

    # Create a simple image with the payload text (for demonstration, using a data URI)
    # In a real implementation, you might generate an actual image file or use a service
    # Build SVG separately to avoid nested f-string/quoting issues, then encode
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="50"><text x="10" y="20" font-size="16">{}</text></svg>'.format(payload)
    img_data_uri = "data:image/svg+xml;base64,{b64}".format(
        b64=base64.b64encode(svg.encode()).decode()
    )
    current_html = doc.to_string()
    if img_data_uri in current_html:
        return current_html

    # Generate CSS to set the background image
    css_code = f"""
    <style>
    {selector} {{
        background-image: url('{img_data_uri}');
        background-repeat: no-repeat;
        background-position: 10px 10px;
        pointer-events: none;
        z-index: 9997;
        height: 10%;
        display: block !important;
    }}
    </style>
    """

    # Inject before </head> or </body>
    modified_html = doc.to_string()
    if "<head>" in modified_html:
        return inject_before_closing_tag(modified_html, "head", css_code)
    else:
        return inject_before_closing_tag(modified_html, "body", css_code)


def _apply_svg_path_text(
    html: str, doc: HTMLDocument, instance: DeceptionInstance, placement: dict
) -> str:
    """Apply text along an SVG path.
    As of now, the SVG is injected into the body.
    The selector is ignored. TODO!
    """
    payload = instance.payload_text or ""
    selector = placement.get("selector", "body")
    current_html = doc.to_string()
    if f"<textPath href=\"#text-path\">{payload}</textPath>" in current_html:
        return current_html

    # Create SVG with text along a path
    svg_code = f"""
    <svg width="400" height="100" style="position:absolute;top:100px;left:100px;pointer-events:none;z-index:9999;">
        <defs>
            <path id="text-path" d="M 10 50 Q 200 0 390 50" />
        </defs>
        <text font-size="16" fill="#000000">
            <textPath href="#text-path">{payload}</textPath>
        </text>
    </svg>
    """

    # Inject SVG into the target element
    modified_html = doc.to_string()
    target_elem = doc.find_element(selector)
    if target_elem is None:
        logger.warning(f"Target selector '{selector}' not found, using body")
        target_elem = doc.find_element("body")
        if target_elem is None:
            raise InvalidPlacementError(
                "No body element found", instance_id=instance.instance_id
            )

    return inject_before_closing_tag(modified_html, "body", svg_code)
