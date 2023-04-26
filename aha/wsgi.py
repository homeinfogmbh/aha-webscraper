"""Non-authenticated WSGI interface.

XXX: For internal use only!
"""
from typing import Union

from wsgilib import Application, JSON, JSONMessage

from aha.api import find_location
from aha.exceptions import AmbiguousLocations
from aha.exceptions import HTTPError
from aha.exceptions import NoLocationFound
from aha.exceptions import ScrapingError
from aha.functions import get_address, get_cached_pickups


__all__ = ['APPLICATION']


APPLICATION = Application('lpt', cors=True)
CACHE = {}


@APPLICATION.route('/', methods=['POST'], strict_slashes=False)
def garbage_pickup() -> Union[JSON, JSONMessage]:
    """Returns information about the garbage collection."""

    address = get_address()

    try:
        location = find_location(address.street)
    except NoLocationFound:
        return JSONMessage('No matching locations found.')
    except AmbiguousLocations as locations:
        return JSONMessage(
            'Multiple matching locations found.',
            locations=[location.name for location in locations]
        )

    try:
        pickups = get_cached_pickups(location, address.house_number)
    except HTTPError as error:
        return JSONMessage('HTTP error.', status_code=error.status_code)
    except ScrapingError as error:
        return JSONMessage('Scraping error.', error=error.message)

    return JSON([pickup.to_json() for pickup in pickups])
