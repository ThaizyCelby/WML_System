"""Data masking utilities for sensitive information."""
import re


def mask_email(email: str) -> str:
    """Mask an email address for display.

    Example: john.doe@example.com -> j***@example.com
    """
    if not email or '@' not in email:
        return '***'
    local, domain = email.split('@', 1)
    if len(local) <= 1:
        masked_local = '*'
    else:
        masked_local = local[0] + '*' * (len(local) - 1)
    return f"{masked_local}@{domain}"


def mask_phone(phone: str) -> str:
    """Mask a phone number for display.

    Example: +27123456789 -> +27*****6789
    """
    if not phone:
        return '***'
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 7:
        return '***'
    return phone[:3] + '*****' + phone[-4:]


def mask_id_number(id_number: str) -> str:
    """Mask a South African ID number.

    Example: 9001011234087 -> 900101*****87
    """
    if not id_number or len(id_number) < 8:
        return '***'
    return id_number[:6] + '*****' + id_number[-2:]


def mask_ip_address(ip: str) -> str:
    """Mask part of an IP address for display.

    Example: 192.168.1.100 -> 192.168.*.*
    """
    if not ip:
        return '***'
    parts = ip.split('.')
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.*.*"
    # IPv6 - mask everything after first two groups
    return ip.split(':')[0] + ':****'
