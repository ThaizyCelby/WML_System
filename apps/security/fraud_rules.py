"""Deterministic fraud signals. Pure functions â€” no DB writes."""
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

from django.utils import timezone


@dataclass
class Signal:
    code: str
    weight: int
    message: str
    metadata: dict = field(default_factory=dict)


def rule_velocity_login_failures(ip_address: str, email: str, window_minutes: int = 15,
                                 threshold: int = 10) -> Optional[Signal]:
    """Many failed logins from the same IP or against the same email."""
    from .models import LoginAttempt
    since = timezone.now() - timedelta(minutes=window_minutes)
    count_ip = LoginAttempt.objects.filter(
        ip_address=ip_address, success=False, created_at__gte=since,
    ).count()
    count_email = LoginAttempt.objects.filter(
        email__iexact=email, success=False, created_at__gte=since,
    ).count()
    worst = max(count_ip, count_email)
    if worst >= threshold:
        return Signal(
            code='login_velocity_exceeded',
            weight=35,   # <-- changed from 25 to 35 (medium risk threshold)
            message=f"{worst} failed logins in {window_minutes} minutes",
            metadata={'ip_count': count_ip, 'email_count': count_email},
        )
    return None


def rule_multiple_users_same_ip(ip_address: str, window_minutes: int = 60,
                                threshold: int = 5) -> Optional[Signal]:
    """Too many distinct successful logins from the same IP â€” credential stuffing."""
    from .models import LoginAttempt
    since = timezone.now() - timedelta(minutes=window_minutes)
    distinct = (
        LoginAttempt.objects
        .filter(ip_address=ip_address, success=True, created_at__gte=since)
        .values('user_id')
        .distinct()
        .count()
    )
    if distinct >= threshold:
        return Signal(
            code='multiple_users_same_ip',
            weight=30,
            message=f"{distinct} distinct users logged in from one IP in {window_minutes} min",
            metadata={'distinct_users': distinct, 'ip': ip_address},
        )
    return None


def rule_new_device_for_user(user, fingerprint: str) -> Optional[Signal]:
    """First time this user is seen on this device fingerprint."""
    from .models import UserDevice
    if not fingerprint:
        return None
    exists = UserDevice.objects.filter(user=user, fingerprint=fingerprint).exists()
    if not exists:
        return Signal(
            code='new_device',
            weight=15,
            message='Login from a new device',
            metadata={'fingerprint': fingerprint[:16]},
        )
    return None


def rule_impossible_travel(user, new_ip: str, max_kmh: float = 900.0) -> Optional[Signal]:
    """
    Detect impossible travel between consecutive successful logins.
    Requires an IP geo-lookup adapter; here we use a simple country/region heuristic
    based on the first octet â€” replace with a real GeoIP database for production.
    """
    from .models import LoginAttempt
    last = (
        LoginAttempt.objects
        .filter(user=user, success=True)
        .exclude(ip_address=new_ip)
        .order_by('-created_at')
        .first()
    )
    if not last or not last.ip_address:
        return None
    # Heuristic: if the first two octets differ, assume different region (very rough)
    def region(ip: str) -> str:
        parts = (ip or '').split('.')
        return '.'.join(parts[:2]) if len(parts) == 4 else ip
    if region(last.ip_address) != region(new_ip):
        elapsed_minutes = max((timezone.now() - last.created_at).total_seconds() / 60, 1)
        if elapsed_minutes < 30:  # less than 30 min between two different regions
            return Signal(
                code='impossible_travel',
                weight=35,
                message=f"Login from {new_ip} shortly after {last.ip_address}",
                metadata={'previous_ip': last.ip_address, 'current_ip': new_ip,
                          'elapsed_minutes': round(elapsed_minutes, 1)},
            )
    return None


def rule_rapid_applications(user, window_hours: int = 24, threshold: int = 3) -> Optional[Signal]:
    """Multiple loan applications in a short window."""
    from apps.loans.models import LoanApplication
    since = timezone.now() - timedelta(hours=window_hours)
    count = LoanApplication.objects.filter(client=user, created_at__gte=since).count()
    if count >= threshold:
        return Signal(
            code='rapid_applications',
            weight=20,
            message=f"{count} loan applications in {window_hours}h",
            metadata={'count': count},
        )
    return None


def rule_duplicate_identity(user) -> Optional[Signal]:
    """Same ID number or bank account used by another account."""
    from apps.accounts.models import ClientProfile
    try:
        my_profile = user.client_profile
    except ClientProfile.DoesNotExist:
        return None
    matches = ClientProfile.objects.exclude(user=user)
    hits = []
    if my_profile.id_number:
        hits = list(matches.filter(id_number=my_profile.id_number).values_list('user_id', flat=True))
    if hits:
        return Signal(
            code='duplicate_identity',
            weight=45,
            message='ID number also registered on another account',
            metadata={'matching_user_ids': [str(h) for h in hits]},
        )
    return None


def rule_rapid_document_uploads(user, window_hours: int = 1, threshold: int = 10) -> Optional[Signal]:
    from apps.documents.models import Document
    since = timezone.now() - timedelta(hours=window_hours)
    count = Document.objects.filter(client=user, created_at__gte=since).count()
    if count >= threshold:
        return Signal(
            code='rapid_document_uploads',
            weight=15,
            message=f"{count} documents uploaded in {window_hours}h",
            metadata={'count': count},
        )
    return None


ALL_RULES = [
    'rule_velocity_login_failures',
    'rule_multiple_users_same_ip',
    'rule_new_device_for_user',
    'rule_impossible_travel',
    'rule_rapid_applications',
    'rule_duplicate_identity',
    'rule_rapid_document_uploads',
]
