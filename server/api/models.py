"""Request contracts. Public models never accept administrative fields."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo
import re

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

CONSENT_VERSION = '2026-09-20-v1'
PHONE = re.compile(r'1[3-9][0-9]{9}')
QQ = re.compile(r'[1-9][0-9]{4,14}')
Rating = Annotated[StrictInt, Field(ge=1, le=5)]
Hours = Annotated[Decimal, Field(ge=0, le=5, decimal_places=2, allow_inf_nan=False)]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    @field_validator('*', mode='before')
    @classmethod
    def reject_controls(cls, value):
        if isinstance(value, str) and any(ord(c) < 32 and c not in '\n\r\t' for c in value):
            raise ValueError('请移除不可见控制字符。')
        return value


class Submission(Model):
    consent: StrictBool
    consentVersion: str = Field(min_length=1, max_length=40)
    website: str = Field(default='', max_length=200)  # Honeypot, never persisted.

    @model_validator(mode='after')
    def confirmed(self):
        if not self.consent:
            raise ValueError('请阅读并确认信息使用说明。')
        if self.website:
            raise ValueError('无法接收本次提交。')
        return self


class Booking(Submission):
    name: str = Field(min_length=1, max_length=40)
    gradeMajor: str = Field(min_length=1, max_length=100)
    phone: str = Field(default='', max_length=11)
    qq: str = Field(default='', max_length=15)
    email: str = Field(default='', max_length=254)
    device: str = Field(min_length=1, max_length=120)
    os: str = Field(min_length=1, max_length=100)
    issue: str = Field(min_length=5, max_length=4000)
    preferredContactTime: str = Field(default='', max_length=200)

    @model_validator(mode='after')
    def contacts(self):
        if not self.phone and not self.qq:
            raise ValueError('手机和 QQ 请至少填写一个。')
        if self.phone and not PHONE.fullmatch(self.phone):
            raise ValueError('请填写有效的大陆手机号码。')
        if self.qq and not QQ.fullmatch(self.qq):
            raise ValueError('QQ 号应为 5–15 位数字。')
        if self.email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', self.email):
            raise ValueError('请检查邮箱格式。')
        return self


class Feedback(Submission):
    nameMajor: str = Field(min_length=1, max_length=100)
    contactType: Literal['qq', 'phone']
    contact: str = Field(min_length=5, max_length=15)
    bookingReference: str = Field(default='', max_length=64)
    serviceTypes: list[Literal['repair', 'purchase_advice']] = Field(min_length=1, max_length=2)
    summary: str = Field(min_length=1, max_length=2000)
    volunteerNames: str = Field(min_length=1, max_length=200)
    reportedHours: Annotated[Decimal, Field(gt=0, le=5, decimal_places=2, allow_inf_nan=False)]
    requestedOn: date
    attitudeRating: Rating
    skillRating: Rating
    overallRating: Rating
    comment: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def validate_feedback(self):
        if not (QQ if self.contactType == 'qq' else PHONE).fullmatch(self.contact):
            raise ValueError('请检查联系方式格式。')
        if self.requestedOn > datetime.now(ZoneInfo('Asia/Shanghai')).date():
            raise ValueError('预约或咨询日期不能晚于今天。')
        self.serviceTypes = sorted(set(self.serviceTypes))
        return self


class UpdateRecord(Model):
    version: Annotated[StrictInt, Field(ge=1)]
    status: str = Field(min_length=1, max_length=30)
    notes: str = Field(default='', max_length=4000)
    reason: str = Field(default='', max_length=500)
    confirmedHours: Hours | None = None
    bookingId: str | None = Field(default=None, max_length=36)


class ServiceSettings(Model):
    version: Annotated[StrictInt, Field(ge=1)]
    acceptingBookings: StrictBool
    acceptingFeedback: StrictBool
    closedMessage: str = Field(min_length=1, max_length=300)
