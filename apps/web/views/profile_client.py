"""Client profile view — capture personal, employment, address, and consent records."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.models import ClientProfile, User
from apps.notifications.models import NotificationPreference


CONSENT_VERSION = '1.0'

CONSENT_FIELDS = {
    'consent_credit_check': 'credit_check_consent',
    'consent_terms': 'terms_accepted',
    'consent_privacy': 'privacy_accepted',
    'consent_affordability': 'affordability_consent',
}


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _parse_decimal(value, default=Decimal('0.00')):
    if value in (None, '', '0'):
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _normalize_phone(raw, default_cc='27'):
    """
    Return a canonical E.164-style phone number.

        0728672014      -> +27728672014
        27728672014     -> +27728672014
        +27728672014    -> +27728672014
        '  072 867 2014' -> +27728672014
        ''              -> ''
    """
    if not raw:
        return ''
    digits = re.sub(r'\D', '', str(raw))
    if not digits:
        return ''
    if digits.startswith('0'):
        digits = default_cc + digits[1:]
    elif not digits.startswith(default_cc):
        digits = default_cc + digits
    return f'+{digits}'


def _record_consents(profile, request):
    """
    Merge the four mandatory consents into profile.consent_records.

    Each consent entry stores:
        granted: bool
        timestamp: ISO timestamp (UTC)
        ip: source IP
        user_agent: request UA (truncated)
        version: consent text version at time of capture

    Only updates an entry if the granted flag actually changes — this preserves
    the original consent timestamp as immutable evidence (POPIA / NCA audit trail).
    """
    consents = dict(profile.consent_records or {})
    now = timezone.now().isoformat()
    ip = request.META.get('REMOTE_ADDR', '')
    ua = (request.META.get('HTTP_USER_AGENT', '') or '')[:300]

    for form_field, code in CONSENT_FIELDS.items():
        granted = form_field in request.POST
        existing = consents.get(code) or {}
        if existing.get('granted') == granted and existing.get('version') == CONSENT_VERSION:
            continue  # no change, preserve original evidence
        consents[code] = {
            'granted': granted,
            'timestamp': now,
            'ip': ip,
            'user_agent': ua,
            'version': CONSENT_VERSION,
        }

    profile.consent_records = consents


def _render_form(request, client_profile, prefs):
    return render(request, 'client/profile.html', {
        'client_profile': client_profile,
        'prefs': prefs,
        'consent_records': client_profile.consent_records or {},
    })


# ──────────────────────────────────────────────────────────────
# View
# ──────────────────────────────────────────────────────────────

@login_required
def profile(request):
    """
    Display and update the client's profile.

    Server-side authorisation: only the authenticated user's own profile can be
    read or modified. The queryset is scoped to request.user and is never
    derived from user input.
    """
    client_profile, _ = ClientProfile.objects.get_or_create(user=request.user)
    prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method != 'POST':
        return _render_form(request, client_profile, prefs)

    user = request.user

    # ── Read all fields up-front (so we can re-render on error) ──
    first_name = (request.POST.get('first_name') or '').strip()[:150]
    last_name = (request.POST.get('last_name') or '').strip()[:150]
    raw_phone = (request.POST.get('phone_number') or '').strip()
    phone = _normalize_phone(raw_phone)

    id_number = (request.POST.get('id_number') or '').strip()[:20]
    dob_raw = (request.POST.get('date_of_birth') or '').strip()
    employment = (request.POST.get('employment_type') or '').strip()
    employer_name = (request.POST.get('employer_name') or '').strip()[:200]

    # Residential address (stored as a structured JSON on the profile)
    address_street = (request.POST.get('address_street') or '').strip()[:200]
    address_city = (request.POST.get('address_city') or '').strip()[:100]
    address_province = (request.POST.get('address_province') or '').strip()[:100]
    address_postal_code = (request.POST.get('address_postal_code') or '').strip()[:20]

    # ── Pre-flight validation ────────────────────────────────
    errors = []

    if not first_name:
        errors.append('First name is required.')
    if not last_name:
        errors.append('Last name is required.')

    if raw_phone and not phone:
        errors.append('Phone number is not valid.')

    # Phone uniqueness: exclude the current user.
    if phone and User.objects.exclude(pk=user.pk).filter(phone_number=phone).exists():
        errors.append('That phone number is already registered to another account.')

    # id_number uniqueness
    if id_number:
        conflict = (
            ClientProfile.objects
            .exclude(pk=client_profile.pk)
            .filter(id_number=id_number)
            .exists()
        )
        if conflict:
            errors.append('That ID number is already registered.')

    if errors:
        for msg in errors:
            messages.error(request, msg)
        return _render_form(request, client_profile, prefs)

    # ── Persist inside a single transaction ──────────────────
    try:
        with transaction.atomic():
            # User (personal info)
            user.first_name = first_name
            user.last_name = last_name
            if phone:
                user.phone_number = phone
            user.save(update_fields=[
                'first_name', 'last_name', 'phone_number', 'updated_at',
            ])

            # ClientProfile (KYC / affordability)
            client_profile.id_number = id_number

            if dob_raw:
                try:
                    client_profile.date_of_birth = date.fromisoformat(dob_raw)
                except ValueError:
                    pass  # invalid date -> leave unchanged

            # Only overwrite employment_type if a value was submitted (empty
            # means "leave as-is"); this avoids the field being blanked when
            # the client only updates their income on a subsequent save.
            if employment:
                client_profile.employment_type = employment[:50]

            client_profile.employer_name = employer_name
            client_profile.monthly_income = _parse_decimal(
                request.POST.get('monthly_income')
            )
            client_profile.monthly_expenses = _parse_decimal(
                request.POST.get('monthly_expenses')
            )
            client_profile.existing_debt_obligations = _parse_decimal(
                request.POST.get('existing_debt_obligations')
            )

            # Residential address (structured)
            # Only overwrite if at least one field was provided — this avoids
            # wiping a previously valid address when the form is partially
            # submitted.
            if address_street or address_city or address_province or address_postal_code:
                client_profile.residential_address = {
                    'street': address_street,
                    'city': address_city,
                    'province': address_province,
                    'postal_code': address_postal_code,
                }

            _record_consents(client_profile, request)
            client_profile.save()

            # Notification preferences
            prefs.email_enabled = 'email_enabled' in request.POST
            prefs.sms_enabled = 'sms_enabled' in request.POST
            prefs.in_app_enabled = 'in_app_enabled' in request.POST
            prefs.marketing_opt_in = 'marketing_opt_in' in request.POST
            prefs.save()

    except IntegrityError as exc:
        # Race-condition safety net: another request may have claimed
        # the same phone/id_number in the milliseconds since our check.
        err = str(exc).lower()
        if 'phone_number' in err:
            messages.error(
                request,
                'That phone number was just registered by another account. '
                'Please try a different number.',
            )
        elif 'id_number' in err:
            messages.error(
                request,
                'That ID number was just registered. Please try again.',
            )
        else:
            messages.error(request, 'Could not save your profile. Please try again.')
        return _render_form(request, client_profile, prefs)

    messages.success(request, 'Profile updated.')
    return redirect('client_profile')