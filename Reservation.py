# domain/value_objects.py
from pydantic import BaseModel, Field, validator
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4
from typing import Optional, List

class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"

class BookingSource(str, Enum):
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

class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"

class DateRange(BaseModel):
    check_in: date
    check_out: date

    @validator('check_out')
    def check_out_after_check_in(cls, v, values):
        if 'check_in' in values and v <= values['check_in']:
            raise ValueError('Check-out must be after check-in')
        return v

    def nights(self) -> int:
        """Calculate number of nights"""
        return (self.check_out - self.check_in).days

    class Config:
        frozen = True

class Money(BaseModel):
    amount: Decimal = Field(gt=0)  # Must be strictly greater than 0
    currency: str = "IDR"

    class Config:
        frozen = True

class GuestCount(BaseModel):
    adults: int = Field(ge=1, le=10)
    children: int = Field(ge=0, le=10)
    
    class Config:
        frozen = True

class SpecialRequest(BaseModel):
    request_id: UUID = Field(default_factory=uuid4)
    request_type: RequestType
    description: str
    fulfilled: bool = False
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def fulfill(self, notes: str) -> None:
        """Mark request as fulfilled"""
        self.fulfilled = True
        self.notes = notes

    def is_fulfilled(self) -> bool:
        """Check if request is fulfilled"""
        return self.fulfilled

    class Config:
        from_attributes = True

class CancellationPolicy(BaseModel):
    policy_name: str
    refund_percentage: Decimal = Field(ge=0, le=100)
    deadline_hours: int = Field(ge=0)
    
    class Config:
        frozen = True


# domain/entities.py
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime, date, timedelta
from typing import Optional, List
from decimal import Decimal

