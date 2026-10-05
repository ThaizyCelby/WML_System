"""Client bank statement views."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.banking.models import BankStatement, BankTransaction
from apps.banking.services import BankStatementService
from apps.documents.models import Document


@login_required
def list_statements(request):
    statements = BankStatement.objects.filter(client=request.user).order_by('-created_at')
    return render(request, 'client/banking/list.html', {'statements': statements})


@login_required
def upload_statement(request):
    """Upload the PDF via Django form, create a Document, then a BankStatement."""
    from apps.documents.services import DocumentService

    if request.method == 'POST':
        file_obj = request.FILES.get('file')
        bank_name = request.POST.get('bank_name', '').strip()

        if not file_obj:
            messages.error(request, 'Please select a PDF file.')
            return redirect('client_bank_upload')

        if not file_obj.name.lower().endswith('.pdf'):
            messages.error(request, 'Please upload a PDF file.')
            return redirect('client_bank_upload')

        try:
            doc = DocumentService.upload_document(
                client=request.user,
                file_obj=file_obj,
                document_type='bank_statement',
                uploaded_by=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except Exception as e:
            messages.error(request, f'Upload failed: {e}')
            return redirect('client_bank_upload')

        statement = BankStatement.objects.create(
            client=request.user,
            document=doc,
            bank_name=bank_name or 'Unknown',
            processing_status='pending',
        )
        BankStatementService.process_statement(statement)
        messages.success(request, 'Bank statement uploaded and processed.')
        return redirect('client_bank_detail', statement_id=statement.id)

    return render(request, 'client/banking/upload.html')

@login_required
def detail(request, statement_id):
    statement = get_object_or_404(BankStatement, id=statement_id, client=request.user)
    transactions = statement.transactions.order_by('-transaction_date')

    # Summary figures — deterministic, computed from stored transactions
    credit_total = sum(t.amount for t in transactions if t.transaction_type == 'credit')
    debit_total = sum(t.amount for t in transactions if t.transaction_type == 'debit')

    return render(request, 'client/banking/detail.html', {
        'statement': statement,
        'transactions': transactions,
        'credit_total': credit_total,
        'debit_total': debit_total,
        'transaction_count': transactions.count(),
    })


@login_required
def analyze(request, statement_id):
    """HTMX endpoint: trigger AI analysis and return the results partial."""
    statement = get_object_or_404(BankStatement, id=statement_id, client=request.user)
    if request.method != 'POST':
        return redirect('client_bank_detail', statement_id=statement.id)

    if statement.processing_status != 'completed':
        messages.warning(request, 'Statement not yet fully processed.')
        return redirect('client_bank_detail', statement_id=statement.id)

    payday, debt = BankStatementService.analyze_with_ai(statement)
    return render(request, 'client/banking/_analysis.html', {
        'statement': statement,
        'payday': payday,
        'debt': debt,
    })


@login_required
def statement_spending(request, statement_id):
    """Client-facing spending analysis page."""
    statement = get_object_or_404(
        BankStatement, id=statement_id, client=request.user,
    )
    summary = BankStatementService.summarize_spending(statement)
    return render(request, 'client/banking/spending.html', {
        'statement': statement,
        'summary': summary,
    })