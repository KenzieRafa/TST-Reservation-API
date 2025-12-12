"""Domain Entities - Aggregates"""
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List
from decimal import Decimal

from domain.enums import ReservationStatus, ReservationSource, RequestType, WaitlistStatus, Priority
from domain.value_objects import DateRange, GuestCount, Money, CancellationPolicy, SpecialRequest


class Reservation(BaseModel):
    """Reservation Aggregate Root Entity"""

    # Identity
    reservation_id: UUID = Field(default_factory=uuid4)
    confirmation_code: str

    # References to other contexts
    guest_id: UUID
    room_type_id: str

    # Value Objects
    date_range: DateRange
    guest_count: GuestCount
    total_amount: Money
    cancellation_policy: CancellationPolicy

    # Enums/Status
    status: ReservationStatus = ReservationStatus.PENDING
    reservation_source: ReservationSource = ReservationSource.WEBSITE

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
        reservation_source: ReservationSource,
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
            reservation_source=reservation_source,
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
        now = datetime.now(timezone.utc)
        checkin_datetime = datetime.combine(self.date_range.check_in, datetime.min.time())
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
        nights = self.get_nights()
        # Assuming a base rate per night
        base_rate = 1000000  # IDR
        new_amount = Decimal(nights * base_rate)

        self.total_amount = Money(
            amount=new_amount,
            currency=self.total_amount.currency
        )


class Availability(BaseModel):
    """Availability Aggregate Root Entity"""

    # Composite Identity
    room_type_id: str
    availability_date: date

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
    def is_fully_reserved(self) -> bool:
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


class WaitlistEntry(BaseModel):
    """Waitlist Aggregate Root Entity"""

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
        if new_priority.value > self.priority.value:
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
        # Base score from priority enum
        score = self.priority.value * 100

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
