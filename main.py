from fastapi import FastAPI, HTTPException, Depends
from uuid import UUID
from datetime import date, timedelta
from typing import List, Optional
from fastapi.security import OAuth2PasswordRequestForm

from api.schemas import (
    # Reservation
    CreateReservationRequest, ModifyReservationRequest, AddSpecialRequestRequest,
    ConfirmReservationRequest, CheckInRequest, CancelReservationRequest,
    ReservationResponse, SpecialRequestResponse, MoneyResponse,
    # Availability
    CreateAvailabilityRequest, AvailabilityResponse, CheckAvailabilityRequest,
    ReserveRoomsRequest, BlockRoomsRequest,
    # Waitlist
    CreateWaitlistRequest, WaitlistResponse, ConvertWaitlistRequest,
    ExtendWaitlistRequest, UpgradePriorityRequest,
    # Auth
    Token, UserResponse
)

from api.dependencies import get_current_active_user, fake_users_db, get_user
from infrastructure.security import verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from domain.auth import User

from application.services import ReservationService, AvailabilityService, WaitlistService
from infrastructure.repositories.in_memory_repositories import (
    InMemoryReservationRepository, InMemoryAvailabilityRepository, InMemoryWaitlistRepository
)
from domain.enums import ReservationSource, Priority, ReservationStatus, RequestType, WaitlistStatus
from domain.value_objects import DateRange, GuestCount

app = FastAPI(
    title="Hotel Reservation API",
    description="API untuk Reservation Context dengan Domain-Driven Design",
    version="1.0.0"
)

# Initialize repositories
reservation_repo = InMemoryReservationRepository()
availability_repo = InMemoryAvailabilityRepository()
waitlist_repo = InMemoryWaitlistRepository()

# Dependency injection
def get_reservation_service() -> ReservationService:
    return ReservationService(reservation_repo, availability_repo, waitlist_repo)

def get_availability_service() -> AvailabilityService:
    return AvailabilityService(availability_repo)

def get_waitlist_service() -> WaitlistService:
    return WaitlistService(waitlist_repo)

# ============================================================================
# HEALTH & ENUM REFERENCE ENDPOINTS
# ============================================================================

