"""Check whether a client's profile is complete enough to apply for a loan."""
from decimal import Decimal


REQUIRED_FIELDS = [
    # (path, label)
    ('user.first_name', 'First name'),
    ('user.last_name', 'Last name'),
    ('user.email', 'Email'),
    ('user.phone_number', 'Mobile number'),
    ('profile.id_number', 'ID number'),
    ('profile.date_of_birth', 'Date of birth'),
    ('profile.employment_type', 'Employment type'),
    ('profile.monthly_income', 'Monthly income'),
    ('profile.monthly_expenses', 'Monthly expenses'),
]

REQUIRED_ADDRESS = True  # residential_address must have street + city
REQUIRED_CONSENTS = [
    'credit_check_consent',   # consent to pull credit bureau
    'terms_accepted',         # T&Cs
    'privacy_accepted',       # POPIA privacy notice
    'affordability_consent',  # NCA affordability assessment
]


def _get(obj, path: str):
    for part in path.split('.'):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def get_profile_gaps(user) -> list[dict]:
    """
    Return a list of {code, label} for items missing from the profile.
    """
    gaps = []

    # Basic required fields
    try:
        profile = user.client_profile
    except Exception:
        profile = None

    for path, label in REQUIRED_FIELDS:
        # profile is separate from user
        obj = user
        if path.startswith('profile.'):
            obj = profile
            if obj is None:
                gaps.append({'code': path, 'label': label})
                continue
            attr = path.split('.', 1)[1]
            value = getattr(obj, attr, None)
        else:
            attr = path.split('.', 1)[1] if '.' in path else path
            value = getattr(obj, attr, None) if obj is not None else None

        if value in (None, '', 0, Decimal('0')):
            gaps.append({'code': path, 'label': label})

    # Address
    if REQUIRED_ADDRESS and profile is not None:
        addr = profile.residential_address or {}
        if not addr.get('street') or not addr.get('city'):
            gaps.append({'code': 'profile.residential_address', 'label': 'Residential address'})

    # Consents (stored on profile.consent_records)
    if profile is not None:
        consents = profile.consent_records or {}
        for code in REQUIRED_CONSENTS:
            entry = consents.get(code) or {}
            if not entry.get('granted'):
                label = {
                    'credit_check_consent': 'Consent to a credit bureau check',
                    'terms_accepted': 'Terms & Conditions accepted',
                    'privacy_accepted': 'Privacy notice accepted',
                    'affordability_consent': 'Affordability assessment consent',
                }[code]
                gaps.append({'code': f'consent.{code}', 'label': label})

    return gaps


def is_profile_complete(user) -> bool:
    return not get_profile_gaps(user)