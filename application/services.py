"""Application Services - Business use cases"""
from uuid import UUID
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from domain.repositories import ReservationRepository, AvailabilityRepository, WaitlistRepository
from domain.entities import Reservation, Availability, WaitlistEntry
from domain.enums import ReservationSource, RequestType, Priority
from domain.value_objects import DateRange, GuestCount, Money, CancellationPolicy


class ReservationService:
    """Service for Reservation business use cases"""

    def __init__(self,
                 repository: ReservationRepository,
                 availability_repo: Optional[AvailabilityRepository] = None,
                 waitlist_repo: Optional[WaitlistRepository] = None):
        self.repository = repository
        self.availability_repo = availability_repo
        self.waitlist_repo = waitlist_repo

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
        reservation_source: ReservationSource = ReservationSource.WEBSITE,
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
            reservation_source=reservation_source,
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

    async def get_reservation_by_confirmation_code(self, code: str) -> Optional[Reservation]:
        """Get reservation by confirmation code"""
        return await self.repository.find_by_confirmation_code(code)

    async def get_reservations_by_guest(self, guest_id: UUID) -> List[Reservation]:
        """Get all reservations for a guest"""
        return await self.repository.find_by_guest_id(guest_id)

    async def get_all_reservations(self) -> List[Reservation]:
        """Get all reservations"""
        return await self.repository.find_all()

    async def modify_reservation(
        self,
        reservation_id: UUID,
        new_check_in: Optional[date] = None,
        new_check_out: Optional[date] = None,
        new_adults: Optional[int] = None,
        new_children: Optional[int] = None,
        new_room_type_id: Optional[str] = None
    ) -> Optional[Reservation]:
        """Modify existing reservation"""
        reservation = await self.repository.find_by_id(reservation_id)
        if not reservation:
            return None

        # Build optional new date range and guest count
        new_date_range = None
        if new_check_in and new_check_out:
            new_date_range = DateRange(check_in=new_check_in, check_out=new_check_out)

        new_guest_count = None
        if new_adults is not None and new_children is not None:
            new_guest_count = GuestCount(adults=new_adults, children=new_children)

        # Use aggregate method for modification with validation
        try:
            reservation.modify(
                new_date_range=new_date_range,
                new_guest_count=new_guest_count,
                new_room_type_id=new_room_type_id
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

    async def check_in_guest(
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

    async def check_out_guest(
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
    ) -> Optional[Reservation]:
        """Add special request to reservation"""
        reservation = await self.repository.find_by_id(reservation_id)
        if not reservation:
            return None

        try:
            reservation.add_special_request(request_type, description)
            await self.repository.update(reservation)
            return reservation
        except ValueError as e:
            raise ValueError(f"Cannot add special request: {str(e)}")


class AvailabilityService:
    """Service for Availability business use cases"""

    def __init__(self, repository: AvailabilityRepository):
        self.repository = repository

    async def create_availability(
        self,
        room_type_id: str,
        availability_date: date,
        total_rooms: int,
        overbooking_threshold: int = 0
    ) -> Availability:
        """Create availability for a room type on a specific date"""
        availability = Availability(
            room_type_id=room_type_id,
            availability_date=availability_date,
            total_rooms=total_rooms,
            reserved_rooms=0,
            blocked_rooms=0,
            overbooking_threshold=overbooking_threshold
        )
        return await self.repository.save(availability)

    async def get_availability(self, room_type_id: str, availability_date: date) -> Optional[Availability]:
        """Get availability for a specific room type and date"""
        return await self.repository.find_by_room_and_date(room_type_id, availability_date)

    async def check_availability(
        self,
        room_type_id: str,
        start_date: date,
        end_date: date,
        required_count: int
    ) -> bool:
        """Check if rooms are available for date range"""
        availabilities = await self.repository.find_by_room_and_date_range(
            room_type_id, start_date, end_date
        )

        if not availabilities:
            return False

        # All dates must have availability
        for avail in availabilities:
            if not avail.check_availability(required_count):
                return False

        return True

    async def reserve_rooms(
        self,
        room_type_id: str,
        start_date: date,
        end_date: date,
        count: int
    ) -> bool:
        """Reserve rooms for date range"""
        availabilities = await self.repository.find_by_room_and_date_range(
            room_type_id, start_date, end_date
        )

        if not availabilities:
            return False

        try:
            for avail in availabilities:
                avail.reserve_rooms(count)
                await self.repository.update(avail)
            return True
        except ValueError:
            return False

    async def release_rooms(
        self,
        room_type_id: str,
        start_date: date,
        end_date: date,
        count: int
    ) -> bool:
        """Release reserved rooms for date range"""
        availabilities = await self.repository.find_by_room_and_date_range(
            room_type_id, start_date, end_date
        )

        if not availabilities:
            return False

        try:
            for avail in availabilities:
                avail.release_rooms(count)
                await self.repository.update(avail)
            return True
        except ValueError:
            return False

    async def block_rooms(
        self,
        room_type_id: str,
        start_date: date,
        end_date: date,
        count: int,
        reason: str
    ) -> bool:
        """Block rooms for maintenance/events for date range"""
        availabilities = await self.repository.find_by_room_and_date_range(
            room_type_id, start_date, end_date
        )

        if not availabilities:
            return False

        try:
            for avail in availabilities:
                avail.block_rooms(count, reason)
                await self.repository.update(avail)
            return True
        except ValueError:
            return False

    async def unblock_rooms(
        self,
        room_type_id: str,
        start_date: date,
        end_date: date,
        count: int
    ) -> bool:
        """Unblock rooms after maintenance for date range"""
        availabilities = await self.repository.find_by_room_and_date_range(
            room_type_id, start_date, end_date
        )

        if not availabilities:
            return False

        try:
            for avail in availabilities:
                avail.unblock_rooms(count)
                await self.repository.update(avail)
            return True
        except ValueError:
            return False


class WaitlistService:
    """Service for Waitlist business use cases"""

    def __init__(self, repository: WaitlistRepository):
        self.repository = repository

    async def add_to_waitlist(
        self,
        guest_id: UUID,
        room_type_id: str,
        requested_dates: DateRange,
        guest_count: GuestCount,
        priority: Priority = Priority.MEDIUM
    ) -> WaitlistEntry:
        """Add guest to waitlist"""
        waitlist_entry = WaitlistEntry.add_to_waitlist(
            guest_id=guest_id,
            room_type_id=room_type_id,
            requested_dates=requested_dates,
            guest_count=guest_count,
            priority=priority
        )

        return await self.repository.save(waitlist_entry)

    async def get_waitlist_entry(self, waitlist_id: UUID) -> Optional[WaitlistEntry]:
        """Get waitlist entry by ID"""
        return await self.repository.find_by_id(waitlist_id)

    async def get_guest_waitlist(self, guest_id: UUID) -> List[WaitlistEntry]:
        """Get all waitlist entries for a guest"""
        return await self.repository.find_by_guest_id(guest_id)

    async def get_room_waitlist(self, room_type_id: str) -> List[WaitlistEntry]:
        """Get waitlist entries for a room type (sorted by priority)"""
        entries = await self.repository.find_active_by_room_type(room_type_id)
        return sorted(entries, key=lambda e: e.calculate_priority_score(), reverse=True)

    async def get_active_waitlist(self) -> List[WaitlistEntry]:
        """Get all active waitlist entries"""
        return await self.repository.find_all_active()

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

    async def expire_entry(self, waitlist_id: UUID) -> Optional[WaitlistEntry]:
        """Mark waitlist entry as expired"""
        entry = await self.repository.find_by_id(waitlist_id)
        if not entry:
            return None

        entry.expire()
        return await self.repository.update(entry)

    async def extend_expiry(self, waitlist_id: UUID, additional_days: int) -> Optional[WaitlistEntry]:
        """Extend waitlist entry expiry date"""
        entry = await self.repository.find_by_id(waitlist_id)
        if not entry:
            return None

        try:
            entry.extend_expiry(additional_days)
            return await self.repository.update(entry)
        except ValueError as e:
            raise ValueError(f"Cannot extend expiry: {str(e)}")

    async def upgrade_priority(self, waitlist_id: UUID, new_priority: Priority) -> Optional[WaitlistEntry]:
        """Upgrade waitlist entry priority"""
        entry = await self.repository.find_by_id(waitlist_id)
        if not entry:
            return None

        entry.upgrade_priority(new_priority)
        return await self.repository.update(entry)

    async def mark_notified(self, waitlist_id: UUID) -> Optional[WaitlistEntry]:
        """Mark waitlist entry as notified"""
        entry = await self.repository.find_by_id(waitlist_id)
        if not entry:
            return None

        entry.mark_notified()
        return await self.repository.update(entry)

    async def get_entries_to_notify(self) -> List[WaitlistEntry]:
        """Get waitlist entries that need notification"""
        entries = await self.repository.find_all_active()
        return [e for e in entries if e.should_notify_again()]
