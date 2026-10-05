"""Client loan application views."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.affordability.engine import AffordabilityEngine
from apps.loans.interest_engine import calculate_total_repayment
from apps.loans.models import LoanProduct
from apps.loans.services import LoanApplicationService


@login_required
def apply_start(request):
    from apps.kyc.services import get_missing_documents

    missing = get_missing_documents(request.user)
    products = LoanProduct.objects.filter(is_active=True).order_by('name')

    return render(request, 'client/loans/apply.html', {
        'products': products,
        'missing_documents': missing,
        'can_apply': not missing,
    })


@login_required
def apply_preview(request):
    """HTMX endpoint: preview repayment + affordability."""
    if request.method != 'POST':
        return redirect('client_loan_apply')

    product_id = request.POST.get('product_id')
    amount_raw = (request.POST.get('amount') or '').strip()
    term_raw = (request.POST.get('term') or '').strip()

    if not product_id or not amount_raw or not term_raw:
        return render(request, 'client/loans/_apply_preview.html', {
            'error': 'Please select a product, amount, and term.',
        })

    try:
        amount = Decimal(amount_raw)
        term = int(term_raw)
    except (InvalidOperation, ValueError):
        return render(request, 'client/loans/_apply_preview.html', {
            'error': 'Please enter a valid amount and term.',
        })

    product = get_object_or_404(LoanProduct, id=product_id, is_active=True)
    repayment = calculate_total_repayment(
        amount, product.interest_rate, term, product.interest_type,
    )

    try:
        profile = request.user.client_profile
        gross = profile.monthly_income
        expenses = profile.monthly_expenses
        debts = profile.existing_debt_obligations
    except Exception:
        gross = expenses = debts = Decimal('0')

    installment = (
        repayment['total_repayment'] / Decimal(term)
    ).quantize(Decimal('0.01')) if term else Decimal('0')
    affordability = AffordabilityEngine.calculate(gross, expenses, debts, installment)

    return render(request, 'client/loans/_apply_preview.html', {
        'product': product,
        'amount': amount,
        'term': term,
        'repayment': repayment,
        'installment': installment,
        'affordability': affordability,
    })


@login_required
def apply_submit(request):
    if request.method != 'POST':
        return redirect('client_loan_apply')

    from apps.kyc.services import get_missing_documents

    missing = get_missing_documents(request.user)
    if missing:
        names = ', '.join(m['label'] for m in missing)
        messages.error(
            request,
            f'Please upload the following documents before submitting: {names}.',
        )
        return redirect('client_loan_apply')

    try:
        product_id = request.POST['product_id']
        amount = Decimal(request.POST['amount'])
        term = int(request.POST['term'])
        payday_raw = (request.POST.get('client_payday') or '').strip()

        application = LoanApplicationService.create_application(
            client=request.user,
            product_id=product_id,
            amount=amount,
            term=term,
        )

        if payday_raw:
            try:
                payday = int(payday_raw)
                if 1 <= payday <= 31:
                    application.client_payday = payday
                    application.save(update_fields=['client_payday', 'updated_at'])
            except ValueError:
                pass

        LoanApplicationService.submit_application(
            application, request.user, request.META.get('REMOTE_ADDR'),
        )
        messages.success(request, 'Application submitted. We will review it shortly.')
        return redirect('client_loan_list')
    except Exception as e:
        messages.error(request, f'Could not submit application: {e}')
        return redirect('client_loan_apply')