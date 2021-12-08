"""AHA garbage collection dates web scraper."""

from __future__ import annotations
from argparse import ArgumentParser, Namespace
from contextlib import suppress
from datetime import date, datetime
from functools import lru_cache
from json import dumps
from re import IGNORECASE, Pattern, compile     # pylint: disable=W0622
from string import ascii_letters
from urllib.parse import urljoin
from typing import Iterable, Iterator, List, NamedTuple
from xml.etree.ElementTree import Element

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Comment
from requests import get

from mdb import Address


__all__ = ['LocationNotFound', 'AhaDisposalClient', 'PickupSolution', 'main']


BASE_URL = 'https://www.aha-region.de/'
URL = urljoin(BASE_URL, 'abholtermine/abfuhrkalender')
DEFAULT_DISTRICT = 'Hannover'


STREET_MAP = {
    'strasse': 'str.',
    'straße': 'str',
    'Strasse': 'Str.',
    'Straße': 'Str.'
}


class NotAPickup(Exception):
    """Indicates that the respective row is not a Pickup."""


class LocationNotFound(Exception):
    """Indicates that the respective location could not be found."""

    def __init__(self, street: str):
        """Sets the street."""
        super().__init__(street)
        self.street = street


class LoadingLocations(Exception):
    """Indicates that the next possible pickup
    is at the given loading locations.
    """

    def __init__(self, locations):
        super().__init__(locations)
        self.locations = locations

    def __iter__(self):
        for location in self.locations:
            yield location


class Request(NamedTuple):
    """Pickups request."""

    district: str
    street: str
    house_number: str
    loading_location: str

    def split_houseno(self) -> tuple[str, str]:
        """Splits the house number."""
        house_number = ''
        house_number_addon = ''

        for char in self.house_number:
            if char.isdigit():
                house_number += char
            elif char in ascii_letters:
                house_number_addon += char

        return (house_number, house_number_addon)

    def to_json(self) -> dict:
        """Returns a JSON-ish dict."""
        house_number, house_number_addon = self.split_houseno()

        return {
            'gemeinde': self.district,
            'jsaus': '',    # TODO: What is this?
            'strasse': self.street,
            'hausnr': house_number,
            'hausnraddon': house_number_addon,
            'ladeort': self.loading_location,
            'anzeigen': 'Suchen'
        }


class PickupDate(NamedTuple):
    """A pickup date."""

    date: date
    weekday: str
    exceptional: bool

    @classmethod
    def from_string(cls, string: str) -> PickupDate:
        """Creates a new pickup date from the provided string."""
        weekday, date = string.split(', ')  # pylint: disable=W0621
        exceptional = date.endswith('*')
        date = date.strip('*').strip()
        date = datetime.strptime(date, '%d.%m.%Y').date()
        return cls(date, weekday, exceptional)

    def to_json(self) -> dict:
        """Returns a JSON-ish dictionary."""
        return {
            'date': self.date.isoformat(),
            'weekday': self.weekday,
            'exceptional': self.exceptional
        }


class Pickup(NamedTuple):
    """Garbage pickup."""

    type: str
    weekday: str
    interval: str
    image_link: str
    next_dates: List[PickupDate]

    @classmethod
    def from_html(cls, row: Element) -> Pickup:
        """Creates pickup information from an HTML <td> row."""
        try:
            image_link, typ, weekday, next_dates, interval = row.find_all('td')
        except ValueError:
            raise NotAPickup(row) from None

        image_link = image_link.find('img')['src']
        typ = typ.get_text().strip()
        weekday = weekday.get_text().strip()
        interval = interval.get_text().strip()
        next_pickups = []

        for next_date in html_content(next_dates.contents):
            with suppress(ValueError):
                pickup_date = PickupDate.from_string(next_date)
                next_pickups.append(pickup_date)

        return cls(typ, weekday, interval, image_link, next_pickups)

    def to_json(self) -> dict:
        """Returns a JSON-ish dictionary."""
        return {
            'type': self.type,
            'weekday': self.weekday,
            'interval': self.interval,
            'image_link': urljoin(BASE_URL, self.image_link),
            'next_dates': [date.to_json() for date in self.next_dates]
        }


class Location(NamedTuple):
    """Basic location."""

    code: str
    street: str
    house_number: str
    district: str

    def __str__(self):
        """Returns the AHA string representation."""
        return '@'.join((self.code, self.street, self.district))

    @classmethod
    def from_string(cls, string: str, house_number: str = None) -> Location:
        """Creates a pickup location from the provided string."""
        code, street, district = string.split('@')
        return cls(code, street, house_number, district)

    @classmethod
    def from_html(cls, option: Element) -> Location:
        """Creates a loading location from HTML."""
        code = option['value']   # Code must not be stripped.
        content = option.get_text().strip()
        address, district = content.split(',')
        street, house_number = address.rsplit(maxsplit=1)
        house_number = house_number.strip()
        district = district.strip().strip('/').strip()
        return cls(code, street, house_number, district)

    @property
    def address(self) -> str:
        """Returns street and house number."""
        return f'{self.street} {self.house_number}'

    def to_json(self) -> dict:
        """Returns a JSON-ish dictionary."""
        return {
            'code': self.code,
            'street': self.street,
            'house_number': self.house_number,
            'district': self.district
        }


