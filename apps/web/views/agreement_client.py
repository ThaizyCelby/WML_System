"""Client agreement acceptance UI."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.loans.agreement_service import LoanAgreementService
from apps.loans.models import Loan, LoanApplication
from apps.loans.services import LoanApplicationService


@login_required
def view_agreement(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, client=request.user)
    agreement = getattr(loan, 'agreement', None)
    if not agreement:
        raise Http404
    return render(request, 'client/loans/agreement.html', {'loan': loan, 'agreement': agreement})


@login_required
def download_agreement(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, client=request.user)
    agreement = getattr(loan, 'agreement', None)
    if not agreement:
        raise Http404
    try:
        file_obj = default_storage.open(agreement.pdf_storage_key, 'rb')
    except FileNotFoundError:
        raise Http404
    response = FileResponse(file_obj, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="wethu-loan-agreement-{loan.id}.pdf"'
    return response


@login_required
def accept_agreement(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, client=request.user)
    if request.method != 'POST':
        return redirect('client_loan_agreement', loan_id=loan.id)

    if not request.POST.get('i_accept'):
        messages.error(request, 'Please confirm you have read and understood the agreement.')
        return redirect('client_loan_agreement', loan_id=loan.id)

    LoanAgreementService.accept_agreement(
        loan.agreement, request.user,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )
    # Move application to contract_accepted
    try:
        LoanApplicationService.transition(
            loan.application, 'contract_accepted', request.user,
            'Agreement accepted by client', request.META.get('REMOTE_ADDR'),
        )
    except Exception:
        pass

    messages.success(request, 'Thank you. Your acceptance has been recorded.')
    return redirect('client_loan_detail', loan_id=loan.id)