class Reservation(BaseModel):
    # Identity
    reservation_id: UUID = Field(default_factory=uuid4)
    confirmation_code: str

    # References to other contexts
    guest_id: UUID
    room_type_id: str  # Standardized to str for consistency with Availability and WaitlistEntry

    # Value Objects
    date_range: DateRange
    guest_count: GuestCount
    total_amount: Money
    cancellation_policy: CancellationPolicy

    # Enums/Status
    status: ReservationStatus = ReservationStatus.PENDING
    booking_source: BookingSource = BookingSource.WEBSITE

    # Collections (child entities)
    special_requests: List[SpecialRequest] = []

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    modified_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = "SYSTEM"
    version: int = 1

    class Config:
        from_attributes = True

    # ==================== FACTORY METHOD ====================
    @staticmethod
    def create(
        guest_id: UUID,
        room_type_id: str,
        date_range: DateRange,
        guest_count: GuestCount,
        total_amount: Money,
        cancellation_policy: CancellationPolicy,
        booking_source: BookingSource,
        created_by: str = "SYSTEM"
    ) -> "Reservation":
        """Create new reservation with validation"""
        # Validate business rules
        Reservation._validate_date_range(date_range)
        Reservation._validate_guest_count(guest_count)
        Reservation._validate_amount(total_amount)

        # Generate confirmation code
        confirmation_code = Reservation._generate_confirmation_code()

        # Create and return reservation
        return Reservation(
            confirmation_code=confirmation_code,
            guest_id=guest_id,
            room_type_id=room_type_id,
            date_range=date_range,
            guest_count=guest_count,
            total_amount=total_amount,
            cancellation_policy=cancellation_policy,
            booking_source=booking_source,
            status=ReservationStatus.PENDING,
            created_by=created_by
        )

    # ==================== MODIFICATION METHODS ====================
    def modify(
        self,
        new_date_range: Optional[DateRange] = None,
        new_guest_count: Optional[GuestCount] = None,
        new_room_type_id: Optional[str] = None
    ) -> None:
        """Modify reservation details"""
        # Check if modifiable
        if not self.is_modifiable():
            raise ValueError(
                f"Cannot modify reservation in {self.status.value} status or within 24 hours of check-in"
            )

        # Validate new values
        if new_date_range:
            Reservation._validate_date_range(new_date_range)
            self.date_range = new_date_range

        if new_guest_count:
            Reservation._validate_guest_count(new_guest_count)
            self.guest_count = new_guest_count

        if new_room_type_id:
            self.room_type_id = new_room_type_id

        # Recalculate amount (simplified)
        self._recalculate_amount()

        # Update metadata
        self.modified_at = datetime.utcnow()
        self.version += 1

    def add_special_request(
        self,
        request_type: RequestType,
        description: str
    ) -> SpecialRequest:
        """Add special request from guest"""
        # Validate request type
        if not isinstance(request_type, RequestType):
            raise ValueError("Invalid request type")

        # Create special request
        special_request = SpecialRequest(
            request_type=request_type,
            description=description
        )

        # Add to collection
        self.special_requests.append(special_request)

        # Update metadata
        self.modified_at = datetime.utcnow()
        self.version += 1

        return special_request

    # ==================== STATE TRANSITION METHODS ====================
    def confirm(self, payment_confirmed: bool) -> None:
        """Confirm reservation after payment"""
        # Validate can transition to CONFIRMED
        if self.status != ReservationStatus.PENDING:
            raise ValueError(
                f"Cannot confirm reservation with status {self.status.value}"
            )

        if not payment_confirmed:
            raise ValueError("Payment must be confirmed to proceed")

        # Change status
        self.status = ReservationStatus.CONFIRMED
        self.modified_at = datetime.utcnow()
        self.version += 1

    def check_in(self, room_number: str) -> None:
        """Mark guest as checked in"""
        # Validate can check in
        if self.status not in [ReservationStatus.PENDING, ReservationStatus.CONFIRMED]:
            raise ValueError(
                f"Cannot check in with status {self.status.value}"
            )

        # Check if check-in date is today or later
        if self.date_range.check_in > date.today():
            raise ValueError("Cannot check in before check-in date")

        # Change status to CHECKED_IN
        self.status = ReservationStatus.CHECKED_IN
        self.modified_at = datetime.utcnow()
        self.version += 1

    def check_out(self) -> Money:
        """Process guest check-out"""
        # Validate can check out
        if self.status != ReservationStatus.CHECKED_IN:
            raise ValueError(
                f"Cannot check out with status {self.status.value}"
            )

        # Calculate final bill (simplified)
        final_bill = self.total_amount

        # Change status to CHECKED_OUT
        self.status = ReservationStatus.CHECKED_OUT
        self.modified_at = datetime.utcnow()
        self.version += 1

        return final_bill

    def cancel(self, reason: str) -> Money:
        """Cancel reservation"""
        # Validate can cancel
        if not self.is_cancellable():
            raise ValueError(
                f"Cannot cancel reservation with status {self.status.value}"
            )

        # Calculate refund using policy
        refund_amount = self.calculate_refund(date.today())

        # Change status to CANCELLED
        self.status = ReservationStatus.CANCELLED
        self.modified_at = datetime.utcnow()
        self.version += 1

        return refund_amount

    def mark_no_show(self) -> None:
        """Mark guest as no-show"""
        # Validate
        if self.status not in [ReservationStatus.PENDING, ReservationStatus.CONFIRMED]:
            raise ValueError(
                f"Cannot mark as no-show with status {self.status.value}"
            )

        # Change status to NO_SHOW
        self.status = ReservationStatus.NO_SHOW
        self.modified_at = datetime.utcnow()
        self.version += 1

    # ==================== QUERY METHODS ====================
    def is_modifiable(self) -> bool:
        """Check if reservation can be modified"""
        # Can only modify if status is PENDING or CONFIRMED
        if self.status not in [ReservationStatus.PENDING, ReservationStatus.CONFIRMED]:
            return False

        # Cannot modify if check-in is within 24 hours
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        checkin_datetime = datetime.combine(self.date_range.check_in, datetime.min.time())
        # Make checkin_datetime timezone-aware (UTC)
        checkin_datetime = checkin_datetime.replace(tzinfo=timezone.utc)
        hours_until_checkin = (checkin_datetime - now).total_seconds() / 3600

        if hours_until_checkin < 24:
            return False

        return True

    def is_cancellable(self) -> bool:
        """Check if reservation can be cancelled"""
        return self.status in [
            ReservationStatus.PENDING,
            ReservationStatus.CONFIRMED
        ]

    def calculate_refund(self, cancellation_date: date) -> Money:
        """Calculate refund amount based on policy"""
        # Calculate hours from cancellation to check-in
        from datetime import datetime
        cancellation_datetime = datetime.combine(cancellation_date, datetime.min.time())
        checkin_datetime = datetime.combine(self.date_range.check_in, datetime.min.time())
        hours_until_checkin = (checkin_datetime - cancellation_datetime).total_seconds() / 3600

        # If cancelled before deadline, full refund
        if hours_until_checkin >= self.cancellation_policy.deadline_hours:
            refund_amount = self.total_amount.amount
        else:
            # After deadline, apply cancellation policy refund percentage
            refund_amount = self.total_amount.amount * (self.cancellation_policy.refund_percentage / 100)

        return Money(
            amount=refund_amount,
            currency=self.total_amount.currency
        )

    def get_nights(self) -> int:
        """Get number of nights"""
        return self.date_range.nights()

    # ==================== PRIVATE VALIDATION METHODS ====================
    @staticmethod
    def _validate_date_range(date_range: DateRange) -> None:
        """Validate date range business rules"""
        # Check-in date >= today
        if date_range.check_in < date.today():
            raise ValueError("Check-in date must be today or later")

        # Nights >= 1 and <= 30
        nights = (date_range.check_out - date_range.check_in).days
        if nights < 1:
            raise ValueError("Minimum stay is 1 night")
        if nights > 30:
            raise ValueError("Maximum stay is 30 nights")

    @staticmethod
    def _validate_guest_count(guest_count: GuestCount) -> None:
        """Validate guest count business rules"""
        # Adults >= 1
        if guest_count.adults < 1:
            raise ValueError("At least 1 adult is required")

        # Total guests validation
        total_guests = guest_count.adults + guest_count.children
        if total_guests <= 0:
            raise ValueError("At least 1 guest is required")

    @staticmethod
    def _validate_amount(amount: Money) -> None:
        """Validate amount business rules"""
        # Amount > 0
        if amount.amount <= 0:
            raise ValueError("Amount must be greater than 0")

    @staticmethod
    def _generate_confirmation_code() -> str:
        """Generate unique confirmation code"""
        import random
        import string
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    def _recalculate_amount(self) -> None:
        """Recalculate total amount based on nights and rate"""
        # Simplified calculation - in real scenario this would involve database lookups
        nights = self.get_nights()
        # Assuming a base rate per night
        base_rate = 1000000  # IDR
        new_amount = Decimal(nights * base_rate)

        self.total_amount = Money(
            amount=new_amount,
            currency=self.total_amount.currency
        )


# ====================== AVAILABILITY AGGREGATE ======================
class Availability(BaseModel):
    # Composite Identity
    room_type_id: str
    date: date

    # Capacity Tracking
    total_rooms: int = Field(ge=0)
    reserved_rooms: int = Field(ge=0)
    blocked_rooms: int = Field(ge=0)

    # Configuration
    overbooking_threshold: int = Field(ge=0, default=0)

    # Metadata
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1

    class Config:
        from_attributes = True

    # ==================== COMPUTED PROPERTIES ====================
    @property
    def available_rooms(self) -> int:
        """Calculate available rooms"""
        return self.total_rooms - self.reserved_rooms - self.blocked_rooms

    @property
    def is_fully_booked(self) -> bool:
        """Check if no rooms available"""
        return self.available_rooms <= 0

    @property
    def can_overbook(self) -> bool:
        """Check if can accept overbooking"""
        current_overbooking = max(0, -self.available_rooms)
        return current_overbooking < self.overbooking_threshold

    # ==================== KEY METHODS ====================
    def check_availability(self, count: int) -> bool:
        """Check if can accommodate count rooms"""
        return self.available_rooms >= count or (
            self.available_rooms + self.overbooking_threshold >= count
        )

    def reserve_rooms(self, count: int) -> None:
        """Reserve rooms (decrease availability)"""
        # Validate capacity
        if not self.check_availability(count):
            raise ValueError("Insufficient availability to reserve requested rooms")

        self.reserved_rooms += count
        self.last_updated = datetime.utcnow()
        self.version += 1

    def release_rooms(self, count: int) -> None:
        """Release rooms (increase availability)"""
        # Validate count
        if count > self.reserved_rooms:
            raise ValueError("Cannot release more rooms than reserved")

        self.reserved_rooms -= count
        self.last_updated = datetime.utcnow()
        self.version += 1

    def block_rooms(self, count: int, reason: str) -> None:
        """Block rooms for maintenance/events"""
        # Validate capacity
        if self.blocked_rooms + count > self.total_rooms:
            raise ValueError("Cannot block more rooms than available")

        self.blocked_rooms += count
        self.last_updated = datetime.utcnow()
        self.version += 1

    def unblock_rooms(self, count: int) -> None:
        """Unblock rooms after maintenance"""
        if count > self.blocked_rooms:
            raise ValueError("Cannot unblock more than blocked")

        self.blocked_rooms -= count
        self.last_updated = datetime.utcnow()
        self.version += 1


# ====================== WAITLIST AGGREGATE ======================
class WaitlistEntry(BaseModel):
    # Identity
    waitlist_id: UUID = Field(default_factory=uuid4)

    # Request Details
    guest_id: UUID
    room_type_id: str
    requested_dates: DateRange
    guest_count: GuestCount

    # Status & Priority
    priority: Priority = Priority.MEDIUM
    status: WaitlistStatus = WaitlistStatus.ACTIVE

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    notified_at: Optional[datetime] = None

    # Conversion
    converted_reservation_id: Optional[UUID] = None

    class Config:
        from_attributes = True

    # ==================== FACTORY METHOD ====================
    @staticmethod
    def add_to_waitlist(
        guest_id: UUID,
        room_type_id: str,
        requested_dates: DateRange,
        guest_count: GuestCount,
        priority: Priority = Priority.MEDIUM
    ) -> "WaitlistEntry":
        """Add new entry to waitlist"""
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(days=14)

        return WaitlistEntry(
            guest_id=guest_id,
            room_type_id=room_type_id,
            requested_dates=requested_dates,
            guest_count=guest_count,
            priority=priority,
            status=WaitlistStatus.ACTIVE,
            created_at=created_at,
            expires_at=expires_at
        )

    # ==================== STATE TRANSITION METHODS ====================
    def convert_to_reservation(self, reservation_id: UUID) -> None:
        """Convert waitlist entry to actual reservation"""
        # Validate status is ACTIVE
        if self.status != WaitlistStatus.ACTIVE:
            raise ValueError(
                f"Cannot convert waitlist entry with status {self.status.value}"
            )

        # Change status to CONVERTED
        self.status = WaitlistStatus.CONVERTED
        self.converted_reservation_id = reservation_id

    def expire(self) -> None:
        """Mark entry as expired"""
        if self.status == WaitlistStatus.ACTIVE:
            self.status = WaitlistStatus.EXPIRED

    def cancel(self) -> None:
        """Cancel waitlist entry"""
        if self.status == WaitlistStatus.ACTIVE:
            self.status = WaitlistStatus.CANCELLED

    # ==================== MODIFICATION METHODS ====================
    def extend_expiry(self, additional_days: int) -> None:
        """Extend expiry date"""
        if self.status == WaitlistStatus.ACTIVE:
            self.expires_at += timedelta(days=additional_days)

    def upgrade_priority(self, new_priority: Priority) -> None:
        """Upgrade to higher priority"""
        priority_order = {
            Priority.LOW: 1,
            Priority.MEDIUM: 2,
            Priority.HIGH: 3,
            Priority.URGENT: 4
        }

        if priority_order.get(new_priority, 0) > priority_order.get(self.priority, 0):
            self.priority = new_priority

    def mark_notified(self) -> None:
        """Record notification sent"""
        self.notified_at = datetime.utcnow()

    # ==================== QUERY METHODS ====================
    def should_notify_again(self) -> bool:
        """Check if time for reminder"""
        if not self.notified_at:
            return True

        days_since_notification = (datetime.utcnow() - self.notified_at).days
        return days_since_notification >= 3  # Remind every 3 days

    def calculate_priority_score(self) -> int:
        """Calculate priority score for ordering"""
        priority_values = {
            Priority.LOW: 1,
            Priority.MEDIUM: 2,
            Priority.HIGH: 3,
            Priority.URGENT: 4
        }

        # Base score from priority enum
        score = priority_values.get(self.priority, 1) * 100

        # Earlier request = higher score
        days_waiting = (datetime.utcnow() - self.created_at).days
        score += days_waiting * 2

        # Closer to expiry = higher urgency
        days_to_expiry = (self.expires_at - datetime.utcnow()).days
        score += (14 - days_to_expiry) * 5

        return score

    def is_expired(self) -> bool:
        """Check if entry is expired"""
        return datetime.utcnow() > self.expires_at and self.status == WaitlistStatus.ACTIVE


