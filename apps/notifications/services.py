"""Notification service — full implementation with GLM-ready templates."""
import logging

from django.utils import timezone

from .channels import CHANNELS
from .models import Notification, NotificationTemplate

logger = logging.getLogger('apps.notifications')


# ----------------------------------------------------------------------
# Default notification templates
#
# Format: code -> { channel -> (subject, body) }
# Placeholders use Python str.format() syntax and are filled from the
# `context` dict passed to NotificationService.dispatch().
# ----------------------------------------------------------------------
DEFAULT_TEMPLATES = {
    'account_created': {
        'email': (
            'Welcome to Wethu Micro Lenders',
            'Hi {name}, welcome to Wethu Micro Lenders. '
            'Verify your email to get started.',
        ),
        'in_app': (
            'Welcome to Wethu',
            'Welcome! Complete your profile to apply for a loan.',
        ),
    },
    'application_submitted': {
        'email': (
            'Application Received',
            'Hi {name}, we received application {application_id}. '
            'We will review it within 24 hours.',
        ),
        'in_app': (
            'Application Received',
            'We received your loan application.',
        ),
    },
    'application_approved': {
        'email': (
            'Application Approved',
            'Hi {name}, application {application_id} is approved for {amount}. '
            'Please sign your agreement to proceed.',
        ),
        'in_app': (
            'Application Approved',
            'Your application was approved.',
        ),
    },
    'payment_received': {
        'email': (
            'Payment Received',
            'We received your payment of {amount} on loan {loan_id}.',
        ),
        'in_app': (
            'Payment Received',
            'Payment of {amount} received.',
        ),
    },
    'payment_due': {
        'email': (
            'Payment Due Soon',
            'A payment of {amount} is due on {due_date}.',
        ),
        'in_app': (
            'Payment Due',
            'Payment of {amount} due {due_date}.',
        ),
    },
    'payment_overdue': {
        'email': (
            'Payment Overdue',
            'Your payment of {amount} was due on {due_date}. '
            'Please arrange payment to avoid further action.',
        ),
        'in_app': (
            'Payment Overdue',
            'Overdue payment of {amount}.',
        ),
    },

    # ── NEW: Debit decline templates ────────────────────────────────
    'payment_failed': {
        'email': (
            'Your debit order could not be processed',
            'Hi {name},\n\n'
            'Our attempt to collect {amount} on {failure_date} for loan '
            '{loan_id} was declined by your bank.\n\n'
            'Reason: {decline_reason}\n\n'
            'We will automatically retry on {retry_date}. Please make sure '
            'your account has sufficient funds before then, or contact us '
            'if you have already made payment.\n\n'
            'If your bank details have changed, please update your debit '
            'mandate in the portal.\n\n'
            'Wethu Micro Lenders',
        ),
        'in_app': (
            'Debit order declined',
            'R {amount} for loan {loan_id} was declined. We will retry on '
            '{retry_date}. Reason: {decline_reason}',
        ),
    },
    'payment_retry_failed': {
        'email': (
            'Second debit attempt declined',
            'Hi {name},\n\n'
            'We attempted again to collect {amount} for loan {loan_id}, '
            'but the payment was declined a second time.\n\n'
            'Reason: {decline_reason}\n\n'
            'Your instalment is now overdue. Please arrange payment within '
            'the next 48 hours, or contact us to discuss a payment plan.\n\n'
            'If you believe this is an error, reply to this message and '
            'quote reference {loan_id}.\n\n'
            'Wethu Micro Lenders',
        ),
        'in_app': (
            'Payment still declined',
            'Retry for R {amount} on loan {loan_id} was declined. Please '
            'contact support.',
        ),
    },
    # ────────────────────────────────────────────────────────────────

    'mandate_setup_required': {
        'email': (
            'Set up your debit order',
            'Hi {name}, your loan agreement is signed. '
            'Please set up and sign your debit order mandate for loan {loan_id} '
            'so we can activate your repayments.',
        ),
        'in_app': (
            'Set up your debit order',
            'Please sign your debit order mandate to enable automatic repayments.',
        ),
    },

    'mandate_approved': {
        'email': (
            'Debit order activated',
            'Hi {name}, your debit order for loan {loan_id} has been activated. '
            'Repayments will be collected on the scheduled dates.',
        ),
        'in_app': (
            'Debit order activated',
            'Your debit order for loan {loan_id} is now active.',
        ),
    },
    'mandate_rejected': {
        'email': (
            'Debit order could not be activated',
            'Hi {name}, your debit order for loan {loan_id} could not be activated. '
            'Reason: {reason}. Please re-submit your banking details.',
        ),
        'in_app': (
            'Debit order not activated',
            'Your debit order for loan {loan_id} was not activated.',
        ),
    },
    'document_approved': {
        'email': (
            'Document approved',
            'Hi {name}, your {document_type} has been approved by our review team.',
        ),
        'in_app': (
            'Document approved',
            'Your {document_type} was approved.',
        ),
    },
    'document_rejected': {
        'email': (
            'Document needs attention',
            'Hi {name}, your {document_type} was rejected: {notes}. '
            'Please re-upload a clearer copy.',
        ),
        'in_app': (
            'Document rejected',
            'Your {document_type} was rejected.',
        ),
    },
    'document_replacement_approved': {
        'email': (
            'Correction approved',
            'Hi {name}, you may now replace your {document_type}. '
            'Please upload the corrected version.',
        ),
        'in_app': (
            'Correction approved',
            'You may now replace your {document_type}.',
        ),
    },
    'document_replacement_rejected': {
        'email': (
            'Correction not approved',
            'Hi {name}, your request to replace {document_type} was not approved. '
            '{notes}',
        ),
        'in_app': (
            'Correction not approved',
            'Replacement request was not approved.',
        ),
    },
    'security_alert': {
        # Sent to staff / developer. Do NOT include client financial data.
        'email': (
            'Security Alert - {severity_upper}',
            'Severity: {severity}\n'
            'Event: {event_type}\n'
            'User: {user_masked}\n'
            'IP: {ip_address}\n'
            'Risk Score: {risk_score}/100\n'
            'Action Taken: {action_taken}\n'
            'Time: {timestamp}\n'
            'Event ID: {event_id}\n'
            '\n{ai_explanation}',
        ),
    },

    'portfolio_summary': {
        'email': (
            'Weekly portfolio summary',
            '{body}',
        ),
        'in_app': (
            'Weekly portfolio summary',
            'Weekly summary for {week_of} is ready.',
        ),
    },

    'ticket_created': {
        'email': (
            'New support ticket: {subject}',
            'New ticket from {client_email}.\n'
            'Priority: {priority}\n'
            'Subject: {subject}\n'
            'Ticket: {ticket_id}',
        ),
    },
    'ticket_replied': {
        'email': (
            'New reply on ticket: {subject}',
            'A reply was posted on ticket {ticket_id}.\n'
            'Subject: {subject}\n'
            '{preview}',
        ),
        'in_app': (
            'New reply on your ticket',
            'A staff member replied to "{subject}".',
        ),
    },
    'ticket_resolved': {
        'email': (
            'Ticket resolved: {subject}',
            'Your ticket "{subject}" has been resolved.',
        ),
        'in_app': (
            'Ticket resolved',
            'Your ticket "{subject}" has been resolved.',
        ),
    },
    'ticket_closed': {
        'email': (
            'Ticket closed: {subject}',
            'Your ticket "{subject}" has been closed.',
        ),
        'in_app': (
            'Ticket closed',
            'Your ticket "{subject}" has been closed.',
        ),
    },
}


