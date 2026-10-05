"""Frontend forms for accounts."""
import re
from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class _BootstrapMixin:
    """Add Tailwind classes to all widget fields."""
    default_classes = (
        'w-full rounded-lg border border-slate-300 dark:border-slate-700 '
        'bg-white dark:bg-slate-950 px-3 py-2 text-sm '
        'focus:border-brand-500 focus:ring-2 focus:ring-brand-200 dark:focus:ring-brand-900'
    )
    checkbox_classes = 'rounded border-slate-300 text-brand-700 focus:ring-brand-500'

    def _apply_styles(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = self.checkbox_classes
            elif isinstance(widget, (forms.Select,)):
                widget.attrs['class'] = self.default_classes
            else:
                widget.attrs.setdefault('class', self.default_classes)


class LoginForm(_BootstrapMixin, forms.Form):
    email = forms.EmailField(label='Email')
    password = forms.CharField(label='Password', widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styles()


class RegisterForm(_BootstrapMixin, forms.ModelForm):
    password = forms.CharField(label='Password', widget=forms.PasswordInput, min_length=12)
    password_confirm = forms.CharField(label='Confirm password', widget=forms.PasswordInput)
    agree_terms = forms.BooleanField(
        label='I agree to the Terms & Conditions and Privacy Policy',
        required=True,
    )
    consent_credit_check = forms.BooleanField(
        label='I consent to a credit and affordability assessment',
        required=True,
    )

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone_number']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styles()

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean_password(self):
        pw = self.cleaned_data['password']
        if len(pw) < 12:
            raise forms.ValidationError('Password must be at least 12 characters.')
        if not re.search(r'[A-Z]', pw):
            raise forms.ValidationError('Password must contain an uppercase letter.')
        if not re.search(r'[a-z]', pw):
            raise forms.ValidationError('Password must contain a lowercase letter.')
        if not re.search(r'\d', pw):
            raise forms.ValidationError('Password must contain a number.')
        if not re.search(r'[^A-Za-z0-9]', pw):
            raise forms.ValidationError('Password must contain a special character.')
        return pw

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') != cleaned.get('password_confirm'):
            self.add_error('password_confirm', 'Passwords do not match.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class PasswordChangeFormWeb(_BootstrapMixin, forms.Form):
    old_password = forms.CharField(label='Current password', widget=forms.PasswordInput)
    new_password = forms.CharField(label='New password', widget=forms.PasswordInput, min_length=12)
    new_password_confirm = forms.CharField(label='Confirm new password', widget=forms.PasswordInput)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self._apply_styles()

    def clean_old_password(self):
        pw = self.cleaned_data['old_password']
        if not self.user.check_password(pw):
            raise forms.ValidationError('Current password is incorrect.')
        return pw

    def clean(self):
        cleaned = super().clean()
        new = cleaned.get('new_password')
        if new and cleaned.get('new_password_confirm') != new:
            self.add_error('new_password_confirm', 'Passwords do not match.')
        return cleaned

    def save(self):
        self.user.set_password(self.cleaned_data['new_password'])
        self.user.save(update_fields=['password', 'updated_at'])
        return self.user