# domain/repositories.py
from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID
from datetime import date

class ReservationRepository(ABC):
    @abstractmethod
    async def save(self, reservation: Reservation) -> Reservation:
        pass

    @abstractmethod
    async def find_by_id(self, reservation_id: UUID) -> Optional[Reservation]:
        pass

    @abstractmethod
    async def find_by_confirmation_code(self, code: str) -> Optional[Reservation]:
        pass

    @abstractmethod
    async def find_all(self) -> List[Reservation]:
        pass

    @abstractmethod
    async def update(self, reservation: Reservation) -> Reservation:
        pass

    @abstractmethod
    async def delete(self, reservation_id: UUID) -> bool:
        pass


class AvailabilityRepository(ABC):
    @abstractmethod
    async def save(self, availability: Availability) -> Availability:
        pass

    @abstractmethod
    async def find_by_room_and_date(self, room_type_id: str, date: date) -> Optional[Availability]:
        pass

    @abstractmethod
    async def find_by_room_and_date_range(self, room_type_id: str, start_date: date, end_date: date) -> List[Availability]:
        pass

    @abstractmethod
    async def update(self, availability: Availability) -> Availability:
        pass


class WaitlistRepository(ABC):
    @abstractmethod
    async def save(self, waitlist_entry: WaitlistEntry) -> WaitlistEntry:
        pass

    @abstractmethod
    async def find_by_id(self, waitlist_id: UUID) -> Optional[WaitlistEntry]:
        pass

    @abstractmethod
    async def find_by_guest_id(self, guest_id: UUID) -> List[WaitlistEntry]:
        pass

    @abstractmethod
    async def find_active_by_room_type(self, room_type_id: str) -> List[WaitlistEntry]:
        pass

    @abstractmethod
    async def find_all(self) -> List[WaitlistEntry]:
        pass

    @abstractmethod
    async def update(self, waitlist_entry: WaitlistEntry) -> WaitlistEntry:
        pass

    @abstractmethod
    async def delete(self, waitlist_id: UUID) -> bool:
        pass


# infrastructure/in_memory_repository.py
from typing import Optional, List, Dict
from uuid import UUID
from datetime import date

class InMemoryReservationRepository(ReservationRepository):
    def __init__(self):
        self._storage: Dict[UUID, Reservation] = {}

    async def save(self, reservation: Reservation) -> Reservation:
        self._storage[reservation.reservation_id] = reservation
        return reservation

    async def find_by_id(self, reservation_id: UUID) -> Optional[Reservation]:
        return self._storage.get(reservation_id)

    async def find_by_confirmation_code(self, code: str) -> Optional[Reservation]:
        for reservation in self._storage.values():
            if reservation.confirmation_code == code:
                return reservation
        return None

    async def find_all(self) -> List[Reservation]:
        return list(self._storage.values())

    async def update(self, reservation: Reservation) -> Reservation:
        if reservation.reservation_id in self._storage:
            self._storage[reservation.reservation_id] = reservation
            return reservation
        raise ValueError("Reservation not found")

    async def delete(self, reservation_id: UUID) -> bool:
        if reservation_id in self._storage:
            del self._storage[reservation_id]
            return True
        return False


class InMemoryAvailabilityRepository(AvailabilityRepository):
    def __init__(self):
        self._storage: Dict[tuple, Availability] = {}

    async def save(self, availability: Availability) -> Availability:
        key = (availability.room_type_id, availability.date)
        self._storage[key] = availability
        return availability

    async def find_by_room_and_date(self, room_type_id: str, date: date) -> Optional[Availability]:
        return self._storage.get((room_type_id, date))

    async def find_by_room_and_date_range(self, room_type_id: str, start_date: date, end_date: date) -> List[Availability]:
        results = []
        for (rt_id, d), availability in self._storage.items():
            if rt_id == room_type_id and start_date <= d < end_date:
                results.append(availability)
        return results

    async def update(self, availability: Availability) -> Availability:
        key = (availability.room_type_id, availability.date)
        if key in self._storage:
            self._storage[key] = availability
            return availability
        raise ValueError("Availability not found")


class InMemoryWaitlistRepository(WaitlistRepository):
    def __init__(self):
        self._storage: Dict[UUID, WaitlistEntry] = {}

    async def save(self, waitlist_entry: WaitlistEntry) -> WaitlistEntry:
        self._storage[waitlist_entry.waitlist_id] = waitlist_entry
        return waitlist_entry

    async def find_by_id(self, waitlist_id: UUID) -> Optional[WaitlistEntry]:
        return self._storage.get(waitlist_id)

    async def find_by_guest_id(self, guest_id: UUID) -> List[WaitlistEntry]:
        return [entry for entry in self._storage.values() if entry.guest_id == guest_id]

    async def find_active_by_room_type(self, room_type_id: str) -> List[WaitlistEntry]:
        return [
            entry for entry in self._storage.values()
            if entry.room_type_id == room_type_id and entry.status == WaitlistStatus.ACTIVE
        ]

    async def find_all(self) -> List[WaitlistEntry]:
        return list(self._storage.values())

    async def update(self, waitlist_entry: WaitlistEntry) -> WaitlistEntry:
        if waitlist_entry.waitlist_id in self._storage:
            self._storage[waitlist_entry.waitlist_id] = waitlist_entry
            return waitlist_entry
        raise ValueError("Waitlist entry not found")

    async def delete(self, waitlist_id: UUID) -> bool:
        if waitlist_id in self._storage:
            del self._storage[waitlist_id]
            return True
        return False


