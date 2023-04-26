"""Common functions."""

from datetime import date

from flask import request

from hwdb import Deployment
from mdb import Address

from aha.api import get_pickups
from aha.types import Location, Pickup


__all__ = ['get_address', 'get_cached_pickups']


CACHE = {}


def get_address() -> Address:
    """Return the requested address."""

    if address_id := request.json.get('address'):
        return Address.get(Address.id == address_id)

    if deployment_id := request.json.get('deployment'):
        deployment = Deployment.select(cascade=True).where(
            Deployment.id == deployment_id
        ).get()
        return deployment.lpt_address or deployment.address

    return Address(
        street=request.json['street'],
        house_number=request.json['houseNumber'],
        zip_code=request.json['zipCode'],
        city=request.json['city'],
        district=request.json.get('district')
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
        locations[location] = pickups = list(
            get_pickups(location, house_number)
        )
        return pickups
