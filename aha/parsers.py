"""Common data parsers."""

from datetime import date, datetime
from functools import cache
from re import IGNORECASE, Pattern, compile
from typing import Iterator

from bs4.element import Comment, NavigableString, PageElement, Tag


__all__ = ['parse_date', 'street_regex', 'text_content']


STREET_MAP = {
    'strasse': 'str.',
    'straße': 'str',
    'Strasse': 'Str.',
    'Straße': 'Str.'
}


def is_text_element(item: PageElement) -> bool:
    """Determines whether the item is plain text."""

    return isinstance(item, NavigableString) and not isinstance(item, Comment)


def parse_date(string: str) -> date:
    """Extracts dates from HTML elements."""

    _, date_string = string.split(',')  # discard weekday
    date_string = date_string.replace('*', '').strip()
    return datetime.strptime(date_string, '%d.%m.%Y').date()


@cache
def street_regex(street: str) -> Pattern:
    """Returns a regular expression to match the street name."""

    for key, value in STREET_MAP.items():
        if street.endswith(key):
            street = street.replace(key, value)
            break

    return compile(street.replace('.', '.*'), flags=IGNORECASE)


def text_content(element: Tag) -> Iterator[str]:
    """Extracts text content from an HTML element."""

    return map(str, filter(is_text_element, element.contents))
