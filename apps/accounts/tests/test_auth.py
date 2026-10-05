"""Tests for authentication functionality."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

User = get_user_model()


@pytest.mark.django_db
class TestRegistration:

    def test_register_success(self, api_client):
        url = reverse('api_register')
        data = {
            'email': 'new@example.com',
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
            'first_name': 'New',
            'last_name': 'User',
            'phone_number': '+27123456780',
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email='new@example.com').exists()

    def test_register_password_mismatch(self, api_client):
        url = reverse('api_register')
        data = {
            'email': 'new@example.com',
            'password': 'StrongPass123!',
            'password_confirm': 'DifferentPass123!',
            'first_name': 'New',
            'last_name': 'User',
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_weak_password(self, api_client):
        url = reverse('api_register')
        data = {
            'email': 'new@example.com',
            'password': 'weak',
            'password_confirm': 'weak',
            'first_name': 'New',
            'last_name': 'User',
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_duplicate_email(self, api_client, regular_user):
        url = reverse('api_register')
        data = {
            'email': 'client@wethu.test',
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
            'first_name': 'Another',
            'last_name': 'User',
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestLogin:

    def test_login_success(self, api_client, regular_user):
        url = reverse('api_login')
        data = {'email': 'client@wethu.test', 'password': 'ClientPass123!'}
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_login_wrong_password(self, api_client, regular_user):
        url = reverse('api_login')
        data = {'email': 'client@wethu.test', 'password': 'WrongPass123!'}
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, api_client):
        url = reverse('api_login')
        data = {'email': 'nonexistent@example.com', 'password': 'SomePass123!'}
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_rate_limiting(self, api_client, regular_user):
        """After 3 failed attempts, the account is locked → HTTP 401."""
        url = reverse('api_login')

        for _ in range(3):
            response = api_client.post(url, {
                'email': 'client@wethu.test',
                'password': 'WrongPass123!',
            }, format='json')
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # 4th attempt — account is now locked
        response = api_client.post(url, {
            'email': 'client@wethu.test',
            'password': 'ClientPass123!',
        }, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert 'locked' in str(response.data).lower()

        regular_user.refresh_from_db()
        assert regular_user.is_locked
        assert regular_user.failed_login_attempts >= 3


@pytest.mark.django_db
class TestPasswordChange:

    def test_change_password_success(self, authenticated_client, regular_user):
        url = reverse('api_password_change')
        data = {
            'old_password': 'ClientPass123!',
            'new_password': 'NewClientPass123!',
            'new_password_confirm': 'NewClientPass123!',
        }
        response = authenticated_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        regular_user.refresh_from_db()
        assert regular_user.check_password('NewClientPass123!')

    def test_change_password_wrong_old(self, authenticated_client):
        url = reverse('api_password_change')
        data = {
            'old_password': 'WrongOldPass123!',
            'new_password': 'NewClientPass123!',
            'new_password_confirm': 'NewClientPass123!',
        }
        response = authenticated_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST