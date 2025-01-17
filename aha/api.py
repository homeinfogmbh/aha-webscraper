"""Web scraping API."""

from functools import cache
from logging import getLogger
from typing import Any, Iterable, Iterator, Optional, Union

from bs4 import BeautifulSoup
from requests import get, post

from aha.exceptions import AmbiguousLocations
from aha.exceptions import HTTPError
from aha.exceptions import NoLocationFound
from aha.exceptions import ScrapingError
from aha.parsers import street_regex
from aha.types import HouseNumber, Location, Pickup, Request


__all__ = ["LOGGER", "get_locations", "find_location", "get_pickups"]


LOGGER = getLogger("aha-webscraper")
PARAMS = {"von": "A", "bis": "Z"}
URL = "https://www.aha-region.de/abholtermine/abfuhrkalender"


def frames(iterable: Iterable[Any], size: int) -> Iterator[tuple[Any, ...]]:
    """Yields tuples of the given size from the iterable."""

    if size < 1:
        raise ValueError("Size must be >= 1")

    frame = []

    for item in iterable:
        frame.append(item)

        if len(frame) == size:
            yield tuple(frame)
            frame.clear()

    if frame:
        LOGGER.warning("Last frame not filled: %s", frame)


def _get_locations(municipality) -> Iterator[Location]:
    """Yields locations."""
    PARAMS['gemeinde'] = municipality
    if (response := get(URL, params=PARAMS)).status_code != 200:
        raise HTTPError.from_response(response)

    document = BeautifulSoup(response.text, "html5lib")

    if (select := document.find(id="strasse")) is None:
        raise ScrapingError('Could not find select element with id "strasse"', document)

    for option in select.find_all("option"):
        yield Location.from_string(option["value"])


@cache
def get_locations(municipality) -> frozenset[Location]:
    """Returns a set of locations."""

    return frozenset(_get_locations(municipality))


def find_location(name: str, *, district: Optional[str] = None,  municipality: Optional[str] = 'Hannover') -> Location:
    """Yields locations."""

    try:
        location, *superfluous = sorted(
            location
            for location in get_locations(municipality=municipality)
            if street_regex(name).match(location.name)
            and (district is None or location.district == district)
        )
    except ValueError:
        raise NoLocationFound(name) from None

    if superfluous:
        raise AmbiguousLocations(location, *superfluous)

    return location


def parse_pickups(document: BeautifulSoup) -> Iterator[Pickup]:
    """Parses the pickups."""

    if (table := document.find("table")) is None:
        raise ScrapingError("Could not find table element", document)

    # Discard spacing and buttons and skip header row.
    for _, caption, dates, _ in frames(table.find_all("tr")[1:], 4):
        yield Pickup.from_elements(caption, dates)


def get_pickup_locations(document: BeautifulSoup) -> Iterator[str]:
    """Yields available pickup locations."""

    for element in document.find(id="ladeort").find_all("option"):
        yield element["value"]


def _get_pickups(request: Request) -> Iterator[Pickup]:
    """Yields pickups for the given request."""

    if (response := post(URL, data=request.to_json())).status_code != 200:
        raise HTTPError.from_response(response)

    document = BeautifulSoup(response.text, "html5lib")

    try:
        yield from parse_pickups(document)
    except ScrapingError as error:
        try:
            pickup_location, *_ = get_pickup_locations(document)
        except ValueError:
            raise error

        yield from _get_pickups(request.change_location(pickup_location))


def get_pickups(
    location: Location,
    house_number: Union[HouseNumber, str],
    *,
    municipality:Optional[str]= "Hannover",
    pickup_location: Optional[str] = None,
) -> Iterator[Pickup]:
    """Returns pickups for the given location."""

    if isinstance(house_number, str):
        house_number = HouseNumber.from_string(house_number)

    return _get_pickups(Request(location, house_number, municipality, pickup_location))
