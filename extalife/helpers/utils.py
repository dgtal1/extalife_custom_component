"""Various utilities"""
from datetime import datetime


# sensor conversion routines
class Conv():
    """Value conversion utils"""

    @staticmethod
    def bool_to_percent(value: bool) -> int:
        """ convert boolean value to percent: 0 or 100 use case: e.g. battery sensor attribute"""
        return 0 if value else 1

    @staticmethod
    def boolint_to_percent(value) -> int:
        """ normalize value (int or bool) to percent: 0 or 100 use case: e.g. battery sensor attribute"""
        return value if not isinstance(value, bool) else Conv.bool_to_percent(value)

    @staticmethod
    def timestamp_to_datetime(value: int) -> int:
        """ convert unix timestamp value to normalized ISO8601 representation required by HA"""
        return datetime.utcfromtimestamp(value).isoformat()

    @staticmethod
    def invert_percentage(value: int) -> int:
        """ convert percentage upside down e.g. valve open value"""
        return (100-value)
