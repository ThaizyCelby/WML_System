"""Project-level views."""
from django.shortcuts import redirect


def home_redirect(request):
    """Redirect the root URL to the API documentation."""
    return redirect('swagger-ui')
