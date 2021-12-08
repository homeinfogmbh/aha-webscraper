"""Common exceptions."""

from __future__ import annotations
from typing import Iterator

from bs4 import BeautifulSoup
from requests import Response

from aha.types import Location


__all__ = [
    'AmbiguousLocations',
    'HTTPError',
    'NoLocationFound',
    'ScrapingError'
]


class AmbiguousLocations(Exception):
    """Indicates an ambiguous locations match."""

    def __init__(self, *locations: Location):
        super().__init__(locations)
        self.locations = locations

    def __iter__(self) -> Iterator[Location]:
        return iter(self.locations)


class HTTPError(Exception):
    """Indicates an HTTP error code."""

    def __init__(self, text: str, status_code: int):
        super().__init__(text, status_code)
        self.text = text
        self.status_code = status_code

    @classmethod
    def from_response(cls, response: Response) -> HTTPError:
        """Creates an HTTP error from a requests response object."""
        return cls(response.text, response.status_code)


class NoLocationFound(Exception):
    """Indicats that no matching location was found."""


class ScrapingError(Exception):
    """Indicates an error during scraping."""

    def __init__(self, message: str, document: BeautifulSoup):
        super().__init__(message)
        self.message = message
        self.document = document
