"""Common data parsers."""

from datetime import date, datetime
from functools import cache
from re import IGNORECASE, Pattern, compile     # pylint: disable=W0622
from typing import Iterator

from bs4.element import NavigableString, Tag, Comment


__all__ = ['parse_date', 'street_regex', 'text_content']


STREET_MAP = {
    'strasse': 'str.',
    'straße': 'str',
    'Strasse': 'Str.',
    'Straße': 'Str.'
}


def parse_date(string: str) -> date:
    """Extracts dates from HTML elements."""

    _, date_string = string.split(',')  # discard weekday
    return datetime.strptime(date_string.strip(), '%d.%m.%Y').date()


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

    for item in element.contents:
        if isinstance(item, NavigableString) and not isinstance(item, Comment):
            yield item