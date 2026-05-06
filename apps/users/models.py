from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from core.models import TimeStampedModel
from core.utils.id_generator import next_yearly_id


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        STAFF = "staff", "Staff"
        CUSTOMER = "customer", "Customer"

    public_id = models.CharField(max_length=32, unique=True, blank=True, db_index=True)
    sequence_number = models.PositiveIntegerField(default=0, editable=False)
    sequence_year = models.PositiveIntegerField(default=0, editable=False)

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True)

    def save(self, *args, **kwargs):
        if self.public_id:
            return super().save(*args, **kwargs)

        for _ in range(5):
            yearly = next_yearly_id(User, prefix="UID")
            self.public_id = yearly.public_id
            self.sequence_number = yearly.sequence_number
            self.sequence_year = yearly.sequence_year
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.public_id = ""
                self.sequence_number = 0
                self.sequence_year = 0
                continue
        raise RuntimeError("Failed to generate a unique user public_id after multiple attempts.")


class RefreshToken(TimeStampedModel):
    """
    DB-backed refresh tokens (rotate/revoke support).
    """

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="refresh_tokens")
    jti = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["expires_at", "revoked_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user_id} {self.jti}"

    @property
    def is_active(self) -> bool:
        if self.revoked_at:
            return False
        return self.expires_at >= timezone.now()


class LoginActivity(TimeStampedModel):
    class Event(models.TextChoices):
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        TOKEN_REFRESH = "token_refresh", "Token refresh"

    user = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="login_events")
    event = models.CharField(max_length=30, choices=Event.choices, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["event", "created_at"]),
        ]
        ordering = ["-created_at"]
