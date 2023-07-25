"""Common functions."""

from datetime import date
from typing import Union

from flask import request

from hwdb import Deployment
from mdb import Address
from wsgilib import JSON, JSONMessage

from aha.types import Location, Pickup
from aha.api import find_location, get_pickups
from aha.exceptions import AmbiguousLocations
from aha.exceptions import HTTPError
from aha.exceptions import NoLocationFound
from aha.exceptions import ScrapingError


__all__ = ["by_address", "get_address", "get_cached_pickups"]


CACHE = {}


def by_address(address: Address) -> Union[JSON, JSONMessage]:
    """Return a WSGI response by address."""

    try:
        location = find_location(address.street)
    except NoLocationFound:
        return JSONMessage("No matching locations found.")
    except AmbiguousLocations as locations:
        return JSONMessage(
            "Multiple matching locations found.",
            locations=[location.name for location in locations],
        )

    try:
        pickups = get_cached_pickups(location, address.house_number)
    except HTTPError as error:
        return JSONMessage("HTTP error.", status_code=error.status_code)
    except ScrapingError as error:
        return JSONMessage("Scraping error.", error=error.message)

    return JSON([pickup.to_json() for pickup in pickups])


def get_address() -> Address:
    """Return the requested address."""

    if address_id := request.json.get("address"):
        return Address.get(Address.id == address_id)

    if deployment_id := request.json.get("deployment"):
        deployment = (
            Deployment.select(cascade=True).where(Deployment.id == deployment_id).get()
        )
        return deployment.lpt_address or deployment.address

    return Address(
        street=request.json["street"],
        house_number=request.json["houseNumber"],
        zip_code=request.json["zipCode"],
        city=request.json["city"],
        district=request.json.get("district"),
    )


def get_cached_pickups(location: Location, house_number: str) -> list[Pickup]:
    """Returns cached pickups for the day."""

    try:
        locations = CACHE[date.today()]
    except KeyError:
        CACHE.clear()
        CACHE[date.today()] = locations = {}

    try:
        return locations[location]
    except KeyError:
        locations[location] = pickups = list(get_pickups(location, house_number))
        return pickups
