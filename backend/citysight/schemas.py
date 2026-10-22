"""Request validation schemas (Pydantic v2).

Unknown fields are rejected (``extra="forbid"``) so typos in the frontend
surface as 422 errors instead of being silently ignored.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import ClassVar, Literal, TypeVar

from flask import request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ApiError
from .timeutil import utcnow

T = TypeVar("T", bound=BaseModel)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(_In):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class CameraCreateIn(_In):
    name: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=255)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=9, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=9, decimal_places=6)
    stream_url: str = Field(min_length=1, max_length=2048)
    status: Literal["active", "inactive"] = "active"

    @model_validator(mode="after")
    def _coordinates_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude dan longitude harus diisi bersamaan atau dikosongkan bersamaan.")
        return self


class CameraUpdateIn(_In):
    """PUT accepts a partial update; at least one field is required."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=9, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=9, decimal_places=6)
    stream_url: str | None = Field(default=None, min_length=1, max_length=2048)
    status: Literal["active", "inactive"] | None = None

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.model_fields_set:
            raise ValueError("Minimal satu field harus diisi.")
        for field in ("name", "location", "stream_url", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} tidak boleh null.")
        if ("latitude" in self.model_fields_set) != ("longitude" in self.model_fields_set):
            raise ValueError("latitude dan longitude harus diubah bersamaan.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude dan longitude harus diisi bersamaan atau dikosongkan bersamaan.")
        return self


class Pagination(_In):
    page: int = Field(default=1, ge=1, le=100_000)
    per_page: int = Field(default=100, ge=1, le=500)


class TimeRange(_In):
    from_: AwareDatetime | None = Field(default=None, alias="from")
    to: AwareDatetime | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    max_span: ClassVar[timedelta] = timedelta(days=31)
    default_span: ClassVar[timedelta] = timedelta(hours=24)

    @field_validator("from_", "to", mode="before")
    @classmethod
    def _restore_plus(cls, value):
        # An unencoded "+07:00" offset arrives as " 07:00" in a query string.
        if isinstance(value, str):
            return value.replace(" ", "+")
        return value

    @model_validator(mode="after")
    def _resolve(self):
        end = self.to or utcnow()
        start = self.from_ or (end - self.default_span)
        if start >= end:
            raise ValueError("'from' harus lebih awal dari 'to'.")
        if end - start > self.max_span:
            raise ValueError(f"Rentang waktu maksimal {self.max_span.days} hari.")
        self.from_, self.to = start, end
        return self


class DetectionQuery(TimeRange, Pagination):
    order: Literal["asc", "desc"] = "desc"
    default_span: ClassVar[timedelta] = timedelta(hours=1)


class HourlyQuery(TimeRange):
    pass


class DailyQuery(_In):
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("from_", "to", mode="before")
    @classmethod
    def _date_only(cls, value):
        if isinstance(value, str) and len(value) != 10:
            raise ValueError("Gunakan format tanggal YYYY-MM-DD.")
        return value

    @model_validator(mode="after")
    def _check(self):
        if self.from_ and self.to and self.from_ > self.to:
            raise ValueError("'from' tidak boleh setelah 'to'.")
        if self.from_ and self.to and (self.to - self.from_).days > 366:
            raise ValueError("Rentang tanggal maksimal 366 hari.")
        return self


class CameraListQuery(_In):
    status: Literal["active", "inactive"] | None = None


def parse_body(schema: type[T]) -> T:
    if not request.is_json:
        raise ApiError("Content-Type harus application/json.", status=415, code="unsupported_media_type")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Body JSON tidak valid.", code="invalid_json")
    return schema.model_validate(data)


def parse_query(schema: type[T], ignore: tuple[str, ...] = ()) -> T:
    multi = request.args.to_dict(flat=False)
    if any(len(values) > 1 for values in multi.values()):
        raise ApiError("Parameter query tidak boleh diulang.", status=422, code="duplicate_query_param")
    args = {key: values[0] for key, values in multi.items() if key not in ignore}
    return schema.model_validate(args)
