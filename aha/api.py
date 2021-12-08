"""Parsing functions."""

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
Pickups = Iterator[Pickup]


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

    locations = sorted(
        location for location in get_locations()
        if street_regex(name).fullmatch(location.name)
        and (district is None or location.district == district)
    )

    if not locations:
        raise NoLocationFound(name)

    if len(locations) == 1:
        return locations[0]

    raise AmbiguousLocations(locations)


def get_pickups(location: Location, house_number: Union[HouseNumber, str], *,
                municipality: str = 'Hannover',
                pickup_location: Optional[str] = None) -> Pickups:
    """Returns pickups for the given location."""

    if isinstance(house_number, str):
        house_number = HouseNumber.from_string(house_number)

    request = Request(location, house_number, municipality, pickup_location)
    data = request.to_json()

    if (response := post(URL, data=data)).status_code != 200:
        raise HTTPError.from_response(response)

    document = BeautifulSoup(response.text, 'html5lib')

    if (table := document.find('table')) is None:
        if pickup_location is not None:
            print(response.text)
            raise ScrapingError('Could not find table element', response.text)

        for element in document.find(id='ladeort').find_all('option'):
            yield from get_pickups(location, house_number,
                                   pickup_location=element['value'])

        return

    for _, caption, dates, _ in frames(table.find_all('tr')[1:], 4):
        yield Pickup.from_elements(caption, dates)