class NotificationService:
    """Central notification dispatcher."""

    @staticmethod
    def ensure_default_templates():
        """Idempotently seed DEFAULT_TEMPLATES into the database."""
        for code, channels in DEFAULT_TEMPLATES.items():
            for channel, (subj, body) in channels.items():
                NotificationTemplate.objects.get_or_create(
                    code=code, channel=channel,
                    defaults={'subject': subj, 'body': body},
                )

    @staticmethod
    def dispatch(user, code, context=None, channels=None):
        """
        Send a notification to a user across one or more channels.

        channels: list of channel keys, or None to use user preferences.
        """
        context = context or {}
        context.setdefault('name', getattr(user, 'full_name', '') or user.email)

        if channels is None:
            prefs = getattr(user, 'notification_preferences', None)
            channels = []
            if not prefs or prefs.email_enabled:
                channels.append('email')
            if not prefs or prefs.in_app_enabled:
                channels.append('in_app')
            if prefs and prefs.sms_enabled:
                channels.append('sms')

        results = []
        for channel in channels:
            template = NotificationTemplate.objects.filter(
                code=code, channel=channel, is_active=True,
            ).first()
            if not template:
                logger.debug("No template %s/%s", code, channel)
                continue

            rendered = template.render(context)
            notification = Notification.objects.create(
                user=user, code=code, channel=channel,
                title=rendered['subject'] or code,
                message=rendered['body'],
                metadata=context,
                status='pending',
            )

            channel_impl = CHANNELS.get(channel)
            if not channel_impl:
                notification.status = 'failed'
                notification.error_message = f'Unknown channel: {channel}'
                notification.save(update_fields=['status', 'error_message'])
                results.append(notification)
                continue

            ok = channel_impl.send(notification)
            notification.status = 'sent' if ok else 'failed'
            notification.sent_at = timezone.now() if ok else None
            notification.save(update_fields=[
                'status', 'sent_at', 'error_message', 'updated_at',
            ])
            results.append(notification)

        return results

    # ------------------------------------------------------------------
    # Backward-compatible shims used by earlier phases
    # ------------------------------------------------------------------
    @staticmethod
    def send_security_alert(event):
        """
        Dispatch a security alert email to every configured recipient.

        Builds the full context the security_alert template requires.
        Never raises — a failed alert must not crash the caller.
        """
        from django.conf import settings
        from django.contrib.auth import get_user_model
        from django.utils import timezone as _tz

        recipients = getattr(settings, 'SECURITY_ALERT_RECIPIENTS', []) or []

        # Build a complete context once, then reuse per recipient.
        user_obj = getattr(event, 'user', None)
        if user_obj and getattr(user_obj, 'email', None):
            email = user_obj.email
            local, _, domain = email.partition('@')
            masked = f"{local[:2]}***@{domain}" if domain else f"{local[:2]}***"
        else:
            masked = 'anonymous'

        severity = getattr(event, 'severity', 'unknown')
        context = {
            'severity': severity,
            'severity_upper': str(severity).upper(),
            'event_type': getattr(event, 'event_type', 'unknown'),
            'user_masked': masked,
            'ip_address': getattr(event, 'ip_address', '') or '—',
            'risk_score': getattr(event, 'risk_score', 0),
            'action_taken': getattr(event, 'action_taken', 'none'),
            'timestamp': _tz.now().strftime('%Y-%m-%d %H:%M:%S %Z'),
            'event_id': str(getattr(event, 'id', '—')),
            'ai_explanation': getattr(event, 'ai_explanation', '') or '',
        }

        sent = []
        if not recipients:
            logger.warning(
                "Security alert raised but SECURITY_ALERT_RECIPIENTS is empty: %s",
                context['event_type'],
            )
            return sent

        User = get_user_model()
        for email in recipients:
            user = User.objects.filter(email=email, is_active=True).first()
            if not user:
                logger.warning("Security alert recipient not found: %s", email)
                continue
            try:
                sent.extend(NotificationService.dispatch(
                    user, 'security_alert',
                    context=dict(context),  # copy so dispatch can mutate
                    channels=['email'],
                ))
            except Exception:
                logger.exception(
                    "Failed to send security alert to %s", email,
                )
        return sent

    @staticmethod
    def send_email(*, to, subject, body, **kwargs):
        logger.info("Direct email -> %s: %s", to, subject)
        return True

    @staticmethod
    def send_sms(*, to, message, **kwargs):
        logger.info("Direct SMS -> %s: %s", to, message[:40])
        return True

    @staticmethod
    def send_in_app(*, user, title, message, **kwargs):
        Notification.objects.create(
            user=user, code='manual', channel='in_app',
            title=title, message=message, status='sent', sent_at=timezone.now(),
        )
        return True