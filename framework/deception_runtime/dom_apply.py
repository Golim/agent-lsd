"""
DOM-space deception application handlers.
"""

from deception_runtime.errors import (
    InvalidPlacementError,
    SelectorNotFoundError,
    UnsupportedChannelError,
)
from deception_runtime.html_tools import HTMLDocument
from deception_runtime.logging import StructuredLogger
from deception_runtime.registry import DeceptionInstance

logger = StructuredLogger(__name__)


def _payload_allows_html(instance: DeceptionInstance, config: dict) -> bool:
    """Check whether the payload should be inserted as HTML fragments."""
    if "allow_html" in config:
        return bool(config["allow_html"])

    payload = instance.raw.get("payload")
    return bool(payload.get("allow_html")) if isinstance(payload, dict) else False


def _set_payload_content(
    doc: HTMLDocument, element: object, payload: str, allow_html: bool
) -> None:
    """Set element content as text or HTML fragment."""
    if allow_html:
        doc.set_html(element, payload)
    else:
        doc.set_text(element, payload)


def apply_dom(html: str, instance: DeceptionInstance, config: dict, robots_txt: bool = False) -> str:
    """
    Apply DOM-based deception to HTML.

    Args:
        html: Original HTML
        instance: Deception instance
        config: Configuration dict with fail_open, etc.
        robots_txt: Whether the document is a robots.txt file

    Returns:
        Modified HTML

    Raises:
        SelectorNotFoundError: If required selector not found (only if fail_closed)
        UnsupportedChannelError: If channel/surface not supported
    """
    doc = HTMLDocument(html)

    surface = instance.surface
    placement = instance.placement or {}
    allow_html = _payload_allows_html(instance, config)

    # Get payload (lxml handles HTML escaping automatically when setting text/attributes)
    payload = instance.payload_text or ""

    # Route handlers by surface
    try:
        if surface == "aria_label":
            return _apply_aria_label(doc, instance, payload, placement)
        elif surface == "aria_description":
            return _apply_aria_description(doc, instance, payload, placement)
        elif surface == "hidden_div":
            return _apply_hidden_div(doc, instance, payload, placement, allow_html)
        elif surface == "offscreen_div":
            return _apply_offscreen_div(doc, instance, payload, placement, allow_html)
        elif surface == "meta_tag":
            return _apply_meta_tag(doc, instance, payload)
        elif surface == "text_node":
            return _apply_text_node(doc, instance, payload, placement, allow_html)
        elif surface == "comment":
            return _apply_comment(doc, instance, payload, placement)
        elif surface == "robots_txt":
            if not robots_txt:
                return doc.to_string()  # No changes if not robots.txt
            return _apply_robots_txt(doc, instance, payload)
        else:
            raise UnsupportedChannelError(
                f"Unsupported DOM surface: {surface}", instance_id=instance.instance_id
            )
    except (SelectorNotFoundError, InvalidPlacementError) as e:
        if config.get("fail_open", True):
            logger.warning(
                "DOM application failed, returning original HTML",
                instance_id=instance.instance_id,
                surface=surface,
                error=str(e),
            )
            return html
        else:
            raise


def _apply_aria_label(
    doc: HTMLDocument, instance: DeceptionInstance, payload: str, placement: dict
) -> str:
    """Apply aria-label deception."""
    selector = placement.get("selector")
    if not selector:
        raise InvalidPlacementError(
            "Missing selector for aria_label", instance_id=instance.instance_id
        )

    target = doc.find_element(selector)
    if target is None:
        raise SelectorNotFoundError(
            f"Selector '{selector}' not found", instance_id=instance.instance_id
        )

    current = doc.get_attribute(target, "aria-label")
    if current and payload in current:
        return doc.to_string()

    # Append to existing aria-label or set new one
    doc.append_to_attribute(target, "aria-label", payload, separator=". ")

    return doc.to_string()


def _apply_aria_description(
    doc: HTMLDocument, instance: DeceptionInstance, payload: str, placement: dict
) -> str:
    """Apply aria-description deception."""
    selector = placement.get("selector")
    if not selector:
        raise InvalidPlacementError(
            "Missing selector for aria_description", instance_id=instance.instance_id
        )

    target = doc.find_element(selector)
    if target is None:
        raise SelectorNotFoundError(
            f"Selector '{selector}' not found", instance_id=instance.instance_id
        )

    current = doc.get_attribute(target, "aria-description")
    if current and payload in current:
        return doc.to_string()

    # Append to existing aria-description or set new one
    doc.append_to_attribute(target, "aria-description", payload, separator=". ")

    return doc.to_string()


