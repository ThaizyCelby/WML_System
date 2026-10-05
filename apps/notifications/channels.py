"""Notification channels (email, SMS, in-app)."""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

logger = logging.getLogger('apps.notifications')


EMAIL_HTML_WRAPPER = """\
<!doctype html>
<html><body style="font-family:Inter,Arial,sans-serif;background:#f8fafc;padding:24px;margin:0">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;padding:24px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px">
      <strong style="color:#0e2c5c;font-size:16px">Wethu Micro Lenders</strong>
    </div>
    <h1 style="font-size:18px;color:#0e2c5c;margin:0 0 12px 0">{title}</h1>
    <div style="color:#334155;font-size:14px;line-height:1.6;white-space:pre-wrap">{body}</div>
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0">
    <p style="color:#94a3b8;font-size:11px;margin:0">
      This is an automated message. Do not reply directly to this email.
    </p>
  </div>
</body></html>
"""


class BaseChannel:
    key = 'base'

    def send(self, notification) -> bool:
        raise NotImplementedError


class EmailChannel(BaseChannel):
    key = 'email'

    def send(self, notification) -> bool:
        try:
            from_email = getattr(
                settings, 'DEFAULT_FROM_EMAIL', 'noreply@wethumicrolenders.co.za',
            )
            subject = notification.title
            text_body = notification.message
            html_body = EMAIL_HTML_WRAPPER.format(
                title=escape(subject),
                body=escape(text_body),
            )

            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=from_email,
                to=[notification.user.email],
            )
            msg.attach_alternative(html_body, 'text/html')
            msg.send(fail_silently=False)
            return True
        except Exception as e:
            logger.exception("Email send failed: %s", e)
            notification.error_message = str(e)[:500]
            return False


class SMSChannel(BaseChannel):
    key = 'sms'

    def send(self, notification) -> bool:
        phone = getattr(notification.user, 'phone_number', None)
        if not phone:
            notification.error_message = 'No phone number on file'
            return False
        logger.info("SMS (stub) -> %s: %s", phone, notification.message[:40])
        return True


class InAppChannel(BaseChannel):
    key = 'in_app'

    def send(self, notification) -> bool:
        return True


CHANNELS = {c.key: c() for c in (EmailChannel, SMSChannel, InAppChannel)}