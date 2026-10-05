"""URL configuration for accounts app."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views
from .dashboard import dashboard

router = DefaultRouter()
router.register(r'profile', views.UserProfileViewSet, basename='user-profile')

urlpatterns = [
    # API endpoint names are prefixed with 'api_' to avoid clashing with
    # the frontend URL names in apps/web/urls.py (which are 'login',
    # 'register', 'password_change', etc.).
    path('dashboard/', dashboard, name='api_dashboard'),
    path('register/', views.RegisterView.as_view(), name='api_register'),
    path('login/', views.LoginView.as_view(), name='api_login'),
    path('refresh/', views.RefreshTokenView.as_view(), name='api_token_refresh'),
    path('logout/', views.LogoutView.as_view(), name='api_logout'),
    path('password/change/', views.PasswordChangeView.as_view(), name='api_password_change'),
    path('password/reset/', views.PasswordResetRequestView.as_view(), name='api_password_reset_request'),
    path('password/reset/confirm/', views.PasswordResetConfirmView.as_view(), name='api_password_reset_confirm'),
]

urlpatterns += router.urls