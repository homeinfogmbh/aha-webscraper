"""Parsing functions."""

from functools import cache
from json import dumps
from typing import Iterator, Optional

from bs4 import BeautifulSoup
from requests import get, post

from aha.exceptions import AmbiguousLocations
from aha.exceptions import HTTPError
from aha.exceptions import NoLocationFound
from aha.exceptions import ScrapingError
from aha.functions import frames
from aha.parsers import street_regex
from aha.types import HouseNumber, Location, Pickup, Request


URL = 'https://www.aha-region.de/abholtermine/abfuhrkalender'
Pickups = Iterator[Pickup]
JSON = {
	"gemeinde": "Hannover",
	"jsaus": "",
	"strasse": "00867@Fenskestr.@",
	"hausnr": "25",
	"hausnraddon": "",
	"ladeort": "00867-0023+",
	"anzeigen": "Suchen"
}


def _get_locations() -> Iterator[Location]:
    """Yields locations."""

    params = {'von': 'A', 'bis': 'Z'}

    if (response := get(URL, params=params)).status_code != 200:
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


def get_pickups(location: Location, house_number: HouseNumber, *,
                pickup_location: Optional[str] = None) -> Pickups:
    """Returns pickups for the given location."""

    request = Request(location, house_number, pickup_location)
    data = request.to_json()

    if (response := post(URL, data=data)).status_code != 200:
        raise HTTPError.from_response(response)

    document = BeautifulSoup(response.text, 'html5lib')

    if (table := document.find('table')) is None:
        if pickup_location is not None:
            print(response.text)
            raise ScrapingError('Could not find table element', response.text)

        for pickup_location in document.find(id='ladeort').find_all('option'):
            yield from get_pickups(location, house_number,
                                   pickup_location=pickup_location['value'])

        return

    for _, caption, dates, _ in frames(table.find_all('tr')[1:], 4):
        yield Pickup.from_elements(caption, dates)


def run() -> None:
    """Runs the program."""

    for location in sorted(get_locations()):
        print(location)

    print(find_location('Fenskestr.'))

    try:
        print(find_location('Wilhelm-Busch-Str.'))
    except AmbiguousLocations as locations:
        print('Ambiguos locations:')

        for location in locations:
            print(location)

    print(location := find_location('Wilhelm-Busch-Str.',
                                    district='Nordstadt'))
    print(p1 := list(get_pickups(location, HouseNumber(2))))

    print(location := find_location('Fenskestr.'))
    print(p2 := list(get_pickups(location, HouseNumber(25))))

    print(p1 == p2)
