"""Vendor-scoped staff views."""
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render

from apps.loans.models import Loan, LoanApplication
from apps.vendors.models import Vendor, VendorUser
from apps.vendors.tenancy import user_vendor_ids


def _first_vendor(user):
    """Return the vendor the user belongs to (or None)."""
    ids = user_vendor_ids(user)
    if ids is None or not ids:
        return None
    return Vendor.objects.filter(id__in=ids, is_active=True).first()


@login_required
def vendor_dashboard(request):
    vendor = _first_vendor(request.user)
    if not vendor:
        messages.error(request, 'You do not have access to a vendor portal.')
        return redirect('portal_dashboard')

    loans = Loan.objects.filter(vendor=vendor)
    apps = LoanApplication.objects.filter(vendor=vendor)

    context = {
        'vendor': vendor,
        'loans_active': loans.filter(status='active').count(),
        'loans_overdue': loans.filter(status='overdue').count(),
        'outstanding': loans.aggregate(s=Sum('outstanding_balance'))['s'] or Decimal('0'),
        'apps_in_review': apps.filter(status__in=[
            'submitted', 'document_review', 'kyc_review',
            'affordability_review', 'credit_review',
        ]).count(),
        'recent_apps': apps.select_related('client', 'product').order_by('-created_at')[:10],
    }
    return render(request, 'vendor/dashboard.html', context)