from django.urls import path

from . import views_mfa

urlpatterns = [
    path('setup/', views_mfa.setup, name='mfa_setup'),
    path('challenge/', views_mfa.challenge, name='mfa_challenge'),
    path('recovery-codes/', views_mfa.recovery_codes, name='mfa_recovery_codes'),
    path('disable/', views_mfa.disable, name='mfa_disable'),
]