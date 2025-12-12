"""API Schemas - Request and Response DTOs"""
from pydantic import BaseModel, Field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from typing import List, Optional

from domain.enums import ReservationSource, RequestType, Priority, ReservationStatus, WaitlistStatus


# ============================================================================
# RESERVATION SCHEMAS
# ============================================================================

class SpecialRequestRequest(BaseModel):
    """Special request request DTO"""
    type: RequestType
    description: str


class CreateReservationRequest(BaseModel):
    """Create reservation request DTO"""
    guest_id: UUID
    room_type_id: str
    check_in: date
    check_out: date
    adults: int = Field(ge=1, le=10)
    children: int = Field(ge=0, le=10, default=0)
    reservation_source: ReservationSource = Field(default=ReservationSource.WEBSITE, description="Source of reservation")
    special_requests: List[SpecialRequestRequest] = []
    created_by: str = "SYSTEM"


class ModifyReservationRequest(BaseModel):
    """Modify reservation request DTO"""
    check_in: Optional[date] = None
    check_out: Optional[date] = None
    adults: Optional[int] = Field(None, ge=1, le=10)
    children: Optional[int] = Field(None, ge=0, le=10)
    room_type_id: Optional[str] = None


class AddSpecialRequestRequest(BaseModel):
    """Add special request request DTO"""
    request_type: RequestType
    description: str


class ConfirmReservationRequest(BaseModel):
    """Confirm reservation request DTO"""
    payment_confirmed: bool = True


class CheckInRequest(BaseModel):
    """Check-in request DTO"""
    room_number: str


class CancelReservationRequest(BaseModel):
    """Cancel reservation request DTO"""
    reason: str = "Guest changed plans"


class SpecialRequestResponse(BaseModel):
    """Special request response DTO"""
    request_id: UUID
    request_type: str
    description: str
    fulfilled: bool = False
    notes: Optional[str] = None
    created_at: datetime


class ReservationResponse(BaseModel):
    """Reservation response DTO"""
    reservation_id: UUID
    confirmation_code: str
    guest_id: UUID
    room_type_id: str
    check_in: date
    check_out: date
    adults: int
    children: int
    total_amount: Decimal
    currency: str
    status: str
    reservation_source: str
    special_requests: List[SpecialRequestResponse]
    created_at: datetime
    modified_at: datetime
    created_by: str
    version: int


class MoneyResponse(BaseModel):
    """Money response DTO"""
    amount: Decimal
    currency: str


# ============================================================================
# AVAILABILITY SCHEMAS
# ============================================================================

class CreateAvailabilityRequest(BaseModel):
    """Create availability request DTO"""
    room_type_id: str
    availability_date: date
    total_rooms: int = Field(ge=1)
    overbooking_threshold: int = Field(ge=0, default=0)


class CheckAvailabilityRequest(BaseModel):
    """Check availability request DTO"""
    room_type_id: str
    start_date: date
    end_date: date
    required_count: int = Field(ge=1, default=1)


class ReserveRoomsRequest(BaseModel):
    """Reserve rooms request DTO"""
    room_type_id: str
    start_date: date
    end_date: date
    count: int = Field(ge=1)


class BlockRoomsRequest(BaseModel):
    """Block rooms request DTO"""
    room_type_id: str
    start_date: date
    end_date: date
    count: int = Field(ge=1)
    reason: str


class AvailabilityResponse(BaseModel):
    """Availability response DTO"""
    room_type_id: str
    availability_date: date
    total_rooms: int
    reserved_rooms: int
    blocked_rooms: int
    available_rooms: int
    overbooking_threshold: int
    last_updated: datetime
    version: int


# ============================================================================
# WAITLIST SCHEMAS
# ============================================================================

class CreateWaitlistRequest(BaseModel):
    """Create waitlist entry request DTO"""
    guest_id: UUID
    room_type_id: str
    check_in: date
    check_out: date
    adults: int = Field(ge=1, le=10)
    children: int = Field(ge=0, le=10, default=0)
    priority: str = "2"  # MEDIUM - as string for API, will convert to Priority enum in service


class ConvertWaitlistRequest(BaseModel):
    """Convert waitlist to reservation request DTO"""
    reservation_id: UUID


class ExtendWaitlistRequest(BaseModel):
    """Extend waitlist expiry request DTO"""
    additional_days: int = Field(ge=1)


class UpgradePriorityRequest(BaseModel):
    """Upgrade priority request DTO"""
    new_priority: str  # As string for API flexibility


class WaitlistResponse(BaseModel):
    """Waitlist response DTO"""
    waitlist_id: UUID
    guest_id: UUID
    room_type_id: str
    check_in: date
    check_out: date
    adults: int
    children: int
    priority: str
    status: str
    created_at: datetime
    expires_at: datetime
    notified_at: Optional[datetime] = None
    converted_reservation_id: Optional[UUID] = None
    priority_score: int


# ============================================================================
# AUTH SCHEMAS
# ============================================================================

class Token(BaseModel):
    """Token response DTO"""
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """Token payload DTO"""
    username: Optional[str] = None

class UserResponse(BaseModel):
    """User response DTO"""
    user_id: UUID
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: bool