@app.get("/api/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "API is running"}

@app.get("/api/enums/reservation-status", tags=["Enum Reference"])
async def get_reservation_statuses():
    """Get all ReservationStatus enum values"""
    return {
        "values": [f"{item.name}" for item in ReservationStatus],
        "description": "Reservation status values: PENDING, CONFIRMED, CHECKED_IN, CHECKED_OUT, CANCELLED, NO_SHOW"
    }

@app.get("/api/enums/reservation-source", tags=["Enum Reference"])
async def get_reservation_sources():
    """Get all ReservationSource enum values"""
    return {
        "values": [f"{item.name}" for item in ReservationSource],
        "description": "Reservation source values: WEBSITE, MOBILE_APP, PHONE, OTA, DIRECT, CORPORATE"
    }

@app.get("/api/enums/request-type", tags=["Enum Reference"])
async def get_request_types():
    """Get all RequestType enum values"""
    return {
        "values": [f"{item.name}" for item in RequestType],
        "description": "Request type values: EARLY_CHECK_IN, LATE_CHECK_OUT, HIGH_FLOOR, ACCESSIBLE_ROOM, QUIET_ROOM, CRIBS, EXTRA_BED, SPECIAL_AMENITIES"
    }

@app.get("/api/enums/waitlist-status", tags=["Enum Reference"])
async def get_waitlist_statuses():
    """Get all WaitlistStatus enum values"""
    return {
        "values": [f"{item.name}" for item in WaitlistStatus],
        "description": "Waitlist status values: ACTIVE, CONVERTED, EXPIRED, CANCELLED"
    }

@app.get("/api/enums/priority", tags=["Enum Reference"])
async def get_priorities():
    """Get all Priority enum values"""
    return {
        "values": {item.name: item.value for item in Priority},
        "description": "Priority values: LOW=1, MEDIUM=2, HIGH=3, URGENT=4"
    }

# ============================================================================
# AUTH ENDPOINTS
# ============================================================================

@app.post("/token", response_model=Token, tags=["Auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user(fake_users_db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=UserResponse, tags=["Auth"])
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

# ============================================================================
# RESERVATION ENDPOINTS
# ============================================================================

@app.post("/api/reservations", response_model=ReservationResponse, status_code=201, tags=["Reservations"])
async def create_reservation(
    request: CreateReservationRequest,
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Create new reservation"""
    try:
        # reservation_source is already ReservationSource enum from Pydantic validation
        special_requests = [{"type": req.type.value, "description": req.description} for req in request.special_requests]

        reservation = await service.create_reservation(
            guest_id=request.guest_id,
            room_type_id=request.room_type_id,
            check_in=request.check_in,
            check_out=request.check_out,
            adults=request.adults,
            children=request.children,
            reservation_source=request.reservation_source,
            special_requests=special_requests,
            created_by=request.created_by
        )

        return _reservation_to_response(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/reservations", response_model=List[ReservationResponse], tags=["Reservations"])
async def get_all_reservations(
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Get all reservations"""
    reservations = await service.get_all_reservations()
    return [_reservation_to_response(r) for r in reservations]

@app.get("/api/reservations/{reservation_id}", response_model=ReservationResponse, tags=["Reservations"])
async def get_reservation(
    reservation_id: UUID,
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Get reservation by ID"""
    reservation = await service.get_reservation(reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return _reservation_to_response(reservation)

@app.get("/api/reservations/guest/{guest_id}", response_model=List[ReservationResponse], tags=["Reservations"])
async def get_guest_reservations(
    guest_id: UUID,
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Get all reservations for a guest"""
    reservations = await service.get_reservations_by_guest(guest_id)
    return [_reservation_to_response(r) for r in reservations]

@app.get("/api/reservations/code/{confirmation_code}", response_model=ReservationResponse, tags=["Reservations"])
async def get_reservation_by_code(
    confirmation_code: str,
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Get reservation by confirmation code"""
    reservation = await service.get_reservation_by_confirmation_code(confirmation_code)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return _reservation_to_response(reservation)

@app.put("/api/reservations/{reservation_id}", response_model=ReservationResponse, tags=["Reservations"])
async def modify_reservation(
    reservation_id: UUID,
    request: ModifyReservationRequest,
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Modify reservation details"""
    try:
        reservation = await service.modify_reservation(
            reservation_id=reservation_id,
            new_check_in=request.check_in,
            new_check_out=request.check_out,
            new_adults=request.adults,
            new_children=request.children,
            new_room_type_id=request.room_type_id
        )
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return _reservation_to_response(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reservations/{reservation_id}/special-requests", response_model=ReservationResponse, tags=["Reservations"])
async def add_special_request(
    reservation_id: UUID,
    request: AddSpecialRequestRequest,
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Add special request to reservation"""
    try:
        reservation = await service.add_special_request(
            reservation_id=reservation_id,
            request_type=request.request_type,
            description=request.description
        )
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return _reservation_to_response(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reservations/{reservation_id}/confirm", response_model=ReservationResponse, tags=["Reservations"])
async def confirm_reservation(
    reservation_id: UUID,
    request: ConfirmReservationRequest,
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Confirm reservation after payment"""
    try:
        reservation = await service.confirm_reservation(
            reservation_id=reservation_id,
            payment_confirmed=request.payment_confirmed
        )
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return _reservation_to_response(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reservations/{reservation_id}/check-in", response_model=ReservationResponse, tags=["Reservations"])
async def check_in_guest(
    reservation_id: UUID,
    request: CheckInRequest,
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Check in guest"""
    try:
        reservation = await service.check_in_guest(
            reservation_id=reservation_id,
            room_number=request.room_number
        )
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return _reservation_to_response(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reservations/{reservation_id}/check-out", response_model=MoneyResponse, tags=["Reservations"])
async def check_out_guest(
    reservation_id: UUID,
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Check out guest"""
    try:
        final_amount = await service.check_out_guest(reservation_id)
        if not final_amount:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return {"amount": final_amount.amount, "currency": final_amount.currency}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reservations/{reservation_id}/cancel", response_model=MoneyResponse, tags=["Reservations"])
async def cancel_reservation(
    reservation_id: UUID,
    request: CancelReservationRequest,
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Cancel reservation"""
    try:
        refund_amount = await service.cancel_reservation(
            reservation_id=reservation_id,
            reason=request.reason
        )
        if not refund_amount:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return {"amount": refund_amount.amount, "currency": refund_amount.currency}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reservations/{reservation_id}/no-show", response_model=ReservationResponse, tags=["Reservations"])
async def mark_no_show(
    reservation_id: UUID,
    service: ReservationService = Depends(get_reservation_service),
    current_user: User = Depends(get_current_active_user)
):
    """Mark guest as no-show"""
    try:
        reservation = await service.mark_no_show(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return _reservation_to_response(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ============================================================================
# AVAILABILITY ENDPOINTS
# ============================================================================

@app.post("/api/availability", response_model=AvailabilityResponse, status_code=201, tags=["Availability"])
async def create_availability(
    request: CreateAvailabilityRequest,
    service: AvailabilityService = Depends(get_availability_service),
    current_user: User = Depends(get_current_active_user)
):
    """Create availability for a room type on a specific date"""
    try:
        availability = await service.create_availability(
            room_type_id=request.room_type_id,
            availability_date=request.availability_date,
            total_rooms=request.total_rooms,
            overbooking_threshold=request.overbooking_threshold
        )
        return _availability_to_response(availability)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/availability/{room_type_id}/{availability_date}", response_model=AvailabilityResponse, tags=["Availability"])
async def get_availability(
    room_type_id: str,
    availability_date: date,
    service: AvailabilityService = Depends(get_availability_service),
    current_user: User = Depends(get_current_active_user)
):
    """Get availability for a specific room type and date"""
    availability = await service.get_availability(room_type_id, availability_date)
    if not availability:
        raise HTTPException(status_code=404, detail="Availability not found")
    return _availability_to_response(availability)

@app.post("/api/availability/check", tags=["Availability"])
async def check_availability(
    request: CheckAvailabilityRequest,
    service: AvailabilityService = Depends(get_availability_service),
    current_user: User = Depends(get_current_active_user)
):
    """Check if rooms are available for a date range"""
    available = await service.check_availability(
        room_type_id=request.room_type_id,
        start_date=request.start_date,
        end_date=request.end_date,
        required_count=request.required_count
    )
    return {"available": available}

@app.post("/api/availability/reserve", tags=["Availability"])
async def reserve_rooms(
    request: ReserveRoomsRequest,
    service: AvailabilityService = Depends(get_availability_service),
    current_user: User = Depends(get_current_active_user)
):
    """Reserve rooms for a date range"""
    try:
        success = await service.reserve_rooms(
            room_type_id=request.room_type_id,
            start_date=request.start_date,
            end_date=request.end_date,
            count=request.count
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to reserve rooms")
        return {"success": True, "message": "Rooms reserved successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/availability/release", tags=["Availability"])
async def release_rooms(
    request: ReserveRoomsRequest,
    service: AvailabilityService = Depends(get_availability_service),
    current_user: User = Depends(get_current_active_user)
):
    """Release rooms for a date range"""
    try:
        success = await service.release_rooms(
            room_type_id=request.room_type_id,
            start_date=request.start_date,
            end_date=request.end_date,
            count=request.count
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to release rooms")
        return {"success": True, "message": "Rooms released successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/availability/block", tags=["Availability"])
async def block_rooms(
    request: BlockRoomsRequest,
    service: AvailabilityService = Depends(get_availability_service),
    current_user: User = Depends(get_current_active_user)
):
    """Block rooms for maintenance/events"""
    try:
        success = await service.block_rooms(
            room_type_id=request.room_type_id,
            start_date=request.start_date,
            end_date=request.end_date,
            count=request.count,
            reason=request.reason
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to block rooms")
        return {"success": True, "message": "Rooms blocked successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/availability/unblock", tags=["Availability"])
async def unblock_rooms(
    request: ReserveRoomsRequest,
    service: AvailabilityService = Depends(get_availability_service),
    current_user: User = Depends(get_current_active_user)
):
    """Unblock rooms after maintenance"""
    try:
        success = await service.unblock_rooms(
            room_type_id=request.room_type_id,
            start_date=request.start_date,
            end_date=request.end_date,
            count=request.count
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to unblock rooms")
        return {"success": True, "message": "Rooms unblocked successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ============================================================================
# WAITLIST ENDPOINTS
# ============================================================================

@app.post("/api/waitlist", response_model=WaitlistResponse, status_code=201, tags=["Waitlist"])
async def add_to_waitlist(
    request: CreateWaitlistRequest,
    service: WaitlistService = Depends(get_waitlist_service),
    current_user: User = Depends(get_current_active_user)
):
    """Add guest to waitlist"""
    try:
        priority = Priority(int(request.priority))
        requested_dates = DateRange(check_in=request.check_in, check_out=request.check_out)
        guest_count = GuestCount(adults=request.adults, children=request.children)

        entry = await service.add_to_waitlist(
            guest_id=request.guest_id,
            room_type_id=request.room_type_id,
            requested_dates=requested_dates,
            guest_count=guest_count,
            priority=priority
        )
        return _waitlist_to_response(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/waitlist/active", response_model=List[WaitlistResponse], tags=["Waitlist"])
async def get_active_waitlist(
    service: WaitlistService = Depends(get_waitlist_service),
    current_user: User = Depends(get_current_active_user)
):
    """Get all active waitlist entries"""
    entries = await service.get_active_waitlist()
    return [_waitlist_to_response(e) for e in entries]

@app.get("/api/waitlist/guest/{guest_id}", response_model=List[WaitlistResponse], tags=["Waitlist"])
async def get_guest_waitlist(
    guest_id: UUID,
    service: WaitlistService = Depends(get_waitlist_service),
    current_user: User = Depends(get_current_active_user)
):
    """Get all waitlist entries for a guest"""
    entries = await service.get_guest_waitlist(guest_id)
    return [_waitlist_to_response(e) for e in entries]

@app.get("/api/waitlist/room/{room_type_id}", response_model=List[WaitlistResponse], tags=["Waitlist"])
async def get_room_waitlist(
    room_type_id: str,
    service: WaitlistService = Depends(get_waitlist_service),
    current_user: User = Depends(get_current_active_user)
):
    """Get waitlist entries for a room type (sorted by priority)"""
    entries = await service.get_room_waitlist(room_type_id)
    return [_waitlist_to_response(e) for e in entries]

@app.get("/api/waitlist/{waitlist_id}", response_model=WaitlistResponse, tags=["Waitlist"])
async def get_waitlist_entry(
    waitlist_id: UUID,
    service: WaitlistService = Depends(get_waitlist_service),
    current_user: User = Depends(get_current_active_user)
):
    """Get waitlist entry by ID"""
    entry = await service.get_waitlist_entry(waitlist_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    return _waitlist_to_response(entry)

@app.post("/api/waitlist/{waitlist_id}/convert", response_model=WaitlistResponse, tags=["Waitlist"])
async def convert_waitlist_to_reservation(
    waitlist_id: UUID,
    request: ConvertWaitlistRequest,
    service: WaitlistService = Depends(get_waitlist_service),
    current_user: User = Depends(get_current_active_user)
):
    """Convert waitlist entry to reservation"""
    try:
        entry = await service.convert_to_reservation(waitlist_id, request.reservation_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Waitlist entry not found")
        return _waitlist_to_response(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/waitlist/{waitlist_id}/expire", response_model=WaitlistResponse, tags=["Waitlist"])
async def expire_waitlist_entry(
    waitlist_id: UUID,
    service: WaitlistService = Depends(get_waitlist_service),
    current_user: User = Depends(get_current_active_user)
):
    """Mark waitlist entry as expired"""
    try:
        entry = await service.expire_entry(waitlist_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Waitlist entry not found")
        return _waitlist_to_response(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/waitlist/{waitlist_id}/extend", response_model=WaitlistResponse, tags=["Waitlist"])
async def extend_waitlist_expiry(
    waitlist_id: UUID,
    request: ExtendWaitlistRequest,
    service: WaitlistService = Depends(get_waitlist_service),
    current_user: User = Depends(get_current_active_user)
):
    """Extend waitlist entry expiry date"""
    try:
        entry = await service.extend_expiry(waitlist_id, request.additional_days)
        if not entry:
            raise HTTPException(status_code=404, detail="Waitlist entry not found")
        return _waitlist_to_response(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/waitlist/{waitlist_id}/upgrade-priority", response_model=WaitlistResponse, tags=["Waitlist"])
async def upgrade_waitlist_priority(
    waitlist_id: UUID,
    request: UpgradePriorityRequest,
    service: WaitlistService = Depends(get_waitlist_service),
    current_user: User = Depends(get_current_active_user)
):
    """Upgrade waitlist entry priority"""
    try:
        priority = Priority(int(request.new_priority))
        entry = await service.upgrade_priority(waitlist_id, priority)
        if not entry:
            raise HTTPException(status_code=404, detail="Waitlist entry not found")
        return _waitlist_to_response(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/waitlist/{waitlist_id}/notify", response_model=WaitlistResponse, tags=["Waitlist"])
async def mark_waitlist_notified(
    waitlist_id: UUID,
    service: WaitlistService = Depends(get_waitlist_service),
    current_user: User = Depends(get_current_active_user)
):
    """Mark waitlist entry as notified"""
    try:
        entry = await service.mark_notified(waitlist_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Waitlist entry not found")
        return _waitlist_to_response(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/waitlist/notify/pending", response_model=List[WaitlistResponse], tags=["Waitlist"])
async def get_waitlist_entries_to_notify(
    service: WaitlistService = Depends(get_waitlist_service),
    current_user: User = Depends(get_current_active_user)
):
    """Get waitlist entries that need notification"""
    entries = await service.get_entries_to_notify()
    return [_waitlist_to_response(e) for e in entries]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _reservation_to_response(reservation) -> ReservationResponse:
    """Convert Reservation entity to ReservationResponse"""
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
        reservation_source=reservation.reservation_source.value,
        special_requests=[
            SpecialRequestResponse(
                request_id=sr.request_id,
                request_type=sr.request_type.value,
                description=sr.description,
                fulfilled=sr.fulfilled,
                notes=sr.notes,
                created_at=sr.created_at
            )
            for sr in reservation.special_requests
        ],
        created_at=reservation.created_at,
        modified_at=reservation.modified_at,
        created_by=reservation.created_by,
        version=reservation.version
    )

def _availability_to_response(availability) -> AvailabilityResponse:
    """Convert Availability entity to AvailabilityResponse"""
    return AvailabilityResponse(
        room_type_id=availability.room_type_id,
        availability_date=availability.availability_date,
        total_rooms=availability.total_rooms,
        reserved_rooms=availability.reserved_rooms,
        blocked_rooms=availability.blocked_rooms,
        available_rooms=availability.available_rooms,
        overbooking_threshold=availability.overbooking_threshold,
        last_updated=availability.last_updated,
        version=availability.version
    )

def _waitlist_to_response(entry) -> WaitlistResponse:
    """Convert WaitlistEntry entity to WaitlistResponse"""
    return WaitlistResponse(
        waitlist_id=entry.waitlist_id,
        guest_id=entry.guest_id,
        room_type_id=entry.room_type_id,
        check_in=entry.requested_dates.check_in,
        check_out=entry.requested_dates.check_out,
        adults=entry.guest_count.adults,
        children=entry.guest_count.children,
        priority=entry.priority.name,
        status=entry.status.value,
        created_at=entry.created_at,
        expires_at=entry.expires_at,
        notified_at=entry.notified_at,
        converted_reservation_id=entry.converted_reservation_id,
        priority_score=entry.calculate_priority_score()
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
