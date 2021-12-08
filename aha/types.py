"""Common data types."""

from __future__ import annotations
from datetime import date
from enum import Enum
from string import ascii_letters
from typing import NamedTuple, Optional

from bs4.element import Tag

from aha.parsers import parse_date, text_content


__all__ = ['HouseNumber', 'Interval', 'Location', 'Pickup', 'Request']


class HouseNumber(NamedTuple):
    """Represents a house number."""

    number: int
    suffix: str = ''

    @classmethod
    def from_string(cls, string: str) -> HouseNumber:
        """Splits the house number."""
        number: list[str] = []
        suffix: list[str] = []
        index = 0

        for index, char in enumerate(string):
            if not char.isdigit():
                break

            number.append(char)

        for char in string[index:]:
            if char in ascii_letters:
                suffix.append(char)

        return cls(int(''.join(number)), ''.join(suffix))


class Interval(Enum):
    """Pickup interval."""

    FORTNIGHTLY = '14- täglich'
    WEEKLY = '1x wöchentlich'


class Location(NamedTuple):
    """Location parameters."""

    id: str
    name: str
    district: str

    def __str__(self):
        return '@'.join(self)

    @classmethod
    def from_string(cls, string: str) -> Location:
        """Parses the location parameters from a string."""
        return cls(*string.split('@'))


class Pickup(NamedTuple):
    """Pickup calendar events."""

    type: str
    image: str
    weekday: str
    dates: list[date]
    interval: Interval

    @classmethod
    def from_elements(cls, caption: Tag, schedule: Tag) -> Pickup:
        """Creates a pickup from an element pair."""
        type_ = caption.find('strong').text
        image = caption.find('img')['src']
        weekday, dates, interval = schedule.find_all('td')
        weekday = weekday.text
        dates = [parse_date(date) for date in text_content(dates)]
        interval = Interval(interval.text)
        return cls(type_, image, weekday, dates, interval)

    def to_json(self) -> dict:
        """Returns a JSON-ish dict."""
        return {
            'type': self.type,
            'image': self.image,
            'weekday': self.weekday,
            'dates': [d.isoformat() for d in self.dates],
            'interval': self.interval.name
        }


class Request(NamedTuple):
    """Pickups request."""

    location: Location
    house_number: HouseNumber
    municipality: str
    pickup_location: Optional[str] = None

    def change_location(self, pickup_location: str) -> Request:
        """Returns a request with changed pickup location."""
        return type(self)(self.location, self.house_number, self.municipality,
                          pickup_location)

    def to_json(self) -> dict:
        """Returns a JSON-ish dict."""
        return {
            'gemeinde': self.municipality,
            'strasse': str(self.location),
            'hausnr': str(self.house_number.number),
            'hausnraddon': self.house_number.suffix,
            'ladeort': self.pickup_location,
            'anzeigen': 'Suchen'
        }
