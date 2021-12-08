"""Web scraping API."""

from functools import cache
from typing import Iterator, Optional, Union

from bs4 import BeautifulSoup
from requests import get, post

from aha.exceptions import AmbiguousLocations
from aha.exceptions import HTTPError
from aha.exceptions import NoLocationFound
from aha.exceptions import ScrapingError
from aha.functions import frames
from aha.parsers import street_regex
from aha.types import HouseNumber, Location, Pickup, Request


__all__ = ['get_locations', 'find_location', 'get_pickups']


PARAMS = {'von': 'A', 'bis': 'Z'}
URL = 'https://www.aha-region.de/abholtermine/abfuhrkalender'


def _get_locations() -> Iterator[Location]:
    """Yields locations."""

    if (response := get(URL, params=PARAMS)).status_code != 200:
        raise HTTPError.from_response(response)

    document = BeautifulSoup(response.text, 'html5lib')

    if (select := document.find(id='strasse')) is None:
        raise ScrapingError('Could not find select element with id "strasse"',
                            response.text)

    for option in select.find_all('option'):
        yield Location.from_string(option['value'])


@cache
def get_locations() -> frozenset[Location]:
    """Returns a set of locations."""

    return frozenset(_get_locations())


def find_location(name: str, *, district: Optional[str] = None) -> Location:
    """Yields locations."""

    try:
        location, *superfluous = sorted(
            location for location in get_locations()
            if street_regex(name).fullmatch(location.name)
            and (district is None or location.district == district)
        )
    except ValueError:
        raise NoLocationFound(name) from None

    if superfluous:
        raise AmbiguousLocations(location, *superfluous)

    return location


def parse_pickups(document: BeautifulSoup, *,
                  pickup_location: Optional[str] = None) -> Iterator[Pickup]:
    """Parses the pickups."""

    if (table := document.find('table')) is None:
        raise ScrapingError('Could not find table element', document)

    # Discard spacing and buttons and skip header row.
    for _, caption, dates, _ in frames(table.find_all('tr')[1:], 4):
        yield Pickup.from_elements(
            caption, dates, pickup_location=pickup_location)


def get_pickup_locations(document: BeautifulSoup) -> Iterator[str]:
    """Yields available pickup locations."""

    for element in document.find(id='ladeort').find_all('option'):
        yield element['value']


def get_pickups(location: Location, house_number: Union[HouseNumber, str], *,
                municipality: str = 'Hannover',
                pickup_location: Optional[str] = None) -> Iterator[Pickup]:
    """Returns pickups for the given location."""

    if isinstance(house_number, str):
        house_number = HouseNumber.from_string(house_number)

    request = Request(location, house_number, municipality, pickup_location)

    if (response := post(URL, data=request.to_json())).status_code != 200:
        raise HTTPError.from_response(response)

    document = BeautifulSoup(response.text, 'html5lib')

    try:
        yield from parse_pickups(document, pickup_location=pickup_location)
    except ScrapingError:
        if not (pickup_locations := list(get_pickup_locations(document))):
            raise

        for pickup_location in pickup_locations:    # pylint: disable=R1704
            yield from get_pickups(
                location, house_number, municipality=municipality,
                pickup_location=pickup_location)
