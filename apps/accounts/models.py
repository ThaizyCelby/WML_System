"""Accounts models: User, Role, Permission, UserRole, RolePermission, ClientProfile."""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.fields import EncryptedTextField, EncryptedJSONField
from core.mixins.soft_delete_mixin import SoftDeleteModel
from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class Organisation(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    A tenant on the Wethu platform.

    Every business record belongs to exactly one organisation. Cross-tenant
    access is prevented by middleware + queryset scoping.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('trial', 'Trial'),
        ('suspended', 'Suspended'),
        ('inactive', 'Inactive'),
    ]

    name = models.CharField(max_length=200, unique=True, db_index=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)

    legal_name = models.CharField(max_length=255, blank=True)
    registration_number = models.CharField(max_length=50, blank=True)
    tax_number = models.CharField(max_length=50, blank=True)
    ncr_number = models.CharField(
        max_length=50, blank=True,
        help_text='National Credit Regulator registration number.',
    )

    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    address = models.JSONField(default=dict, blank=True)

    logo_storage_key = models.CharField(max_length=500, blank=True)
    primary_color = models.CharField(max_length=7, blank=True, default='#0f172a')

    plan = models.CharField(max_length=50, blank=True, default='standard')
    subscription_starts_at = models.DateField(null=True, blank=True)
    subscription_ends_at = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='active', db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)

    settings = models.JSONField(
        default=dict, blank=True,
        help_text='Arbitrary per-organisation config (feature flags, limits, etc).',
    )

    class Meta:
        db_table = 'organisations'
        ordering = ['name']
        indexes = [
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.name

    @property
    def is_suspended(self) -> bool:
        return self.status == 'suspended' or not self.is_active


class UserManager(BaseUserManager):
    """Email-based user manager."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('email_verified', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(UUIDPrimaryKeyModel, AbstractBaseUser, PermissionsMixin,
           TimeStampedModel, SoftDeleteModel):
    """Custom user with email login."""

    email = models.EmailField(unique=True, db_index=True, max_length=255)

    organisation = models.ForeignKey(
        Organisation, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='users',
        db_index=True,
        help_text='Tenant this user belongs to. Null for platform superusers.',
    )

    phone_number = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True,
        help_text='International format: +27123456789',
    )
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)

    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True, default=None)
    last_login_at = models.DateTimeField(null=True, blank=True, default=None)

    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=255, blank=True, default='')

    mfa_enrolled_at = models.DateTimeField(null=True, blank=True)
    mfa_last_used_at = models.DateTimeField(null=True, blank=True)
    mfa_last_used_counter = models.BigIntegerField(null=True, blank=True)

    password_history = models.TextField(blank=True, default='')

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email', 'is_active']),
            models.Index(fields=['phone_number']),
            models.Index(fields=['created_at']),
            models.Index(fields=['organisation', 'is_active']),
        ]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def is_locked(self):
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False

    @property
    def has_staff_access(self) -> bool:
        if self.is_superuser or self.is_staff:
            return True
        staff_roles = (
            'Administrator', 'Credit Officer', 'Finance Officer',
            'Collections Officer', 'Compliance Officer', 'Auditor',
        )
        return self.user_roles.filter(
            role__name__in=staff_roles, role__is_active=True,
        ).exists()

    @property
    def is_client_only(self) -> bool:
        return not self.has_staff_access

    def lock_account(self, duration_seconds: int = 1200):
        self.locked_until = timezone.now() + timezone.timedelta(seconds=duration_seconds)
        self.save(update_fields=['locked_until', 'updated_at'])

    def unlock_account(self):
        self.locked_until = None
        self.failed_login_attempts = 0
        self.save(update_fields=['locked_until', 'failed_login_attempts', 'updated_at'])

    def increment_failed_attempts(self):
        self.failed_login_attempts += 1
        self.save(update_fields=['failed_login_attempts', 'updated_at'])
        return self.failed_login_attempts

    def reset_failed_attempts(self):
        if self.failed_login_attempts > 0:
            self.failed_login_attempts = 0
            self.save(update_fields=['failed_login_attempts', 'updated_at'])

    def record_login(self):
        self.last_login_at = timezone.now()
        self.failed_login_attempts = 0
        self.save(update_fields=['last_login_at', 'failed_login_attempts', 'updated_at'])

    def has_role(self, role_name: str) -> bool:
        return self.user_roles.filter(role__name=role_name, role__is_active=True).exists()

    def get_roles(self):
        return self.user_roles.filter(role__is_active=True).select_related('role')

    def has_permission(self, permission_codename: str) -> bool:
        if self.is_superuser:
            return True
        return self.user_roles.filter(
            role__is_active=True,
            role__role_permissions__permission__codename=permission_codename,
            role__role_permissions__permission__is_active=True,
        ).exists()


class Role(UUIDPrimaryKeyModel, TimeStampedModel):
    name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='children',
    )
    is_system_role = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'roles'

    def __str__(self):
        return self.name

    def get_all_permissions(self):
        permissions = set()
        current = self
        while current:
            for rp in current.role_permissions.select_related('permission'):
                if rp.permission.is_active:
                    permissions.add(rp.permission.codename)
            current = current.parent
        return permissions


class Permission(UUIDPrimaryKeyModel, TimeStampedModel):
    codename = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    app_label = models.CharField(max_length=100, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'permissions'
        unique_together = [('app_label', 'codename')]

    def __str__(self):
        return f"{self.app_label}.{self.codename}"


class UserRole(UUIDPrimaryKeyModel, TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_roles')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='user_roles')
    assigned_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='assigned_roles',
    )

    class Meta:
        db_table = 'user_roles'
        unique_together = [('user', 'role')]


class RolePermission(UUIDPrimaryKeyModel, TimeStampedModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='role_permissions')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name='role_permissions')

    class Meta:
        db_table = 'role_permissions'
        unique_together = [('role', 'permission')]


class ClientProfile(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Extended profile for client users.

    NOTE: Banking information is NOT stored here. The client enters banking
    details at mandate-signing time (see BankAccount).
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='client_profile',
    )

    # KYC — encrypted at rest
    id_number = EncryptedTextField(blank=True, default='')
    id_number_index = models.CharField(
        max_length=64, blank=True, default='', db_index=True,
        help_text='HMAC-SHA256 of id_number for equality search.',
    )
    date_of_birth = models.DateField(null=True, blank=True)
    residential_address = EncryptedJSONField(blank=True, null=True, default=None)

    # Employment
    employment_type = models.CharField(
        max_length=50, blank=True,
        choices=[
            ('full_time', 'Full Time'),
            ('part_time', 'Part Time'),
            ('self_employed', 'Self Employed'),
            ('contract', 'Contract'),
            ('unemployed', 'Unemployed'),
            ('retired', 'Retired'),
        ],
    )
    employer_name = models.CharField(max_length=200, blank=True)
    employment_start_date = models.DateField(null=True, blank=True)

    # Financial
    monthly_income = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )
    monthly_expenses = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )
    existing_debt_obligations = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )

    # KYC status
    kyc_status = models.CharField(
        max_length=30, default='pending',
        choices=[
            ('pending', 'Pending'),
            ('submitted', 'Submitted'),
            ('under_review', 'Under Review'),
            ('verified', 'Verified'),
            ('failed', 'Failed'),
            ('additional_info_required', 'Additional Information Required'),
            ('suspended', 'Suspended'),
        ],
    )

    consent_records = models.JSONField(default=dict, blank=True)
    communication_preferences = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'client_profiles'
        indexes = [
            models.Index(fields=['kyc_status']),
        ]

    def __str__(self):
        return f"Client: {self.user.email}"

    def save(self, *args, **kwargs):
        from core.crypto import blind_index
        self.id_number_index = blind_index(self.id_number) if self.id_number else ''
        super().save(*args, **kwargs)


class MFARecoveryCode(UUIDPrimaryKeyModel, TimeStampedModel):
    """Single-use recovery code for MFA. Stored hashed, marked used once consumed."""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='mfa_recovery_codes',
    )
    code_hash = models.CharField(max_length=128, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'mfa_recovery_codes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'used_at']),
        ]

    def __str__(self):
        state = 'used' if self.used_at else 'active'
        return f'MFA code for {self.user_id} ({state})'


class BankAccount(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    A client's bank account, referenced by debit mandates.

    The full account number is encrypted at rest. A blind index allows
    exact-match lookups without decrypting. Only the last 4 digits are
    stored in plaintext for display.
    """
    SOURCE_CHOICES = [
        ('client_entered', 'Client entered'),
        ('bank_statement', 'Bank statement'),
        ('mandate_created', 'Mandate creation'),
        ('staff_entered', 'Staff entered'),
    ]

    ACCOUNT_TYPE_CHOICES = [
        ('cheque', 'Cheque / Current'),
        ('savings', 'Savings'),
        ('transmission', 'Transmission'),
    ]

    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='bank_accounts',
        db_index=True,
    )

    client = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='bank_accounts',
    )
    bank_name = models.CharField(max_length=100)
    account_type = models.CharField(
        max_length=20, choices=ACCOUNT_TYPE_CHOICES, default='cheque',
    )
    account_holder_name = models.CharField(max_length=200)

    account_number = EncryptedTextField(blank=True, default='')
    account_number_last4 = models.CharField(max_length=4, blank=True, default='')
    account_number_index = models.CharField(
        max_length=64, blank=True, default='', db_index=True,
        help_text='HMAC-SHA256 of the digits of account_number.',
    )

    branch_code = models.CharField(max_length=20, blank=True, default='')

    is_primary = models.BooleanField(default=False, db_index=True)
    is_verified = models.BooleanField(default=False)

    source = models.CharField(
        max_length=30, choices=SOURCE_CHOICES, default='client_entered',
    )
    consent_reference = models.CharField(max_length=255, blank=True, default='')

    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='verified_bank_accounts',
    )

    class Meta:
        db_table = 'bank_accounts'
        ordering = ['-is_primary', '-last_seen_at', '-created_at']
        indexes = [
            models.Index(fields=['client', 'is_primary']),
            models.Index(fields=['client', 'is_verified']),
            models.Index(fields=['client', 'account_number_index']),
            models.Index(fields=['organisation', 'is_primary']),
        ]

    def __str__(self):
        return f"{self.bank_name} ****{self.account_number_last4}"

    @property
    def masked_number(self) -> str:
        return f"****{self.account_number_last4}" if self.account_number_last4 else "—"

    def save(self, *args, **kwargs):
        raw = self.account_number or ''
        if raw:
            digits = ''.join(c for c in str(raw) if c.isdigit())
            self.account_number_last4 = digits[-4:] if len(digits) >= 4 else digits
            from core.crypto import blind_index
            self.account_number_index = blind_index(digits)

        demote_others = bool(self.is_primary and self.client_id)
        super().save(*args, **kwargs)
        if demote_others:
            BankAccount.objects.filter(
                client_id=self.client_id, is_primary=True,
            ).exclude(pk=self.pk).update(is_primary=False)