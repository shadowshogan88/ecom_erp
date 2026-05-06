from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone


@dataclass(frozen=True)
class MonthlyId:
    public_id: str
    sequence_number: int
    sequence_year: int
    sequence_month: int


@dataclass(frozen=True)
class YearlyId:
    public_id: str
    sequence_number: int
    sequence_year: int


def _month_key_date():
    # Use local date so the month/year match the business timezone.
    return timezone.localdate()


def build_monthly_public_id(prefix: str, sequence_number: int, *, month: int, year: int) -> str:
    return f"{prefix}-{sequence_number}/{month:02d}-{year % 100:02d}"


def build_yearly_public_id(prefix: str, sequence_number: int, *, year: int) -> str:
    return f"{prefix}-{sequence_number:07d}/{year % 100:02d}"


def next_monthly_id(model_cls, *, prefix: str) -> MonthlyId:
    today = _month_key_date()
    year = today.year
    month = today.month
    manager = getattr(model_cls, "all_objects", model_cls.objects)
    max_seq = (
        manager.filter(sequence_year=year, sequence_month=month).aggregate(Max("sequence_number"))[
            "sequence_number__max"
        ]
        or 0
    )
    next_seq = max_seq + 1
    return MonthlyId(
        public_id=build_monthly_public_id(prefix, next_seq, month=month, year=year),
        sequence_number=next_seq,
        sequence_year=year,
        sequence_month=month,
    )


def next_yearly_id(model_cls, *, prefix: str) -> YearlyId:
    today = _month_key_date()
    year = today.year
    manager = getattr(model_cls, "all_objects", model_cls.objects)
    max_seq = manager.filter(sequence_year=year).aggregate(Max("sequence_number"))["sequence_number__max"] or 0
    next_seq = max_seq + 1
    return YearlyId(
        public_id=build_yearly_public_id(prefix, next_seq, year=year),
        sequence_number=next_seq,
        sequence_year=year,
    )


def assign_monthly_id_and_save(instance, *, prefix: str, id_field: str = "public_id") -> None:
    """
    Assigns a monthly-reset public id like: ORD-1/04-26.

    Requires instance fields:
      - public_id (or id_field)
      - sequence_number (int)
      - sequence_year (int)
      - sequence_month (int)

    Concurrency note (SQLite):
      We rely on a UNIQUE constraint on `public_id` and retry on IntegrityError.
    """

    if getattr(instance, id_field):
        instance.save()
        return

    model_cls = instance.__class__
    for _ in range(5):
        monthly = next_monthly_id(model_cls, prefix=prefix)
        setattr(instance, id_field, monthly.public_id)
        instance.sequence_number = monthly.sequence_number
        instance.sequence_year = monthly.sequence_year
        instance.sequence_month = monthly.sequence_month
        try:
            with transaction.atomic():
                instance.save()
                return
        except IntegrityError:
            setattr(instance, id_field, "")
            instance.sequence_number = 0
            instance.sequence_year = 0
            instance.sequence_month = 0
            continue
    raise RuntimeError(f"Failed to generate unique {id_field} after multiple attempts.")


def assign_yearly_id_and_save(instance, *, prefix: str, id_field: str = "public_id") -> None:
    """
    Assigns a yearly-reset public id like: UID-0000001/26.

    Requires instance fields:
      - public_id (or id_field)
      - sequence_number (int)
      - sequence_year (int)
    """

    if getattr(instance, id_field):
        instance.save()
        return

    model_cls = instance.__class__
    for _ in range(5):
        yearly = next_yearly_id(model_cls, prefix=prefix)
        setattr(instance, id_field, yearly.public_id)
        instance.sequence_number = yearly.sequence_number
        instance.sequence_year = yearly.sequence_year
        try:
            with transaction.atomic():
                instance.save()
                return
        except IntegrityError:
            setattr(instance, id_field, "")
            instance.sequence_number = 0
            instance.sequence_year = 0
            continue
    raise RuntimeError(f"Failed to generate unique {id_field} after multiple attempts.")
