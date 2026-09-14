"""
HTML parsing and manipulation utilities.

Supports lxml (preferred) or beautifulsoup4 fallback.
"""

import html as html_module
import re
from typing import Any

from deception_runtime.errors import DependencyMissingError, HTMLParsingError
from deception_runtime.logging import StructuredLogger

logger = StructuredLogger(__name__)

# Try to import HTML parsing libraries
_HTML_PARSER: str | None = None
_lxml_available = False
_bs4_available = False

try:
    from lxml import etree, html as lxml_html
    _lxml_available = True
    _HTML_PARSER = "lxml"
    logger.debug("Using lxml for HTML parsing")
except ImportError:
    pass


def _class_contains_expr(class_name: str) -> str:
    """Build an XPath class-membership check for a single class token."""
    return (
        "contains(concat(' ', normalize-space(@class), ' '), "
        f"' {class_name} ')"
    )


def _xpath_for_simple_selector(selector: str) -> str | None:
    """
    Translate a small subset of CSS selectors to XPath.

    We only need enough for the selectors used by this project when cssselect
    is unavailable: tag names, ids, classes, and simple tag+id/tag+class forms.
    """
    selector = selector.strip()
    if not selector:
        return None

    if selector == "*":
        return "//*"

    # `#id`
    if selector.startswith("#") and selector.count("#") == 1 and "." not in selector:
        return f'//*[@id="{selector[1:]}"]'

    # `.class`
    if selector.startswith(".") and selector.count(".") == 1 and "#" not in selector:
        return f'//*[{_class_contains_expr(selector[1:])}]'

    # `tag`, `tag#id`, `tag.class`
    match = re.fullmatch(
        r"(?P<tag>[a-zA-Z][a-zA-Z0-9_-]*)(?:(?P<id>#[a-zA-Z0-9_-]+)|(?P<class>\.[a-zA-Z0-9_-]+))?",
        selector,
    )
    if not match:
        return None

    tag = match.group("tag")
    id_part = match.group("id")
    class_part = match.group("class")

    conditions: list[str] = []
    if id_part:
        conditions.append(f'@id="{id_part[1:]}"')
    if class_part:
        conditions.append(_class_contains_expr(class_part[1:]))

    if conditions:
        return f"//{tag}[{' and '.join(conditions)}]"
    return f"//{tag}"


def _xpath_find_first(doc: Any, selector: str) -> Any | None:
    """Fallback element lookup for environments without cssselect."""
    xpath = _xpath_for_simple_selector(selector)
    if not xpath:
        return None
    results = doc.xpath(xpath)
    return results[0] if results else None


def _xpath_find_all(doc: Any, selector: str) -> list[Any]:
    """Fallback multi-element lookup for environments without cssselect."""
    xpath = _xpath_for_simple_selector(selector)
    if not xpath:
        return []
    return doc.xpath(xpath)

if not _lxml_available:
    try:
        from bs4 import BeautifulSoup
        _bs4_available = True
        _HTML_PARSER = "bs4"
        logger.debug("Using BeautifulSoup4 for HTML parsing")
    except ImportError:
        pass


def check_html_parser_available() -> None:
    """
    Check if an HTML parser is available.

    Raises:
        DependencyMissingError: If no parser is available
    """
    if _HTML_PARSER is None:
        raise DependencyMissingError(
            "lxml or beautifulsoup4",
            "No HTML parser available. Install lxml (preferred) or beautifulsoup4: "
            "pip install lxml OR pip install beautifulsoup4"
        )


