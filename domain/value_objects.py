"""Domain Value Objects"""
from pydantic import BaseModel, Field, validator
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from typing import Optional
from domain.enums import RequestType


class DateRange(BaseModel):
    """Value Object for date ranges"""
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
    """Value Object for monetary amounts"""
    amount: Decimal = Field(gt=0)
    currency: str = "IDR"

    class Config:
        frozen = True


class GuestCount(BaseModel):
    """Value Object for guest count"""
    adults: int = Field(ge=1, le=10)
    children: int = Field(ge=0, le=10)

    class Config:
        frozen = True


class CancellationPolicy(BaseModel):
    """Value Object for cancellation policy"""
    policy_name: str
    refund_percentage: Decimal = Field(ge=0, le=100)
    deadline_hours: int = Field(ge=0)

    class Config:
        frozen = True


class SpecialRequest(BaseModel):
    """Child Entity for special requests"""
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