# api/schemas.py
from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import List, Optional

class DateRangeRequest(BaseModel):
    check_in: date
    check_out: date

class GuestCountRequest(BaseModel):
    adults: int = Field(ge=1, le=10)
    children: int = Field(ge=0, le=10)

class SpecialRequestRequest(BaseModel):
    type: str
    description: str

class CreateReservationRequest(BaseModel):
    guest_id: UUID
    room_type_id: str
    check_in: date
    check_out: date
    adults: int = Field(ge=1, le=10)
    children: int = Field(ge=0, le=10, default=0)
    booking_source: str = "WEBSITE"
    special_requests: List[SpecialRequestRequest] = []

class UpdateReservationRequest(BaseModel):
    check_in: Optional[date] = None
    check_out: Optional[date] = None
    adults: Optional[int] = Field(None, ge=1, le=10)
    children: Optional[int] = Field(None, ge=0, le=10)
    special_requests: Optional[List[SpecialRequestRequest]] = None

class ReservationResponse(BaseModel):
    reservation_id: UUID
    confirmation_code: str
    guest_id: UUID
    room_type_id: UUID
    check_in: date
    check_out: date
    adults: int
    children: int
    total_amount: Decimal
    currency: str
    status: str
    booking_source: str
    special_requests: List[dict]
    created_at: str
    modified_at: str
    version: int

    @staticmethod
    def from_orm_reservation(reservation) -> "ReservationResponse":
        """Convert domain Reservation to response DTO"""
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            confirmation_code=reservation.confirmation_code,
            guest_id=reservation.guest_id,
            room_type_id=reservation.room_type_id,
            check_in=reservation.date_range.check_in,
            check_out=reservation.date_range.check_out,
            adults=reservation.guest_count.adults,
            children=reservation.guest_count.children,
            total_amount=reservation.total_amount.amount,
            currency=reservation.total_amount.currency,
            status=reservation.status.value,
            booking_source=reservation.booking_source.value,
            special_requests=[{
                "request_id": str(sr.request_id),
                "request_type": sr.request_type.value,
                "description": sr.description,
                "fulfilled": sr.fulfilled
            } for sr in reservation.special_requests],
            created_at=reservation.created_at.isoformat(),
            modified_at=reservation.modified_at.isoformat(),
            version=reservation.version
        )


class ConfirmReservationRequest(BaseModel):
    payment_confirmed: bool = True


class CheckInRequest(BaseModel):
    room_number: str


class CancelReservationRequest(BaseModel):
    reason: str = "Guest requested cancellation"


class AddSpecialRequestRequest(BaseModel):
    request_type: str
    description: str


class SpecialRequestResponse(BaseModel):
    request_id: UUID
    request_type: str
    description: str
    fulfilled: bool = False


class AvailabilityRequest(BaseModel):
    room_type_id: str
    start_date: date
    end_date: date
    required_rooms: int = 1


class AvailabilityResponse(BaseModel):
    room_type_id: str
    start_date: date
    end_date: date
    is_available: bool


class WaitlistRequest(BaseModel):
    guest_id: UUID
    room_type_id: str
    check_in: date
    check_out: date
    adults: int = Field(ge=1, le=10)
    children: int = Field(ge=0, le=10, default=0)
    priority: str = "MEDIUM"


class WaitlistResponse(BaseModel):
    waitlist_id: UUID
    guest_id: UUID
    room_type_id: str
    check_in: date
    check_out: date
    adults: int
    children: int
    priority: str
    status: str
    created_at: str
    expires_at: str
    converted_reservation_id: Optional[UUID] = None

    @staticmethod
    def from_orm_entry(entry) -> "WaitlistResponse":
        """Convert domain WaitlistEntry to response DTO"""
        return WaitlistResponse(
            waitlist_id=entry.waitlist_id,
            guest_id=entry.guest_id,
            room_type_id=entry.room_type_id,
            check_in=entry.requested_dates.check_in,
            check_out=entry.requested_dates.check_out,
            adults=entry.guest_count.adults,
            children=entry.guest_count.children,
            priority=entry.priority.value,
            status=entry.status.value,
            created_at=entry.created_at.isoformat(),
            expires_at=entry.expires_at.isoformat(),
            converted_reservation_id=entry.converted_reservation_id
        )


# application/services.py
from uuid import UUID
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Optional


