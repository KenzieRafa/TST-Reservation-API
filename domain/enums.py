"""Domain Enums"""
from enum import Enum


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class ReservationSource(str, Enum):
    WEBSITE = "WEBSITE"
    MOBILE_APP = "MOBILE_APP"
    PHONE = "PHONE"
    OTA = "OTA"
    DIRECT = "DIRECT"
    CORPORATE = "CORPORATE"


class RequestType(str, Enum):
    EARLY_CHECK_IN = "EARLY_CHECK_IN"
    LATE_CHECK_OUT = "LATE_CHECK_OUT"
    HIGH_FLOOR = "HIGH_FLOOR"
    ACCESSIBLE_ROOM = "ACCESSIBLE_ROOM"
    QUIET_ROOM = "QUIET_ROOM"
    CRIBS = "CRIBS"
    EXTRA_BED = "EXTRA_BED"
    SPECIAL_AMENITIES = "SPECIAL_AMENITIES"


class WaitlistStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CONVERTED = "CONVERTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class Priority(int, Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4
