#! /usr/bin/env python3
"""aha.py

Web scrape AHA pickup locations.

Usage:
    aha.py <street> <house_number> [options]

Options:
    --help, -h          Print this.page.
"""
from datetime import datetime
from json import dumps
from sys import stderr
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


def normalize_street(street):
    """Returns a normalized version of the street name."""

    for key, value in STREET_MAP.items():
        if street.endswith(key):
            return street.replace(key, value)

    return street


def html_content(items):
    """Yields HTML like content."""

    for item in items:
        if isinstance(item, NavigableString):
            if not isinstance(item, Comment):
                yield item


def parse_pickups(table):
    """Parses pickups from the provided table."""

    tbody = table.find('tbody')
    rows = tbody.find_all('tr')

    for row in rows[1:-1]:    # Skip table header and footer
        yield PickupInformation.from_html(row)


def get_loading_locations(html):
    """Yieds loading location from the respective select element."""

    select = html.find(id='ladeort')

    for option in select.find_all('option'):
        yield LoadingLocation.from_html(option)


class LocationWrapper:
    """A location wrapper."""

    def __init__(self, location, house_number):
        """Sets location implementation and house number."""
        self.location = location
        self.house_number = house_number

    def to_dict(self):
        """Returns a JSON-ish dictionary."""
        dictionary = self.location.to_dict()
        dictionary['house_number'] = self.house_number
        return dictionary


class PickupInformation:
    """Pickup information."""

    def __init__(self, typ, weekday, interval, image_link, next_dates):
        """Sets pickup information data."""
        self.typ = typ
        self.weekday = weekday
        self.interval = interval
        self.image_link = image_link
        self.next_dates = next_dates

    @classmethod
    def from_html(cls, row):
        """Creates pickup information from an HTML <td> row."""
        image_link, typ, weekday, next_dates_, interval = row.find_all('td')
        image_link = image_link.find('img')['src']
        typ = typ.get_text().strip()
        weekday = weekday.get_text().strip()
        next_dates = []

        for next_date in html_content(next_dates_.contents):
            next_dates.append(PickupDate.from_string(next_date))

        interval = interval.get_text().strip()
        return cls(typ, weekday, interval, image_link, next_dates)

    def to_dict(self):
        """Returns a JSON-ish dictionary."""
        return {
            'type': self.typ,
            'weekday': self.weekday,
            'interval': self.interval,
            'image_link': urljoin(BASE_URL, self.image_link),
            'next_dates': [date.to_dict() for date in self.next_dates]}


class PickupDate:
    """A pickup date."""

    def __init__(self, date, weekday=None, exceptional=False):
        self.date = date
        self.weekday = weekday
        self.exceptional = exceptional

    @classmethod
    def from_string(cls, string):
        """Creates a new pickup date from the provided string."""
        weekday, date = string.split(', ')
        exceptional = date.endswith('*')
        date = date.strip('*').strip()
        date = datetime.strptime(date, '%d.%m.%Y').date()
        return cls(date, weekday=weekday, exceptional=exceptional)

    def to_dict(self):
        """Returns a JSON-ish dictionary."""
        return {
            'date': self.date.isoformat(),
            'weekday': self.weekday,
            'exceptional': self.exceptional}


class LoadingLocation:
    """A loading location."""

    def __init__(self, key, street, house_number):
        """Sets key and name."""
        self.key = key
        self.street = street
        self.house_number = house_number

    @classmethod
    def from_html(cls, option):
        """Creates a loading location from HTML."""
        key = option['value']
        name = option.get_text().strip().strip(',')
        *street, house_number = name.split()
        street = ' '.join(street)
        return cls(key, street, house_number)


class PickupLocation:
    """A pickup location."""

    def __init__(self, code, street, district):
        """Sets code, street and district."""
        self.code = code
        self.street = street
        self.district = district

    def __str__(self):
        return '@'.join((self.code, self.street, self.district))

    @classmethod
    def from_string(cls, string):
        """Creates a pickup location from the provided string."""
        return cls(*string.split('@'))

    def to_dict(self):
        """Returns a JSON-ish dictionary."""
        return {
            'code': self.code,
            'street': self.street,
            'district': self.district}


class Pickup:
    """A pickup location with dates."""

    def __init__(self, pickups, pickup_location=None, loading_location=None):
        """Sets street, house number and pickups."""
        self.pickups = pickups
        self.pickup_location = pickup_location
        self.loading_location = loading_location

    def to_dict(self):
        """Returns a JSON-ish dictionary."""
        dictionary = {'pickups': [pickup.to_dict() for pickup in self.pickups]}

        if self.pickup_location:
            dictionary['pickup_location'] = self.pickup_location.to_dict()

        if self.loading_location:
            dictionary['loading_location'] = self.loading_location.to_dict()

        return dictionary


class AhaDisposalClient:
    """Client to web-scrape the AHA garbage disposal dates API."""

    def __init__(self, url=DEFAULT_URL, district='Hannover'):
        self.url = url
        self.district = district

    @property
    def pickup_locations(self):
        """Yields the respective pickup addresses."""
        params = {'von': 'A', 'bis': '[', 'gemeinde': self.district}
        reply = get(self.url, params=params)

        if reply.status_code == 200:
            html = BeautifulSoup(reply.text, 'html.parser')
            options = html.find(id='strasse').find_all('option')

            for option in options:
                yield PickupLocation.from_string(str(option['value']))

    def by_pickup_location(self, pickup_location, house_number):
        """Returns the respective pickups."""
        params = {
            'strasse': str(pickup_location),
            'hausnr': house_number}
        reply = get(self.url, params=params)

        if reply.status_code == 200:
            html = BeautifulSoup(reply.text, 'html.parser')
            table = html.find('table')

            if table is None:
                raise LoadingLocations(tuple(get_loading_locations(html)))
            else:
                for pickup in parse_pickups(table):
                    yield pickup

    def by_loading_location(self, loading_location, street_code):
        """Returns the respective pickups."""
        params = {
            'strasse': street_code,
            'hausnr': loading_location.house_number,
            'ladeort': loading_location.key}
        reply = get(self.url, params=params)

        if reply.status_code == 200:
            html = BeautifulSoup(reply.text, 'html.parser')
            table = html.find('table')

            for pickup in parse_pickups(table):
                yield pickup

    def get_pickup_locations(self, street):
        """Gets a location by the respective street name."""
        for pickup_location in self.pickup_locations:
            if street in pickup_location.street:
                yield pickup_location

    def get_pickup_location(self, street):
        """Gets a location by the respective street name."""
        for pickup_location in self.get_pickup_locations(street):
            return pickup_location

        raise LocationNotFound(street)

    def by_address(self, street, house_number):
        """Returns pickups by the respective address."""
        street = normalize_street(street)
        pickup_location = self.get_pickup_location(street)

        try:
            pickups = tuple(self.by_pickup_location(
                pickup_location, house_number))
        except LoadingLocations as loading_locations:
            for loading_location in loading_locations:
                location_wrapper = LocationWrapper(
                    pickup_location, loading_location.house_number)
                pickups = tuple(self.by_loading_location(
                    loading_location, str(pickup_location)))
                yield Pickup(pickups, loading_location=location_wrapper)
        else:
            location_wrapper = LocationWrapper(pickup_location, house_number)
            yield Pickup(pickups, pickup_location=location_wrapper)


def main(options):
    """Runs the web scraper."""

    street = options['<street>']
    house_number = options['<house_number>']

    try:
        house_number = int(house_number)
    except ValueError:
        print('Invalid house number: {}.'.format(house_number), file=stderr)
        exit(2)

    client = AhaDisposalClient()
    pickups = [pickup.to_dict() for pickup in client.by_address(
        street, house_number)]
    print(dumps(pickups, indent=2))


if __name__ == '__main__':
    from docopt import docopt
    main(docopt(__doc__))
