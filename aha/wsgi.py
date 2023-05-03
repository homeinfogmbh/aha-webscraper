"""Non-authenticated WSGI interface.

XXX: For internal use only!
"""
from typing import Union

from wsgilib import Application, JSON, JSONMessage

from aha.functions import by_address, get_address


__all__ = ['APPLICATION']


APPLICATION = Application('aha', cors=True)


@APPLICATION.route('/', methods=['POST'], strict_slashes=False)
def garbage_pickup() -> Union[JSON, JSONMessage]:
    """Returns information about the garbage collection."""

    return by_address(get_address())
