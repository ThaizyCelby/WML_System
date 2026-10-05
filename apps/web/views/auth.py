"""Web authentication views for Wethu Micro Lenders."""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from apps.accounts.forms import LoginForm, PasswordChangeFormWeb, RegisterForm
from apps.security.risk_engine import FraudEngine, record_login_attempt


# ──────────────────────────────────────────────────────────────────────
# Role detection
# ──────────────────────────────────────────────────────────────────────
STAFF_ROLES = (
    'Administrator',
    'Credit Officer',
    'Finance Officer',
    'Collections Officer',
    'Compliance Officer',
    'Auditor',
)


def _is_staff(user) -> bool:
    """Determine whether a user should land on the staff portal."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return any(user.has_role(r) for r in STAFF_ROLES)


def _post_login_redirect(user) -> str:
    """Where to send a user after successful login (when no ?next= given)."""
    return '/staff/' if _is_staff(user) else '/portal/'


# ──────────────────────────────────────────────────────────────────────
# Login / logout
# ──────────────────────────────────────────────────────────────────────
@never_cache
@csrf_protect
def login_view(request):
    # Already signed in — send to the right home
    if request.user.is_authenticated:
        return redirect(_post_login_redirect(request.user))

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        password = form.cleaned_data['password']
        user = authenticate(request, username=email, password=password)

        ip = request.META.get('REMOTE_ADDR')
        ua = request.META.get('HTTP_USER_AGENT', '')

        if user is not None and user.is_active:
            login(request, user)
            record_login_attempt(user, email, ip, ua, success=True)
            try:
                FraudEngine.evaluate(
                    user=user, email=email, ip_address=ip,
                    user_agent=ua, context='login',
                )
            except Exception:
                pass

            # Respect ?next= if present and safe; otherwise route by role
            next_url = request.GET.get('next') or request.POST.get('next')
            if not next_url or not next_url.startswith('/'):
                next_url = _post_login_redirect(user)
            return redirect(next_url)

        # Failed login
        record_login_attempt(
            user, email, ip, ua, success=False, reason='invalid_credentials',
        )
        try:
            FraudEngine.evaluate(
                user=None, email=email, ip_address=ip,
                user_agent=ua, context='login',
            )
        except Exception:
            pass
        form.add_error(None, 'Incorrect email or password.')

    return render(request, 'auth/login.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('home')


# ──────────────────────────────────────────────────────────────────────
# Registration
# ──────────────────────────────────────────────────────────────────────
@never_cache
@csrf_protect
def register_view(request):
    if request.user.is_authenticated:
        return redirect(_post_login_redirect(request.user))

    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Account created. Please sign in.')
        return redirect('login')
    return render(request, 'auth/register.html', {'form': form})


# ──────────────────────────────────────────────────────────────────────
# Password change
# ──────────────────────────────────────────────────────────────────────
@login_required
@csrf_protect
def password_change_view(request):
    form = PasswordChangeFormWeb(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, 'Password updated.')
        return redirect('client_profile')
    return render(request, 'auth/password_change.html', {'form': form})