class ReservationService:
    def __init__(self, repository: ReservationRepository):
        self.repository = repository

    def _calculate_total_amount(self, nights: int) -> Decimal:
        """Calculate total amount based on nights"""
        # Simplified calculation - base rate per night
        base_rate = 1000000  # IDR
        return Decimal(nights * base_rate)

    async def create_reservation(
        self,
        guest_id: UUID,
        room_type_id: str,
        check_in: date,
        check_out: date,
        adults: int,
        children: int,
        special_requests: List[dict],
        booking_source: BookingSource = BookingSource.WEBSITE,
        created_by: str = "SYSTEM"
    ) -> Reservation:
        """Create new reservation with full validation"""
        # Create value objects
        date_range = DateRange(check_in=check_in, check_out=check_out)
        guest_count = GuestCount(adults=adults, children=children)

        # Calculate amount
        nights = date_range.nights()
        total_amount = Money(
            amount=self._calculate_total_amount(nights),
            currency="IDR"
        )

        # Create cancellation policy
        cancellation_policy = CancellationPolicy(
            policy_name="Standard",
            refund_percentage=Decimal("80"),
            deadline_hours=24
        )

        # Use aggregate factory method for creation with validation
        reservation = Reservation.create(
            guest_id=guest_id,
            room_type_id=room_type_id,
            date_range=date_range,
            guest_count=guest_count,
            total_amount=total_amount,
            cancellation_policy=cancellation_policy,
            booking_source=booking_source,
            created_by=created_by
        )

        # Add special requests if any
        for req in special_requests:
            try:
                request_type = RequestType[req.get("type", "").upper()]
                reservation.add_special_request(
                    request_type=request_type,
                    description=req.get("description", "")
                )
            except (KeyError, ValueError):
                pass  # Skip invalid request types

        return await self.repository.save(reservation)

    async def get_reservation(self, reservation_id: UUID) -> Optional[Reservation]:
        """Get reservation by ID"""
        return await self.repository.find_by_id(reservation_id)

    async def get_by_confirmation_code(self, code: str) -> Optional[Reservation]:
        """Get reservation by confirmation code"""
        return await self.repository.find_by_confirmation_code(code)

    async def get_all_reservations(self) -> List[Reservation]:
        """Get all reservations"""
        return await self.repository.find_all()

    async def modify_reservation(
        self,
        reservation_id: UUID,
        check_in: Optional[date] = None,
        check_out: Optional[date] = None,
        adults: Optional[int] = None,
        children: Optional[int] = None,
        room_type_id: Optional[str] = None
    ) -> Optional[Reservation]:
        """Modify existing reservation"""
        reservation = await self.repository.find_by_id(reservation_id)
        if not reservation:
            return None

        # Build optional new date range and guest count
        new_date_range = None
        if check_in and check_out:
            new_date_range = DateRange(check_in=check_in, check_out=check_out)

        new_guest_count = None
        if adults is not None and children is not None:
            new_guest_count = GuestCount(adults=adults, children=children)

        # Use aggregate method for modification with validation
        try:
            reservation.modify(
                new_date_range=new_date_range,
                new_guest_count=new_guest_count,
                new_room_type_id=room_type_id
            )
            return await self.repository.update(reservation)
        except ValueError as e:
            raise ValueError(f"Cannot modify reservation: {str(e)}")

    async def confirm_reservation(
        self,
        reservation_id: UUID,
        payment_confirmed: bool = True
    ) -> Optional[Reservation]:
        """Confirm reservation after payment"""
        reservation = await self.repository.find_by_id(reservation_id)
        if not reservation:
            return None

        try:
            reservation.confirm(payment_confirmed)
            return await self.repository.update(reservation)
        except ValueError as e:
            raise ValueError(f"Cannot confirm reservation: {str(e)}")

    async def check_in_reservation(
        self,
        reservation_id: UUID,
        room_number: str
    ) -> Optional[Reservation]:
        """Check in guest"""
        reservation = await self.repository.find_by_id(reservation_id)
        if not reservation:
            return None

        try:
            reservation.check_in(room_number)
            return await self.repository.update(reservation)
        except ValueError as e:
            raise ValueError(f"Cannot check in: {str(e)}")

    async def check_out_reservation(
        self,
        reservation_id: UUID
    ) -> Optional[Money]:
        """Check out guest and return final bill"""
        reservation = await self.repository.find_by_id(reservation_id)
        if not reservation:
            return None

        try:
            final_bill = reservation.check_out()
            await self.repository.update(reservation)
            return final_bill
        except ValueError as e:
            raise ValueError(f"Cannot check out: {str(e)}")

    async def cancel_reservation(
        self,
        reservation_id: UUID,
        reason: str = "Guest requested cancellation"
    ) -> Optional[Money]:
        """Cancel reservation and calculate refund"""
        reservation = await self.repository.find_by_id(reservation_id)
        if not reservation:
            return None

        try:
            refund = reservation.cancel(reason)
            await self.repository.update(reservation)
            return refund
        except ValueError as e:
            raise ValueError(f"Cannot cancel reservation: {str(e)}")

    async def mark_no_show(self, reservation_id: UUID) -> Optional[Reservation]:
        """Mark reservation as no-show"""
        reservation = await self.repository.find_by_id(reservation_id)
        if not reservation:
            return None

        try:
            reservation.mark_no_show()
            return await self.repository.update(reservation)
        except ValueError as e:
            raise ValueError(f"Cannot mark as no-show: {str(e)}")

    async def add_special_request(
        self,
        reservation_id: UUID,
        request_type: RequestType,
        description: str
    ) -> Optional[SpecialRequest]:
        """Add special request to reservation"""
        reservation = await self.repository.find_by_id(reservation_id)
        if not reservation:
            return None

        try:
            special_request = reservation.add_special_request(request_type, description)
            await self.repository.update(reservation)
            return special_request
        except ValueError as e:
            raise ValueError(f"Cannot add special request: {str(e)}")


