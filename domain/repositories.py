"""Domain Repository Interfaces"""
from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID
from datetime import date

from domain.entities import Reservation, Availability, WaitlistEntry


class ReservationRepository(ABC):
    """Repository interface for Reservation Aggregate"""

    @abstractmethod
    async def save(self, reservation: Reservation) -> Reservation:
        """Save reservation"""
        pass

    @abstractmethod
    async def find_by_id(self, reservation_id: UUID) -> Optional[Reservation]:
        """Find reservation by ID"""
        pass

    @abstractmethod
    async def find_by_confirmation_code(self, code: str) -> Optional[Reservation]:
        """Find reservation by confirmation code"""
        pass

    @abstractmethod
    async def find_by_guest_id(self, guest_id: UUID) -> List[Reservation]:
        """Find reservations by guest ID"""
        pass

    @abstractmethod
    async def find_all(self) -> List[Reservation]:
        """Find all reservations"""
        pass

    @abstractmethod
    async def update(self, reservation: Reservation) -> Reservation:
        """Update reservation"""
        pass

    @abstractmethod
    async def delete(self, reservation_id: UUID) -> bool:
        """Delete reservation"""
        pass


class AvailabilityRepository(ABC):
    """Repository interface for Availability Aggregate"""

    @abstractmethod
    async def save(self, availability: Availability) -> Availability:
        """Save availability"""
        pass

    @abstractmethod
    async def find_by_room_and_date(self, room_type_id: str, availability_date: date) -> Optional[Availability]:
        """Find availability for specific room and date"""
        pass

    @abstractmethod
    async def find_by_room_and_date_range(self, room_type_id: str, start_date: date, end_date: date) -> List[Availability]:
        """Find availabilities for date range"""
        pass

    @abstractmethod
    async def find_all_by_room(self, room_type_id: str) -> List[Availability]:
        """Find all availabilities for a room type"""
        pass

    @abstractmethod
    async def update(self, availability: Availability) -> Availability:
        """Update availability"""
        pass


class WaitlistRepository(ABC):
    """Repository interface for Waitlist Aggregate"""

    @abstractmethod
    async def save(self, waitlist_entry: WaitlistEntry) -> WaitlistEntry:
        """Save waitlist entry"""
        pass

    @abstractmethod
    async def find_by_id(self, waitlist_id: UUID) -> Optional[WaitlistEntry]:
        """Find waitlist entry by ID"""
        pass

    @abstractmethod
    async def find_by_guest_id(self, guest_id: UUID) -> List[WaitlistEntry]:
        """Find waitlist entries for a guest"""
        pass

    @abstractmethod
    async def find_active_by_room_type(self, room_type_id: str) -> List[WaitlistEntry]:
        """Find active waitlist entries for a room type"""
        pass

    @abstractmethod
    async def find_all_active(self) -> List[WaitlistEntry]:
        """Find all active waitlist entries"""
        pass

    @abstractmethod
    async def find_all(self) -> List[WaitlistEntry]:
        """Find all waitlist entries"""
        pass

    @abstractmethod
    async def update(self, waitlist_entry: WaitlistEntry) -> WaitlistEntry:
        """Update waitlist entry"""
        pass

    @abstractmethod
    async def delete(self, waitlist_id: UUID) -> bool:
        """Delete waitlist entry"""
        pass