def _apply_hidden_div(
    doc: HTMLDocument,
    instance: DeceptionInstance,
    payload: str,
    placement: dict,
    allow_html: bool,
) -> str:
    """Apply hidden div deception."""
    selector = placement.get("selector", "body")
    target = doc.find_element(selector)

    if target is None:
        raise SelectorNotFoundError(
            f"Selector '{selector}' not found", instance_id=instance.instance_id
        )

    current_html = doc.to_string()
    if 'style="display:none;"' in current_html and payload in current_html:
        return current_html

    # Create hidden div
    div = doc.create_element("div", style="display:none;")
    _set_payload_content(doc, div, payload, allow_html)

    # Insert based on placement.insertion
    insertion = placement.get("insertion", "append")
    doc.insert_element(div, target, insertion)

    return doc.to_string()


def _apply_offscreen_div(
    doc: HTMLDocument,
    instance: DeceptionInstance,
    payload: str,
    placement: dict,
    allow_html: bool,
) -> str:
    """Apply offscreen div deception (accessible but visually hidden)."""
    selector = placement.get("selector", "body")
    target = doc.find_element(selector)

    if target is None:
        raise SelectorNotFoundError(
            f"Selector '{selector}' not found", instance_id=instance.instance_id
        )

    current_html = doc.to_string()
    if 'style="position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden;"' in current_html and payload in current_html:
        return current_html

    # Create offscreen div (accessible to screen readers)
    div = doc.create_element(
        "div",
        style="position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden;",
    )
    _set_payload_content(doc, div, payload, allow_html)

    # Insert based on placement.insertion
    insertion = placement.get("insertion", "append")
    doc.insert_element(div, target, insertion)

    return doc.to_string()


def _apply_meta_tag(
    doc: HTMLDocument, instance: DeceptionInstance, payload: str
) -> str:
    """Apply meta tag deception."""
    # Find head element
    head = doc.find_element("head")
    if head is None:
        raise SelectorNotFoundError(
            "No <head> element found", instance_id=instance.instance_id
        )

    current_html = doc.to_string()
    if 'name="runtime-note"' in current_html and payload in current_html:
        return current_html

    # Create meta tag
    meta = doc.create_element(
        "meta",
        name="runtime-note",
        content=payload,
    )

    doc.insert_element(meta, head, "append")

    return doc.to_string()


def _apply_text_node(
    doc: HTMLDocument,
    instance: DeceptionInstance,
    payload: str,
    placement: dict,
    allow_html: bool,
) -> str:
    """Apply visible text node deception."""
    selector = placement.get("selector", "body")
    target = doc.find_element(selector)

    if target is None:
        raise SelectorNotFoundError(
            f"Selector '{selector}' not found", instance_id=instance.instance_id
        )

    current_html = doc.to_string()
    if payload in current_html and ("<p" in current_html or "<span" in current_html):
        return current_html

    # Create span for inline or p for block
    tag = "span" if placement.get("inline", False) else "p"
    elem = doc.create_element(
        tag,
    )
    _set_payload_content(doc, elem, payload, allow_html)

    # Insert based on placement.insertion
    insertion = placement.get("insertion", "append")
    doc.insert_element(elem, target, insertion)

    return doc.to_string()


def _apply_comment(
    doc: HTMLDocument, instance: DeceptionInstance, payload: str, placement: dict
) -> str:
    """Apply HTML comment deception."""
    # For comments, we can't easily use the DOM API, so inject as string
    from deception_runtime.html_tools import inject_before_closing_tag

    # Escape comment delimiters in payload
    safe_payload = payload.replace("-->", "--&gt;")
    current_html = doc.to_string()
    if safe_payload in current_html and "<!--" in current_html:
        return current_html
    comment = f"<!-- {safe_payload} -->"

    # Inject before </body> or at end
    return inject_before_closing_tag(doc.to_string(), "body", comment)


def _apply_robots_txt(
    doc: HTMLDocument, instance: DeceptionInstance, payload: str
) -> str:
    """Apply robots.txt deception."""
    # Append the payload to the robots.txt content
    return doc.to_string() + "<br><br>" + payload