class AvailabilityService:
    def __init__(self, repository: AvailabilityRepository):
        self.repository = repository

    async def check_availability(
        self,
        room_type_id: str,
        start_date: date,
        end_date: date,
        required_rooms: int
    ) -> bool:
        """Check if rooms are available for date range"""
        availabilities = await self.repository.find_by_room_and_date_range(
            room_type_id, start_date, end_date
        )

        if not availabilities:
            return False

        # All dates must have availability
        for avail in availabilities:
            if not avail.check_availability(required_rooms):
                return False

        return True

    async def reserve_availability(
        self,
        room_type_id: str,
        start_date: date,
        end_date: date,
        count: int
    ) -> None:
        """Reserve rooms for date range"""
        availabilities = await self.repository.find_by_room_and_date_range(
            room_type_id, start_date, end_date
        )

        for avail in availabilities:
            avail.reserve_rooms(count)
            await self.repository.update(avail)

    async def release_availability(
        self,
        room_type_id: str,
        start_date: date,
        end_date: date,
        count: int
    ) -> None:
        """Release reserved rooms for date range"""
        availabilities = await self.repository.find_by_room_and_date_range(
            room_type_id, start_date, end_date
        )

        for avail in availabilities:
            avail.release_rooms(count)
            await self.repository.update(avail)


class WaitlistService:
    def __init__(self, repository: WaitlistRepository):
        self.repository = repository

    async def add_to_waitlist(
        self,
        guest_id: UUID,
        room_type_id: str,
        requested_dates: DateRange,
        guest_count: GuestCount,
        priority: str = "MEDIUM"
    ) -> WaitlistEntry:
        """Add guest to waitlist"""
        from domain.value_objects import Priority
        priority_enum = Priority[priority.upper()]

        waitlist_entry = WaitlistEntry.add_to_waitlist(
            guest_id=guest_id,
            room_type_id=room_type_id,
            requested_dates=requested_dates,
            guest_count=guest_count,
            priority=priority_enum
        )

        return await self.repository.save(waitlist_entry)

    async def convert_to_reservation(
        self,
        waitlist_id: UUID,
        reservation_id: UUID
    ) -> Optional[WaitlistEntry]:
        """Convert waitlist entry to reservation"""
        entry = await self.repository.find_by_id(waitlist_id)
        if not entry:
            return None

        try:
            entry.convert_to_reservation(reservation_id)
            return await self.repository.update(entry)
        except ValueError as e:
            raise ValueError(f"Cannot convert waitlist: {str(e)}")

    async def get_sorted_waitlist(self, room_type_id: str) -> List[WaitlistEntry]:
        """Get waitlist sorted by priority score"""
        entries = await self.repository.find_active_by_room_type(room_type_id)
        return sorted(entries, key=lambda e: e.calculate_priority_score(), reverse=True)


# main.py
from fastapi import FastAPI, HTTPException, Depends, status
from uuid import UUID
from typing import List
from datetime import date

app = FastAPI(
    title="Hotel Reservation API - DDD Implementation",
    description="Hotel Reservation System with Domain-Driven Design Aggregates",
    version="1.0.0"
)

# Initialize repositories
reservation_repository = InMemoryReservationRepository()
availability_repository = InMemoryAvailabilityRepository()
waitlist_repository = InMemoryWaitlistRepository()

# Dependency injection
def get_reservation_service() -> ReservationService:
    return ReservationService(reservation_repository)

def get_availability_service() -> AvailabilityService:
    return AvailabilityService(availability_repository)

def get_waitlist_service() -> WaitlistService:
    return WaitlistService(waitlist_repository)

# ==================== RESERVATION ENDPOINTS ====================
@app.post("/api/reservations", response_model=ReservationResponse, status_code=201, tags=["Reservations"])
async def create_reservation(
    request: CreateReservationRequest,
    service: ReservationService = Depends(get_reservation_service)
):
    """Create new reservation"""
    try:
        booking_source = BookingSource[request.booking_source.upper()]
        reservation = await service.create_reservation(
            guest_id=request.guest_id,
            room_type_id=request.room_type_id,
            check_in=request.check_in,
            check_out=request.check_out,
            adults=request.adults,
            children=request.children,
            special_requests=[req.dict() for req in request.special_requests],
            booking_source=booking_source
        )
        return ReservationResponse.from_orm_reservation(reservation)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/reservations/{reservation_id}", response_model=ReservationResponse, tags=["Reservations"])
