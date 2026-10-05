"""MFA enrollment, challenge, and recovery views."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.services import AuditService

from .mfa_service import MFAService

logger = logging.getLogger('apps.accounts')


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')


@login_required
def setup(request):
    """Enroll MFA: show QR + secret, then verify a code."""
    user = request.user

    if request.method == 'POST':
        code = request.POST.get('code', '')
        secret = request.session.get('mfa_setup_secret')
        if not secret:
            messages.error(request, 'Session expired. Please start again.')
            return redirect('mfa_setup')

        is_valid, counter = MFAService.verify_code(secret, code)
        if not is_valid:
            messages.error(
                request,
                'Invalid code. Make sure your authenticator app clock is accurate.',
            )
            return redirect('mfa_setup')

        user.mfa_secret = secret
        user.mfa_enabled = True
        user.mfa_enrolled_at = timezone.now()
        user.mfa_last_used_counter = counter
        user.save(update_fields=[
            'mfa_secret', 'mfa_enabled', 'mfa_enrolled_at',
            'mfa_last_used_counter', 'updated_at',
        ])

        codes = MFAService.generate_recovery_codes(user)
        request.session['mfa_verified'] = True
        request.session.pop('mfa_setup_secret', None)
        request.session['mfa_recovery_codes'] = codes

        AuditService.record(
            actor=user, action='mfa_enabled',
            object_type='user', object_id=str(user.id),
            ip_address=_client_ip(request),
        )
        return redirect('mfa_recovery_codes')

    # GET
    if user.mfa_enabled:
        return render(request, 'auth/mfa_setup.html', {'already_enabled': True})

    if not request.session.get('mfa_setup_secret'):
        request.session['mfa_setup_secret'] = MFAService.generate_secret()
    secret = request.session['mfa_setup_secret']

    return render(request, 'auth/mfa_setup.html', {
        'secret': secret,
        'provisioning_uri': MFAService.provisioning_uri(user, secret),
    })


@login_required
def challenge(request):
    """Post-password MFA challenge. Accepts TOTP or recovery code."""
    user = request.user

    if request.session.get('mfa_verified'):
        return redirect('home')
    if not MFAService.user_requires_mfa(user):
        request.session['mfa_verified'] = True
        return redirect('home')

    if request.method == 'POST':
        code = (request.POST.get('code', '') or '').strip()

        # Recovery code path (contains dashes)
        if '-' in code:
            if MFAService.verify_recovery_code(user, code):
                request.session['mfa_verified'] = True
                AuditService.record(
                    actor=user, action='mfa_recovery_code_used',
                    object_type='user', object_id=str(user.id),
                    ip_address=_client_ip(request),
                )
                messages.success(request, 'Recovery code accepted.')
                return redirect('home')
            messages.error(request, 'Invalid recovery code.')
            return redirect('mfa_challenge')

        # TOTP path
        is_valid, counter = MFAService.verify_code(
            user.mfa_secret, code, last_counter=user.mfa_last_used_counter,
        )
        if is_valid:
            user.mfa_last_used_at = timezone.now()
            user.mfa_last_used_counter = counter
            user.save(update_fields=[
                'mfa_last_used_at', 'mfa_last_used_counter', 'updated_at',
            ])
            request.session['mfa_verified'] = True
            AuditService.record(
                actor=user, action='mfa_verified',
                object_type='user', object_id=str(user.id),
                ip_address=_client_ip(request),
            )
            messages.success(request, 'MFA verified.')
            return redirect('home')

        AuditService.record(
            actor=user, action='mfa_failed',
            object_type='user', object_id=str(user.id),
            ip_address=_client_ip(request),
        )
        messages.error(request, 'Invalid code. Please try again.')
        return redirect('mfa_challenge')

    return render(request, 'auth/mfa_challenge.html')


@login_required
def recovery_codes(request):
    """Display recovery codes once, immediately after enrollment."""
    codes = request.session.pop('mfa_recovery_codes', None)
    if not codes:
        messages.info(
            request,
            'Recovery codes can only be viewed immediately after generation.',
        )
        return redirect('home')
    return render(request, 'auth/mfa_recovery_codes.html', {'codes': codes})


@login_required
@require_POST
def disable(request):
    """Disable MFA. Requires current password to confirm."""
    user = request.user
    password = request.POST.get('password', '')

    if not user.check_password(password):
        messages.error(request, 'Incorrect password.')
        return redirect('mfa_setup')

    user.mfa_enabled = False
    user.mfa_secret = ''
    user.mfa_enrolled_at = None
    user.mfa_last_used_counter = None
    user.save(update_fields=[
        'mfa_enabled', 'mfa_secret', 'mfa_enrolled_at',
        'mfa_last_used_counter', 'updated_at',
    ])

    from .models import MFARecoveryCode
    MFARecoveryCode.objects.filter(user=user).delete()
    request.session.pop('mfa_verified', None)

    AuditService.record(
        actor=user, action='mfa_disabled',
        object_type='user', object_id=str(user.id),
        ip_address=_client_ip(request),
    )
    messages.success(request, 'MFA has been disabled.')
    return redirect('home')