class HTMLDocument:
    """
    Wrapper for HTML document manipulation.

    Abstracts over lxml and BeautifulSoup4.
    """

    def __init__(self, html: str):
        """
        Parse HTML document.

        Args:
            html: HTML string to parse

        Raises:
            HTMLParsingError: If parsing fails
        """
        check_html_parser_available()

        self._original_html = html
        self._parser = _HTML_PARSER
        self._doc: Any = None

        try:
            if _HTML_PARSER == "lxml":
                # Use lxml html parser with proper document handling
                self._doc = lxml_html.document_fromstring(html)
            elif _HTML_PARSER == "bs4":
                # Use BeautifulSoup with html.parser
                self._doc = BeautifulSoup(html, "html.parser")
            else:
                raise HTMLParsingError("No HTML parser available")
        except Exception as e:
            raise HTMLParsingError(f"Failed to parse HTML: {e}") from e

    def find_element(self, selector: str) -> Any | None:
        """
        Find first element matching CSS selector.

        Args:
            selector: CSS selector

        Returns:
            Element or None if not found
        """
        try:
            if _HTML_PARSER == "lxml":
                # Prefer cssselect when present, but fall back to XPath for the
                # simple selectors used by the challenges.
                try:
                    results = self._doc.cssselect(selector)
                    return results[0] if results else None
                except Exception:
                    return _xpath_find_first(self._doc, selector)
            elif _HTML_PARSER == "bs4":
                # BeautifulSoup select_one
                return self._doc.select_one(selector)
        except Exception as e:
            logger.debug(f"Selector '{selector}' failed", error=str(e))
            return None

    def find_elements(self, selector: str) -> list[Any]:
        """
        Find all elements matching CSS selector.

        Args:
            selector: CSS selector

        Returns:
            List of elements (may be empty)
        """
        try:
            if _HTML_PARSER == "lxml":
                try:
                    return self._doc.cssselect(selector)
                except Exception:
                    return _xpath_find_all(self._doc, selector)
            elif _HTML_PARSER == "bs4":
                return self._doc.select(selector)
            return []
        except Exception as e:
            logger.debug(f"Selector '{selector}' failed", error=str(e))
            return []

    def create_element(self, tag: str, **attrs: str) -> Any:
        """
        Create a new HTML element.

        Args:
            tag: Element tag name
            **attrs: Element attributes

        Returns:
            New element
        """
        if _HTML_PARSER == "lxml":
            elem = etree.Element(tag)
            for key, value in attrs.items():
                elem.set(key.replace("_", "-"), value)
            return elem
        elif _HTML_PARSER == "bs4":
            from bs4 import Tag
            elem = Tag(name=tag)
            for key, value in attrs.items():
                elem[key.replace("_", "-")] = value
            return elem
        raise HTMLParsingError("No parser available")

    def insert_element(self, element: Any, target: Any, position: str = "append") -> None:
        """
        Insert element relative to target.

        Args:
            element: Element to insert
            target: Target element
            position: 'append', 'prepend', or 'replace'
        """
        if _HTML_PARSER == "lxml":
            if position == "append":
                target.append(element)
            elif position == "prepend":
                target.insert(0, element)
            elif position == "replace":
                parent = target.getparent()
                if parent is not None:
                    parent.replace(target, element)
        elif _HTML_PARSER == "bs4":
            if position == "append":
                target.append(element)
            elif position == "prepend":
                target.insert(0, element)
            elif position == "replace":
                target.replace_with(element)

    def set_attribute(self, element: Any, attr: str, value: str) -> None:
        """
        Set element attribute.

        Args:
            element: Target element
            attr: Attribute name
            value: Attribute value
        """
        if _HTML_PARSER == "lxml":
            element.set(attr, value)
        elif _HTML_PARSER == "bs4":
            element[attr] = value

    def get_attribute(self, element: Any, attr: str) -> str | None:
        """
        Get element attribute value.

        Args:
            element: Target element
            attr: Attribute name

        Returns:
            Attribute value or None
        """
        if _HTML_PARSER == "lxml":
            return element.get(attr)
        elif _HTML_PARSER == "bs4":
            return element.get(attr)
        return None

    def append_to_attribute(self, element: Any, attr: str, value: str, separator: str = " ") -> None:
        """
        Append value to attribute (useful for aria-label, class, etc.).

        Args:
            element: Target element
            attr: Attribute name
            value: Value to append
            separator: Separator between values
        """
        current = self.get_attribute(element, attr)
        if current:
            new_value = f"{current}{separator}{value}"
        else:
            new_value = value
        self.set_attribute(element, attr, new_value)

    def set_text(self, element: Any, text: str) -> None:
        """
        Set element text content.

        Args:
            element: Target element
            text: Text content
        """
        if _HTML_PARSER == "lxml":
            element.text = text
        elif _HTML_PARSER == "bs4":
            element.string = text

    def set_html(self, element: Any, fragment: str) -> None:
        """
        Replace an element's contents with an HTML fragment.

        Args:
            element: Target element
            fragment: HTML fragment to insert as children/content
        """
        if not fragment:
            self.set_text(element, "")
            return

        try:
            if _HTML_PARSER == "lxml":
                # Clear current contents, then splice in the parsed fragment nodes.
                element.text = None
                for child in list(element):
                    element.remove(child)

                container = lxml_html.fragment_fromstring(
                    fragment, create_parent="div"
                )
                if container.text:
                    element.text = container.text
                for child in list(container):
                    element.append(child)
            elif _HTML_PARSER == "bs4":
                from bs4 import BeautifulSoup

                element.clear()
                container = BeautifulSoup(fragment, "html.parser")
                for child in list(container.contents):
                    element.append(child)
        except Exception:
            self.set_text(element, fragment)

    def to_string(self) -> str:
        """
        Convert document back to HTML string.

        Returns:
            HTML string
        """
        try:
            if _HTML_PARSER == "lxml":
                # Convert back to string
                return lxml_html.tostring(self._doc, encoding="unicode", method="html")
            elif _HTML_PARSER == "bs4":
                return str(self._doc)
            return self._original_html
        except Exception as e:
            logger.error("Failed to serialize HTML", error=str(e))
            return self._original_html


def escape_html(text: str) -> str:
    """
    Escape HTML special characters.

    Args:
        text: Plain text

    Returns:
        HTML-escaped text
    """
    return html_module.escape(text)


def inject_before_closing_tag(html: str, tag: str, content: str) -> str:
    """
    Inject content before closing tag (e.g., </body> or </head>).

    Args:
        html: HTML string
        tag: Tag name (e.g., 'body', 'head')
        content: Content to inject

    Returns:
        Modified HTML
    """
    closing_tag = f"</{tag}>"
    if closing_tag in html:
        return html.replace(closing_tag, f"{content}\n{closing_tag}", 1)
    else:
        # Fallback: append to end
        return html + "\n" + content