async def get_reservation(
    reservation_id: UUID,
    service: ReservationService = Depends(get_reservation_service)
):
    """Get reservation by ID"""
    reservation = await service.get_reservation(reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return ReservationResponse.from_orm_reservation(reservation)

@app.get("/api/reservations/code/{confirmation_code}", response_model=ReservationResponse, tags=["Reservations"])
async def get_by_confirmation_code(
    confirmation_code: str,
    service: ReservationService = Depends(get_reservation_service)
):
    """Get reservation by confirmation code"""
    reservation = await service.get_by_confirmation_code(confirmation_code)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return ReservationResponse.from_orm_reservation(reservation)

@app.get("/api/reservations", response_model=List[ReservationResponse], tags=["Reservations"])
async def list_reservations(
    service: ReservationService = Depends(get_reservation_service)
):
    """List all reservations"""
    reservations = await service.get_all_reservations()
    return [ReservationResponse.from_orm_reservation(r) for r in reservations]

@app.put("/api/reservations/{reservation_id}", response_model=ReservationResponse, tags=["Reservations"])
async def modify_reservation(
    reservation_id: UUID,
    request: UpdateReservationRequest,
    service: ReservationService = Depends(get_reservation_service)
):
    """Modify reservation details"""
    try:
        reservation = await service.modify_reservation(
            reservation_id=reservation_id,
            check_in=request.check_in,
            check_out=request.check_out,
            adults=request.adults,
            children=request.children,
            room_type_id=request.room_type_id
        )
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return ReservationResponse.from_orm_reservation(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== RESERVATION STATE TRANSITIONS ====================
@app.post("/api/reservations/{reservation_id}/confirm", response_model=ReservationResponse, tags=["Reservations"])
async def confirm_reservation(
    reservation_id: UUID,
    request: ConfirmReservationRequest,
    service: ReservationService = Depends(get_reservation_service)
):
    """Confirm reservation after payment"""
    try:
        reservation = await service.confirm_reservation(
            reservation_id=reservation_id,
            payment_confirmed=request.payment_confirmed
        )
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return ReservationResponse.from_orm_reservation(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reservations/{reservation_id}/check-in", response_model=ReservationResponse, tags=["Reservations"])
async def check_in_guest(
    reservation_id: UUID,
    request: CheckInRequest,
    service: ReservationService = Depends(get_reservation_service)
):
    """Check in guest"""
    try:
        reservation = await service.check_in_reservation(
            reservation_id=reservation_id,
            room_number=request.room_number
        )
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return ReservationResponse.from_orm_reservation(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reservations/{reservation_id}/check-out", tags=["Reservations"])
async def check_out_guest(
    reservation_id: UUID,
    service: ReservationService = Depends(get_reservation_service)
):
    """Check out guest"""
    try:
        final_bill = await service.check_out_reservation(reservation_id)
        if not final_bill:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return {
            "status": "success",
            "final_bill": {
                "amount": str(final_bill.amount),
                "currency": final_bill.currency
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reservations/{reservation_id}/cancel", tags=["Reservations"])
async def cancel_reservation(
    reservation_id: UUID,
    request: CancelReservationRequest,
    service: ReservationService = Depends(get_reservation_service)
):
    """Cancel reservation"""
    try:
        refund = await service.cancel_reservation(
            reservation_id=reservation_id,
            reason=request.reason
        )
        if not refund:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return {
            "status": "success",
            "refund_amount": {
                "amount": str(refund.amount),
                "currency": refund.currency
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reservations/{reservation_id}/no-show", response_model=ReservationResponse, tags=["Reservations"])
async def mark_no_show(
    reservation_id: UUID,
    service: ReservationService = Depends(get_reservation_service)
):
    """Mark reservation as no-show"""
    try:
        reservation = await service.mark_no_show(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return ReservationResponse.from_orm_reservation(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== SPECIAL REQUESTS ====================
@app.post("/api/reservations/{reservation_id}/special-requests", response_model=SpecialRequestResponse, tags=["Special Requests"])
async def add_special_request(
    reservation_id: UUID,
    request: AddSpecialRequestRequest,
    service: ReservationService = Depends(get_reservation_service)
):
    """Add special request to reservation"""
    try:
        request_type = RequestType[request.request_type.upper()]
        special_request = await service.add_special_request(
            reservation_id=reservation_id,
            request_type=request_type,
            description=request.description
        )
        if not special_request:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return SpecialRequestResponse(
            request_id=special_request.request_id,
            request_type=special_request.request_type.value,
            description=special_request.description,
            fulfilled=special_request.fulfilled
        )
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== AVAILABILITY ENDPOINTS ====================
@app.get("/api/availability/{room_type_id}", response_model=AvailabilityResponse, tags=["Availability"])
async def check_availability(
    room_type_id: str,
    start_date: date,
    end_date: date,
    required_rooms: int = 1,
    service: AvailabilityService = Depends(get_availability_service)
):
    """Check room availability for date range"""
    try:
        is_available = await service.check_availability(
            room_type_id=room_type_id,
            start_date=start_date,
            end_date=end_date,
            required_rooms=required_rooms
        )
        return AvailabilityResponse(
            room_type_id=room_type_id,
            start_date=start_date,
            end_date=end_date,
            is_available=is_available
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== WAITLIST ENDPOINTS ====================
@app.post("/api/waitlist", response_model=WaitlistResponse, status_code=201, tags=["Waitlist"])
async def add_to_waitlist(
    request: WaitlistRequest,
    service: WaitlistService = Depends(get_waitlist_service)
):
    """Add guest to waitlist"""
    try:
        from domain.value_objects import DateRange, GuestCount
        requested_dates = DateRange(check_in=request.check_in, check_out=request.check_out)
        guest_count = GuestCount(adults=request.adults, children=request.children)

        entry = await service.add_to_waitlist(
            guest_id=request.guest_id,
            room_type_id=request.room_type_id,
            requested_dates=requested_dates,
            guest_count=guest_count,
            priority=request.priority
        )
        return WaitlistResponse.from_orm_entry(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/waitlist/{waitlist_id}", response_model=WaitlistResponse, tags=["Waitlist"])
async def get_waitlist_entry(
    waitlist_id: UUID,
    service: WaitlistService = Depends(get_waitlist_service)
):
    """Get waitlist entry by ID"""
    entry = await service.repository.find_by_id(waitlist_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    return WaitlistResponse.from_orm_entry(entry)

@app.post("/api/waitlist/{waitlist_id}/convert", response_model=WaitlistResponse, tags=["Waitlist"])
async def convert_to_reservation(
    waitlist_id: UUID,
    reservation_id: UUID,
    service: WaitlistService = Depends(get_waitlist_service)
):
    """Convert waitlist entry to reservation"""
    try:
        entry = await service.convert_to_reservation(
            waitlist_id=waitlist_id,
            reservation_id=reservation_id
        )
        if not entry:
            raise HTTPException(status_code=404, detail="Waitlist entry not found")
        return WaitlistResponse.from_orm_entry(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "Hotel Reservation API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)