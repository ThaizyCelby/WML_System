"""Public marketing pages for Wethu Micro Lenders."""
from django.contrib import messages
from django.shortcuts import render


def home(request):
    return render(request, 'public/home.html')


def about(request):
    return render(request, 'public/about.html')


def how_it_works(request):
    steps = [
        {'title': 'Apply online', 'body': 'Complete a short application with your income, expenses, and basic personal information.'},
        {'title': 'Upload documents', 'body': 'Upload your ID, proof of address, payslip, and bank statement. Everything is encrypted.'},
        {'title': 'Verification and affordability', 'body': 'We verify documents, analyse your bank statement, and assess affordability â€” always deterministically.'},
        {'title': 'Get your decision', 'body': "You'll receive a transparent offer with the exact interest, fees, and repayment amount."},
        {'title': 'Sign and receive funds', 'body': 'Sign electronically. Repayments are collected by debit order on agreed dates.'},
    ]
    return render(request, 'public/how_it_works.html', {'steps': steps})


def products(request):
    from apps.loans.models import LoanProduct
    products = LoanProduct.objects.filter(is_active=True).order_by('name')
    return render(request, 'public/products.html', {'products': products})


def affordability(request):
    return render(request, 'public/affordability.html')


def faq(request):
    faqs = [
        {'question': 'How much can I borrow?', 'answer': 'Between R1,000 and R150,000 depending on the product and your verified affordability.'},
        {'question': 'How long does approval take?', 'answer': 'Most decisions are made within 24 hours of receiving all required documents.'},
        {'question': 'What documents do I need?', 'answer': 'A valid South African ID or passport, proof of address, latest payslip, and 3 months of bank statements.'},
        {'question': 'What interest rate do you charge?', 'answer': 'Interest is shown on your offer. We follow NCA-prescribed disclosure and never charge hidden fees.'},
        {'question': 'How are repayments collected?', 'answer': 'Via debit order on the agreed repayment dates, with reminders before each collection.'},
        {'question': 'How is my data protected?', 'answer': 'Your data is encrypted, access is role-controlled, and we operate in line with POPIA. You can request access or deletion at any time.'},
        {'question': 'Do you use AI to make decisions?', 'answer': 'AI assists our analysis, but affordability and credit decisions follow deterministic rules and human review.'},
    ]
    return render(request, 'public/faq.html', {'faqs': faqs})


def contact(request):
    if request.method == 'POST':
        messages.success(request, 'Thanks â€” we received your message and will reply shortly.')
    return render(request, 'public/contact.html')


def security(request):
    return render(request, 'public/security.html')


def privacy(request):
    return render(request, 'public/privacy.html')


def terms(request):
    return render(request, 'public/terms.html')


def responsible_lending(request):
    return render(request, 'public/responsible_lending.html')


def accessibility(request):
    return render(request, 'public/accessibility.html')
