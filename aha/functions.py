"""Miscellaneous functions."""

from typing import Any, Iterable, Iterator


__all__ = ['frames']


def frames(iterable: Iterable[Any], size: int) -> Iterator[tuple[Any, ...]]:
    """Yields tuples of the given size from the iterable."""

    if size < 1:
        raise ValueError('Size must be >= 1')

    frame = []

    for item in iterable:
        frame.append(item)

        if len(frame) == size:
            yield tuple(frame)
            frame.clear()

    if frame:
        raise ValueError('Last frame not filled:', frame)