class PickupSolution(NamedTuple):
    """A series of loading information."""

    location: Location
    pickups: List[Pickup]

    def __str__(self):
        """Returns the respective JSON data."""
        return dumps(self.to_json(), indent=2)

    def to_json(self) -> dict:
        """Returns a JSON-ish list."""
        json = self.location.to_json()
        json['pickups'] = [pickup.to_json() for pickup in self.pickups]
        return json


class AhaDisposalClient:
    """Client to web-scrape the AHA garbage disposal dates API."""

    def __init__(self, district=DEFAULT_DISTRICT):
        """Sets URL and district."""
        self.district = district

    def _pickup_locations(self, house_number: str = None) \
            -> Iterator[Location]:
        """Yields the respective pickup addresses."""
        reply = get(URL, params={'gemeinde': self.district})

        if reply.status_code == 200:
            html = BeautifulSoup(reply.text, 'html5lib')
            options = html.find(id='strasse').find_all('option')

            for option in options:
                yield Location.from_string(
                    str(option['value']), house_number=house_number)

    def _get_pickup_locations(self, street: str, house_number: str = None) \
            -> Iterator[Location]:
        """Gets a location by the respective street name."""
        for pickup_location in self._pickup_locations(
                house_number=house_number):
            if street_regex(street).match(pickup_location.street):
                yield pickup_location

    def _get_pickup_location(self, street: str, house_number: str = None) \
            -> Location:
        """Gets a location by the respective street name."""
        for pickup_location in self._get_pickup_locations(
                street, house_number=house_number):
            return pickup_location

        raise LocationNotFound(street)

    def by_street_houseno(self, street: str, house_number: str) \
            -> Iterator[PickupSolution]:
        """Yields pickup solutions by the respective address."""
        house_number = normalize_houseno(house_number)
        pickup_location = self._get_pickup_location(
            street, house_number=house_number)

        try:
            pickups = tuple(by_pickup_location(pickup_location, house_number))
        except LoadingLocations as loading_locations:
            for loading_location in loading_locations:
                pickups = tuple(by_loading_location(
                    loading_location, pickup_location))
                yield PickupSolution(loading_location, pickups)
        else:
            yield PickupSolution(pickup_location, pickups)

    def by_address(self, address: Address) -> Iterator[PickupSolution]:
        """Yields the respective pickups by the respective address."""
        return self.by_street_houseno(address.street, address.house_number)


@lru_cache()
def street_regex(street: str) -> Pattern:
    """Returns a regular expression to match the street name."""

    for key, value in STREET_MAP.items():
        if street.endswith(key):
            street = street.replace(key, value)
            break

    return compile(street.replace('.', '.*'), flags=IGNORECASE)


@lru_cache()
def normalize_houseno(house_number: str) -> str:
    """Tries to remove leading zeros from the house number."""

    return house_number.strip().lstrip('0')


def html_content(items: Iterable[Element]) -> Iterator[Element]:
    """Yields HTML like content."""

    for item in items:
        if isinstance(item, NavigableString) and not isinstance(item, Comment):
            yield item


def parse_pickups(table: Element) -> Iterator[Pickup]:
    """Parses pickups from the provided table."""

    tbody = table.find('tbody')

    if tbody is not None:
        rows = tbody.find_all('tr')

        for row in rows[1:-1]:    # Skip table header and footer.
            with suppress(NotAPickup):
                yield Pickup.from_html(row)


def get_loading_locations(html: Element) -> Iterator[Location]:
    """Yieds loading location from the respective select element."""

    select = html.find(id='ladeort')

    if select is not None:
        for option in select.find_all('option'):
            yield Location.from_html(option)


def by_pickup_location(pickup_location: str, house_number: str):
    """Returns the respective pickups by a pickup location."""

    params = {'strasse': str(pickup_location), 'hausnr': house_number}
    reply = get(URL, params=params)

    if reply.status_code == 200:
        html = BeautifulSoup(reply.text, 'html5lib')
        table = html.find('table')

        if table is None:
            raise LoadingLocations(tuple(get_loading_locations(html)))

        for pickup in parse_pickups(table):
            yield pickup


def by_loading_location(loading_location: Location,
                        pickup_location: Location) -> Iterator[Pickup]:
    """Returns the respective pickups by a loading location."""

    params = {
        'strasse': str(pickup_location),
        'hausnr': pickup_location.house_number,
        'ladeort': loading_location.code
    }
    reply = get(URL, params=params)

    if reply.status_code == 200:
        html = BeautifulSoup(reply.text, 'html5lib')
        table = html.find('table')

        if table is not None:
            for pickup in parse_pickups(table):
                yield pickup


def get_args() -> Namespace:
    """Parses the command line arguments."""

    parser = ArgumentParser(description='Web scrape AHA pickup locations.')
    parser.add_argument('street')
    parser.add_argument('houseno')
    parser.add_argument('-d', '--district', default=DEFAULT_DISTRICT)
    return parser.parse_args()


def main():
    """Runs the web scraper."""

    args = get_args()
    client = AhaDisposalClient(district=args.district)

    for pickup_solution in client.by_street_houseno(args.street, args.houseno):
        print(pickup_solution)
