"""In-Memory Repository Implementations"""
from typing import Optional, List, Dict
from uuid import UUID
from datetime import date

from domain.repositories import ReservationRepository, AvailabilityRepository, WaitlistRepository
from domain.entities import Reservation, Availability, WaitlistEntry
from domain.enums import WaitlistStatus


class InMemoryReservationRepository(ReservationRepository):
    """In-memory implementation of ReservationRepository"""

    def __init__(self):
        self._storage: Dict[UUID, Reservation] = {}

    async def save(self, reservation: Reservation) -> Reservation:
        """Save reservation to memory"""
        self._storage[reservation.reservation_id] = reservation
        return reservation

    async def find_by_id(self, reservation_id: UUID) -> Optional[Reservation]:
        """Find reservation by ID"""
        return self._storage.get(reservation_id)

    async def find_by_confirmation_code(self, code: str) -> Optional[Reservation]:
        """Find reservation by confirmation code"""
        for reservation in self._storage.values():
            if reservation.confirmation_code == code:
                return reservation
        return None

    async def find_by_guest_id(self, guest_id: UUID) -> List[Reservation]:
        """Find reservations by guest ID"""
        return [r for r in self._storage.values() if r.guest_id == guest_id]

    async def find_all(self) -> List[Reservation]:
        """Find all reservations"""
        return list(self._storage.values())

    async def update(self, reservation: Reservation) -> Reservation:
        """Update reservation"""
        if reservation.reservation_id in self._storage:
            self._storage[reservation.reservation_id] = reservation
            return reservation
        raise ValueError("Reservation not found")

    async def delete(self, reservation_id: UUID) -> bool:
        """Delete reservation"""
        if reservation_id in self._storage:
            del self._storage[reservation_id]
            return True
        return False


class InMemoryAvailabilityRepository(AvailabilityRepository):
    """In-memory implementation of AvailabilityRepository"""

    def __init__(self):
        self._storage: Dict[tuple, Availability] = {}

    async def save(self, availability: Availability) -> Availability:
        """Save availability to memory"""
        key = (availability.room_type_id, availability.availability_date)
        self._storage[key] = availability
        return availability

    async def find_by_room_and_date(self, room_type_id: str, availability_date: date) -> Optional[Availability]:
        """Find availability for specific room and date"""
        return self._storage.get((room_type_id, availability_date))

    async def find_by_room_and_date_range(self, room_type_id: str, start_date: date, end_date: date) -> List[Availability]:
        """Find availabilities for date range"""
        results = []
        for (rt_id, d), availability in self._storage.items():
            if rt_id == room_type_id and start_date <= d < end_date:
                results.append(availability)
        return results

    async def find_all_by_room(self, room_type_id: str) -> List[Availability]:
        """Find all availabilities for a room type"""
        return [a for (rt_id, _), a in self._storage.items() if rt_id == room_type_id]

    async def update(self, availability: Availability) -> Availability:
        """Update availability"""
        key = (availability.room_type_id, availability.availability_date)
        if key in self._storage:
            self._storage[key] = availability
            return availability
        raise ValueError("Availability not found")


class InMemoryWaitlistRepository(WaitlistRepository):
    """In-memory implementation of WaitlistRepository"""

    def __init__(self):
        self._storage: Dict[UUID, WaitlistEntry] = {}

    async def save(self, waitlist_entry: WaitlistEntry) -> WaitlistEntry:
        """Save waitlist entry to memory"""
        self._storage[waitlist_entry.waitlist_id] = waitlist_entry
        return waitlist_entry

    async def find_by_id(self, waitlist_id: UUID) -> Optional[WaitlistEntry]:
        """Find waitlist entry by ID"""
        return self._storage.get(waitlist_id)

    async def find_by_guest_id(self, guest_id: UUID) -> List[WaitlistEntry]:
        """Find waitlist entries for a guest"""
        return [entry for entry in self._storage.values() if entry.guest_id == guest_id]

    async def find_active_by_room_type(self, room_type_id: str) -> List[WaitlistEntry]:
        """Find active waitlist entries for a room type"""
        return [
            entry for entry in self._storage.values()
            if entry.room_type_id == room_type_id and entry.status == WaitlistStatus.ACTIVE
        ]

    async def find_all_active(self) -> List[WaitlistEntry]:
        """Find all active waitlist entries"""
        return [entry for entry in self._storage.values() if entry.status == WaitlistStatus.ACTIVE]

    async def find_all(self) -> List[WaitlistEntry]:
        """Find all waitlist entries"""
        return list(self._storage.values())

    async def update(self, waitlist_entry: WaitlistEntry) -> WaitlistEntry:
        """Update waitlist entry"""
        if waitlist_entry.waitlist_id in self._storage:
            self._storage[waitlist_entry.waitlist_id] = waitlist_entry
            return waitlist_entry
        raise ValueError("Waitlist entry not found")

    async def delete(self, waitlist_id: UUID) -> bool:
        """Delete waitlist entry"""
        if waitlist_id in self._storage:
            del self._storage[waitlist_id]
            return True
        return False
