"""Client-side debit-order mandate views."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.payments.mandate_service import MandateService
from apps.payments.models import DebitInstruction
from apps.loans.models import Loan


SOUTH_AFRICAN_BANKS = [
    'Capitec', 'ABSA', 'FNB', 'Nedbank', 'Standard Bank',
    'TymeBank', 'Discovery Bank', 'African Bank', 'Investec',
    'Bidvest Bank', 'Bank Zero',
]


@login_required
def mandate_list(request):
    mandates = (
        DebitInstruction.objects
        .filter(loan__client=request.user)
        .select_related('loan')
        .order_by('-created_at')
    )
    return render(request, 'client/mandates/list.html', {'mandates': mandates})


@login_required
def mandate_create(request, loan_id):
    """Client captures banking details and creates a new mandate."""
    loan = get_object_or_404(Loan, id=loan_id, client=request.user)
    application = loan.application

    try:
        from apps.accounts.bank_account_service import BankAccountService

        # 1. Persist the bank account as a structured record
        account, _created = BankAccountService.add_account(
            client=request.user,
            bank_name=request.POST['bank_name'],
            account_holder_name=request.POST['account_holder_name'],
            account_number=request.POST['account_number'],
            account_type=request.POST.get('account_type', 'cheque'),
            branch_code=request.POST.get('branch_code', ''),
            source='mandate_created',
            actor=request.user,
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        # 2. Create the mandate as before
        instruction = MandateService.create_mandate(
            loan=loan,
            account_holder_name=request.POST['account_holder_name'],
            account_number=request.POST['account_number'],
            bank_name=request.POST['bank_name'],
            branch_code=request.POST.get('branch_code', ''),
            account_type=request.POST.get('account_type', 'cheque'),
            signed_by=request.user,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        # 3. Link them
        BankAccountService.link_to_mandate(account, instruction)

        messages.success(request, 'Banking details saved. Please sign the mandate.')
        return redirect('client_mandate_sign', mandate_id=instruction.id)
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.exception('Mandate creation failed: %s', e)
        messages.error(request, f'Could not save banking details: {e}')


    # Gate 1a: contract must be accepted
    if application.status != 'contract_accepted':
        messages.error(
            request,
            'You must accept the loan agreement before setting up a debit order.',
        )
        return redirect('client_loan_detail', loan_id=loan.id)

    # Gate 1b: admin must have verified the contract
    if not application.contract_verified_by_admin:
        messages.info(
            request,
            'Your signed agreement is being reviewed. You will be notified when '
            'you can set up your debit order.',
        )
        return redirect('client_loan_detail', loan_id=loan.id)

    # Gate 2: admin must have reviewed documents + transactions
    if not application.documents_reviewed:
        messages.info(
            request,
            'Your documents are still being reviewed. Please wait for approval.',
        )
        return redirect('client_loan_detail', loan_id=loan.id)

    if not application.transactions_reviewed:
        messages.info(
            request,
            'Your bank statement transactions are still being reviewed. '
            'Please wait for approval.',
        )
        return redirect('client_loan_detail', loan_id=loan.id)

    # Existing mandate guard
    existing = loan.debit_instructions.filter(
        status__in=['pending_client', 'pending_review', 'active'],
    ).first()
    if existing:
        messages.info(request, 'A mandate already exists for this loan.')
        return redirect('client_mandate_detail', mandate_id=existing.id)

    if request.method == 'POST':
        try:
            instruction = MandateService.create_mandate(
                loan=loan,
                account_holder_name=request.POST['account_holder_name'],
                account_number=request.POST['account_number'],
                bank_name=request.POST['bank_name'],
                branch_code=request.POST.get('branch_code', ''),
                account_type=request.POST.get('account_type', 'cheque'),
                signed_by=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            messages.success(request, 'Banking details saved. Please sign the mandate.')
            return redirect('client_mandate_sign', mandate_id=instruction.id)
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Could not save banking details: {e}')

    return render(request, 'client/mandates/create.html', {
        'loan': loan,
        'banks': SOUTH_AFRICAN_BANKS,
    })


@login_required
def mandate_sign(request, mandate_id):
    instruction = get_object_or_404(
        DebitInstruction, id=mandate_id, loan__client=request.user,
    )

    if instruction.status not in ('pending_client', 'draft'):
        messages.info(request, 'This mandate has already been signed.')
        return redirect('client_mandate_detail', mandate_id=instruction.id)

    if request.method == 'POST':
        if not request.POST.get('i_agree'):
            messages.error(request, 'Please confirm you agree to the mandate.')
        else:
            try:
                MandateService.sign_mandate(
                    instruction, request.user,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                )
                messages.success(request, 'Mandate signed. We will review it shortly.')
                return redirect('client_mandate_detail', mandate_id=instruction.id)
            except ValueError as e:
                messages.error(request, str(e))

    return render(request, 'client/mandates/sign.html', {'mandate': instruction})


@login_required
def mandate_detail(request, mandate_id):
    instruction = get_object_or_404(
        DebitInstruction, id=mandate_id, loan__client=request.user,
    )
    return render(request, 'client/mandates/detail.html', {'mandate': instruction})


@login_required
def mandate_download(request, mandate_id):
    instruction = get_object_or_404(
        DebitInstruction, id=mandate_id, loan__client=request.user,
    )
    if not instruction.mandate_pdf_storage_key:
        raise Http404
    try:
        file_obj = default_storage.open(instruction.mandate_pdf_storage_key, 'rb')
    except FileNotFoundError:
        raise Http404
    response = FileResponse(file_obj, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="mandate-{instruction.mandate_reference_number or instruction.id}.pdf"'
    )
    return response