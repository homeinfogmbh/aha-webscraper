"""Command line program."""

from argparse import ArgumentParser, Namespace
from json import dumps
from logging import DEBUG, WARNING, basicConfig, getLogger

from aha.api import find_location, get_pickups
from aha.exceptions import AmbiguousLocations
from aha.exceptions import HTTPError
from aha.exceptions import NoLocationFound
from aha.exceptions import ScrapingError


__all__ = ['main']


LOG_FORMAT = '[%(levelname)s] %(name)s: %(message)s'
LOGGER = getLogger('aha-webscraper')


def get_args() -> Namespace:
    """Returns the parsed command line arguments."""

    parser = ArgumentParser(description='Retrieve garbage disposal dates.')
    parser.add_argument('street', help='the street name')
    parser.add_argument('houseno', help='the house number')
    parser.add_argument('-d', '--district', help='the district name')
    parser.add_argument(
        '-i', '--indent', type=int, help='indentation for JSON'
    )
    parser.add_argument(
        '-m', '--municipality', default='Hannover', help='the district name'
    )
    parser.add_argument(
        '-v', '--verbose', action='store_true', help='be gassy'
    )
    return parser.parse_args()


def main() -> int:
    """Runs the program."""

    args = get_args()
    basicConfig(format=LOG_FORMAT, level=DEBUG if args.verbose else WARNING)

    try:
        location = find_location(args.street, district=args.district)
    except NoLocationFound:
        LOGGER.error('No matching locations found.')
        return 1
    except AmbiguousLocations as locations:
        LOGGER.warning('Multiple matching locations found:')

        for location in locations:
            LOGGER.warning(location.name)

        return 2

    try:
        pickups = get_pickups(location, args.houseno)
    except HTTPError as error:
        LOGGER.error('HTTP error: %s (%i)', error.text, error.status_code)
        return 3
    except ScrapingError as error:
        LOGGER.error('Scraping error: %s', error.message)
        LOGGER.debug('HTML text:\n%s', error.html)
        return 4

    print(dumps([p.to_json() for p in pickups], indent=args.indent))
    return 0
