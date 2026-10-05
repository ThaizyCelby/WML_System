"""
Organisation context helpers.

Two ways to access the current organisation:

  get_org_for_user(user)   — explicit, from a User instance.
  get_current_org()        — implicit, from the middleware thread-local.

The thread-local is set on every request by OrganisationMiddleware.
Services and background tasks should always prefer the explicit form
(get_org_for_user) when a user is in scope — it's easier to test and
never silently picks up the wrong tenant.
"""
import threading

_thread_local = threading.local()


# ──────────────────────────────────────────────────────────────────────
# Middleware-managed thread-local
# ──────────────────────────────────────────────────────────────────────
def set_current_org(org) -> None:
    """Called by OrganisationMiddleware on each request."""
    _thread_local.organisation = org


def get_current_org():
    """
    Return the organisation for the current request, or None.

    Returns None when called outside a request (e.g. from a management
    command, Celery task, or test without middleware).
    """
    return getattr(_thread_local, 'organisation', None)


def clear_current_org() -> None:
    _thread_local.organisation = None


# ──────────────────────────────────────────────────────────────────────
# Explicit lookup
# ──────────────────────────────────────────────────────────────────────
class OrganisationService:

    @staticmethod
    def get_org_for_user(user):
        """Return the user's organisation, or None if unset/anonymous."""
        if not user:
            return None
        if not getattr(user, 'is_authenticated', False):
            return None
        return getattr(user, 'organisation', None)

    @staticmethod
    def require_org(user):
        """Return the user's organisation or raise ValueError."""
        org = OrganisationService.get_org_for_user(user)
        if not org:
            raise ValueError(
                'User has no organisation assigned. '
                'Assign one before performing tenant-scoped operations.'
            )
        return org

    @staticmethod
    def is_superuser_without_org(user) -> bool:
        """
        A platform superuser who can see across all tenants.

        Rule: superuser with no organisation set → global access.
              superuser with an organisation set → scoped to that org.
        """
        return (
            user
            and getattr(user, 'is_authenticated', False)
            and getattr(user, 'is_superuser', False)
            and getattr(user, 'organisation', None) is None
        )