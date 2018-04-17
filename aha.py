"""AHA garbage collection dates web scraper."""

from collections import namedtuple
from contextlib import suppress
from datetime import datetime
from json import dumps
from re import IGNORECASE, compile as compile_re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Comment
from requests import get


__all__ = ['LocationNotFound', 'AhaDisposalClient']


BASE_URL = 'https://www.aha-region.de/'
DEFAULT_URL = urljoin(BASE_URL, 'abholtermine/abfuhrkalender')


STREET_MAP = {
    'strasse': 'str.',
    'straße': 'str',
    'Strasse': 'Str.',
    'Straße': 'Str.'}


class NotAPickup(Exception):
    """Indicates that the respective row is not a Pickup."""

    pass


class LocationNotFound(Exception):
    """Indicates that the respective location could not be found."""

    def __init__(self, street):
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


def street_regex(street):
    """Returns a regular expression to match the street name."""

    for key, value in STREET_MAP.items():
        if street.endswith(key):
            street = street.replace(key, value)
            break

    return compile_re(street.replace('.', '.*'), flags=IGNORECASE)


def normalize_houseno(house_number):
    """Tries to remove leading zeros from the house number."""

    return house_number.strip().lstrip('0')


def html_content(items):
    """Yields HTML like content."""

    for item in items:
        if isinstance(item, NavigableString) and not isinstance(item, Comment):
            yield item


def parse_pickups(table):
    """Parses pickups from the provided table."""

    tbody = table.find('tbody')

    if tbody is not None:
        rows = tbody.find_all('tr')

        for row in rows[1:-1]:    # Skip table header and footer.
            with suppress(NotAPickup):
                yield Pickup.from_html(row)


def get_loading_locations(html):
    """Yieds loading location from the respective select element."""

    select = html.find(id='ladeort')

    if select is not None:
        for option in select.find_all('option'):
            yield LoadingLocation.from_html(option)


class Pickup(namedtuple(
        'Pickup', 'typ weekday interval image_link next_dates')):
    """Garbage pickup."""

    @classmethod
    def from_html(cls, row):
        """Creates pickup information from an HTML <td> row."""
        try:
            image_link, typ, weekday, next_dates, interval = row.find_all('td')
        except ValueError:
            raise NotAPickup(row)

        image_link = image_link.find('img')['src']
        typ = typ.get_text().strip()
        weekday = weekday.get_text().strip()
        interval = interval.get_text().strip()
        next_dates = [
            PickupDate.from_string(next_date) for next_date
            in html_content(next_dates.contents)]
        return cls(typ, weekday, interval, image_link, next_dates)

    def to_dict(self):
        """Returns a JSON-ish dictionary."""
        return {
            'type': self.typ,
            'weekday': self.weekday,
            'interval': self.interval,
            'image_link': urljoin(BASE_URL, self.image_link),
            'next_dates': [date.to_dict() for date in self.next_dates]}


class PickupDate(namedtuple('PickupDate', ('date', 'weekday', 'exceptional'))):
    """A pickup date."""

    @classmethod
    def from_string(cls, string):
        """Creates a new pickup date from the provided string."""
        weekday, date = string.split(', ')
        exceptional = date.endswith('*')
        date = date.strip('*').strip()
        date = datetime.strptime(date, '%d.%m.%Y').date()
        return cls(date, weekday, exceptional)

    def to_dict(self):
        """Returns a JSON-ish dictionary."""
        return {
            'date': self.date.isoformat(),
            'weekday': self.weekday,
            'exceptional': self.exceptional}


class Location(namedtuple('Location', 'code street house_number district')):
    """Basic location."""

    @property
    def address(self):
        """Returns street and house number."""
        return '{} {}'.format(self.street, self.house_number or 'N/A')

    def to_dict(self):
        """Returns a JSON-ish dictionary."""
        return {
            'code': self.code,
            'street': self.street,
            'house_number': self.house_number,
            'district': self.district}


class LoadingLocation(Location):
    """A loading location."""

    def __init__(self, *_):
        """Sets the pickups."""
        super().__init__()
        self.pickups = ()

    def __str__(self):
        """Returns the AHA string representation."""
        return '@'.join((self.code.strip(), self.street, self.district))

    @classmethod
    def from_html(cls, option):
        """Creates a loading location from HTML."""
        code = option['value']   # Code must not be stripped and end with ' '.
        content = option.get_text().strip()
        address, district = content.split(',')
        street, house_number = address.rsplit(maxsplit=1)
        house_number = house_number.strip()
        district = district.strip().strip('/').strip()
        return cls(code, street, house_number, district)

    def to_dict(self):
        """Returns a JSON-ish dictionary."""
        dictionary = super().to_dict()
        dictionary['pickups'] = [pickup.to_dict() for pickup in self.pickups]
        return dictionary


