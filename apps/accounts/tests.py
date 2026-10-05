import pytest
from django.contrib.auth import get_user_model

@pytest.mark.django_db
def test_user_password_is_hashed():
    User = get_user_model()
    user = User.objects.create_user(username="a@example.com", email="a@example.com", password="VeryStrongPassword123!")
    assert user.password != "VeryStrongPassword123!"
    assert user.check_password("VeryStrongPassword123!")
