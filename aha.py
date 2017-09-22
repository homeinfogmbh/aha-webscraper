#! /usr/bin/env python3
"""aha.py

Web scrape AHA pickup locations.

Usage:
    aha.py <street> <house_number> [options]

Options:
    --help, -h          Print this.page.
"""
from json import dumps
from sys import stderr
from urllib.parse import urljoin

from bs4.element import NavigableString, Comment
from requests import get


__all__ = ['AhaDisposalClient']


BASE_URL = 'https://www.aha-region.de/'
DEFAULT_URL = urljoin(BASE_URL, 'abholtermine/abfuhrkalender')
RESULT_START = '<!-- ###ERGEBNIS### start-->'
RESULT_END = '<!-- ###ERGEBNIS### end-->'
ADDRESS_LIST_START = (
    '<SELECT class=\'tab_body\' id="strasse" name="strasse" size="1">')
ADDRESS_LIST_END = '</select>'
ADDRESS_VALUE_START = "value='"
ADDRESS_VALUE_END = "'>"
LADEORT_LIST_START = (
    '<select class="tab_body" id="ladeort" name="ladeort" size="1">')
LADEORT_LIST_END = '</select>'
DATES_LIST_START = (
    '<!-- ###SUCH_ERGEBNIS_FRAKTIONEN_NAECHSTE_TERMINE### start-->')
DATES_LIST_END = '<!-- ###SUCH_ERGEBNIS_FRAKTIONEN_NAECHSTE_TERMINE### end-->'


def html_content(tags):
    """Yields HTML like content"""

    for tag in tags:
        if not isinstance(tag, Comment) and isinstance(tag, NavigableString):
            yield tag


def pickup_locations(text):
    """Yields pickup locations."""

    try:
        _, start = text.split(LADEORT_LIST_START)
    except ValueError:
        pass
    else:
        lst, _ = start.split(LADEORT_LIST_END)

        for line in lst.split('\n'):
            line = line.strip()

            if line:
                _, key_start = line.split('<option  value="')
                key, name_start = key_start.split('">')
                name, _ = name_start.split('</option>')
                yield (key, name)


def extract_image_link(result_body):
    """Returns the image link."""
    try:
        _, start = result_body.split('<td valign="top" width=""><img src="')
    except ValueError:
        return None
    else:
        link, *_ = start.split('" ')
        return urljoin(BASE_URL, link)


def extract_type(result_body):
    """Returns the pickup type."""

    try:
        _, start = result_body.split('<td valign="top" class="mobile_max">')
    except ValueError:
        return None
    else:
        typ, *_ = start.split('</td>')
        return typ.strip()


def extract_weekdays(result_body):
    """Returns the pickup weekdays."""

    try:
        _, start = result_body.split('<td valign="top" class="mobile_no">')
    except ValueError:
        return None
    else:
        weekday, *_ = start.split('</td>')

        for weekday in weekday.split('<br>'):
            weekday = weekday.strip()

            if weekday:
                yield weekday


def extract_dates(result_body):
    """Returns the pickup dates."""
    try:
        _, start = result_body.split(DATES_LIST_START)
    except ValueError:
        pass
    else:
        dates, *_ = start.split(DATES_LIST_END)

        for date in dates.split('<br>'):
            date = date.strip()

            if date:
                yield date


def extract_results(result):
    """Extracts the search results section."""

    results = {}
    _, *result_starts = result.split('<tr>')

    for result_start in result_starts:
        result_body, _ = result_start.split('</tr>')

        # Skip table headers
        if '<th>' in result_body:
            continue

        type_ = extract_type(result_body)

        if type_ is not None:
            results[type_] = {
                'weekdays': list(extract_weekdays(result_body)),
                'dates': list(extract_dates(result_body)),
                'image': extract_image_link(result_body)}

    return results


class PickupLocation:
    """A pickup location."""

    def __init__(self, string):
        self.code, self.street, self.district = string.split('@')
        self.dates = None

    def __str__(self):
        return '@'.join((self.code, self.street, self.district))

    def render(self, house_number, pickups):
        """Renders pickup location as a dictionary."""
        return {
            'code': self.code,
            'street': self.street,
            'district': self.district,
            'house_number': house_number,
            'pickups': pickups}


class PickupDate:
    """A pickup date."""

    def __init__(self, table_row):
        """Parses pickup date from a table row element"""
        self.typ = None
        self.weekdays = []
        self.dates = []

        for table_column in table_row.find_all('td'):
            classes = table_column.attrs.get('class', [])

            if 'mobile_max' in classes:
                self.typ = table_column.text.strip()
                continue
            elif 'mobile_no' in classes:
                self.weekdays = list(html_content(table_column.contents))
                continue
            elif table_column.attrs.get('valign') == 'top':
                if table_column.attrs.get('width') == '115px':
                    self.dates = list(html_content(table_column.contents))
                    continue

    def to_dict(self):
        """Returns the pickup date as a dictionary."""
        return {
            'weekdays': self.weekdays,
            'dates': self.dates,
            'type': self.typ}


class AhaDisposalClient:
    """Client to web-scrape the AHA garbage disposal dates API."""

    def __init__(self, url=DEFAULT_URL):
        self.url = url

    def addresses(self, start='A', end='[', district='Hannover'):
        """Yields the respective pickup addresses."""
        params = {'von': start, 'bis': end, 'gemeinde': district}
        reply = get(self.url, params=params)

        if reply.status_code == 200:
            _, begin = reply.text.split(ADDRESS_LIST_START)
            lst, _ = begin.split(ADDRESS_LIST_END)

            for line in lst.strip().split('\n'):
                line = line.strip()

                if line:
                    _, start = line.split(ADDRESS_VALUE_START)
                    address, _ = start.split(ADDRESS_VALUE_END)
                    yield PickupLocation(address)

    def pickups(self, address, house_number, pickup_location=None):
        """Returns the respective pickups."""
        params = {'strasse': address, 'hausnr': house_number}

        if pickup_location is not None:
            params['ladeort'] = pickup_location[0]

        reply = get(self.url, params=params)

        if reply.status_code == 200:
            try:
                _, start = reply.text.split(RESULT_START)
            except ValueError:
                result = {}

                for pickup_location in pickup_locations(reply.text):
                    result.update(self.pickups(
                        address, house_number,
                        pickup_location=pickup_location))
            else:
                result, _ = start.split(RESULT_END)
                result = extract_results(result)

            return result


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

    for location in client.addresses():
        if street in location.street:
            pickups = client.pickups(str(location), house_number)
            dictionary = location.render(house_number, pickups)

            if pickups:
                print(dumps({str(location): dictionary}, indent=2))
            else:
                print(dumps({str(location): dictionary}, indent=2),
                      file=stderr)


if __name__ == '__main__':
    from docopt import docopt
    main(docopt(__doc__))