class PickupLocation(Location):
    """A pickup location."""

    def __str__(self):
        """Returns the AHA string representation."""
        return '@'.join((self.code, self.street, self.district))

    @classmethod
    def from_string(cls, string, house_number=None):
        """Creates a pickup location from the provided string."""
        code, street, district = string.split('@')
        return cls(code, street, house_number, district)


class PickupInformation(namedtuple(
        'PickupInformation', 'pickups pickup_location loading_locations')):
    """A pickup location with dates."""

    def __iter__(self):
        """Yields pickups."""
        for pickup in self.pickups:
            yield pickup

    def __str__(self):
        """Returns the dumped dictionary."""
        return dumps(self.to_dict(), indent=2)

    @property
    def pickup(self):
        """Returns True on pickup or False on loading location."""
        if self.pickup_location:
            return True

        return False

    def to_dict(self):
        """Returns a JSON-ish dictionary."""
        dictionary = {}

        if self.pickups is not None:
            dictionary['pickups'] = [
                pickup.to_dict() for pickup in self.pickups]

        if self.pickup_location:
            dictionary['pickup_location'] = self.pickup_location.to_dict()

        if self.loading_locations:
            dictionary['loading_locations'] = [
                loading_location.to_dict() for loading_location
                in self.loading_locations]

        return dictionary


class AhaDisposalClient:
    """Client to web-scrape the AHA garbage disposal dates API."""

    def __init__(self, url=DEFAULT_URL, district='Hannover'):
        """Sets URL and district."""
        self.url = url
        self.district = district

    def pickup_locations(self, house_number=None):
        """Yields the respective pickup addresses."""
        params = {'von': 'A', 'bis': '[', 'gemeinde': self.district}
        reply = get(self.url, params=params)

        if reply.status_code == 200:
            html = BeautifulSoup(reply.text, 'html5lib')
            options = html.find(id='strasse').find_all('option')

            for option in options:
                yield PickupLocation.from_string(
                    str(option['value']), house_number=house_number)

    def by_pickup_location(self, pickup_location, house_number):
        """Returns the respective pickups."""
        params = {
            'strasse': str(pickup_location),
            'hausnr': house_number}
        reply = get(self.url, params=params)

        if reply.status_code == 200:
            html = BeautifulSoup(reply.text, 'html5lib')
            table = html.find('table')

            if table is None:
                raise LoadingLocations(tuple(get_loading_locations(html)))

            for pickup in parse_pickups(table):
                yield pickup

    def by_loading_location(self, loading_location, pickup_location):
        """Returns the respective pickups."""
        params = {
            'strasse': str(pickup_location),
            'hausnr': pickup_location.house_number,
            'ladeort': loading_location.code}
        reply = get(self.url, params=params)

        if reply.status_code == 200:
            html = BeautifulSoup(reply.text, 'html5lib')
            table = html.find('table')

            if table is not None:
                for pickup in parse_pickups(table):
                    yield pickup

    def get_pickup_locations(self, street, house_number=None):
        """Gets a location by the respective street name."""
        street = street_regex(street)

        for pickup_location in self.pickup_locations(
                house_number=house_number):
            if street.match(pickup_location.street):
                yield pickup_location

    def get_pickup_location(self, street, house_number=None):
        """Gets a location by the respective street name."""
        for pickup_location in self.get_pickup_locations(
                street, house_number=house_number):
            return pickup_location

        raise LocationNotFound(street)

    def by_address(self, street, house_number):
        """Returns pickups by the respective address."""
        house_number = normalize_houseno(house_number)
        pickup_location = self.get_pickup_location(
            street, house_number=house_number)

        try:
            pickups = tuple(self.by_pickup_location(
                pickup_location, house_number))
        except LoadingLocations as loading_locations:
            for loading_location in loading_locations:
                pickups = tuple(self.by_loading_location(
                    loading_location, pickup_location))
                loading_location.pickups = pickups

            return PickupInformation(None, None, loading_locations)

        return PickupInformation(pickups, pickup_location, None)
