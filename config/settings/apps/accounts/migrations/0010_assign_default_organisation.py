"""
Data migration: create a default organisation and assign every existing
user to it. Ensures single-tenant mode continues to work without manual
intervention.
"""
from django.db import migrations
from django.utils.text import slugify


DEFAULT_SLUG = 'wethu-default'
DEFAULT_NAME = 'Wethu Micro Lenders (default)'


def assign_default_org(apps, schema_editor):
    Organisation = apps.get_model('accounts', 'Organisation')
    User = apps.get_model('accounts', 'User')

    default_org, created = Organisation.objects.get_or_create(
        slug=DEFAULT_SLUG,
        defaults={
            'name': DEFAULT_NAME,
            'legal_name': 'Wethu Micro Lenders',
            'status': 'active',
            'is_active': True,
            'plan': 'standard',
            'settings': {
                'is_default': True,
                'note': 'Auto-created by migration 0010_assign_default_organisation.',
            },
        },
    )

    verb = 'Created' if created else 'Reused'
    print(f'  {verb} default organisation: {default_org.name} (slug={default_org.slug})')

    # Assign every user who has no organisation.
    unassigned = User.objects.filter(organisation__isnull=True)
    count = unassigned.count()
    if count:
        unassigned.update(organisation=default_org)
        print(f'  Assigned {count} user(s) to {default_org.name}')

    # Give the default org a stable `slugify` fallback name if it was created
    # without one. (Defensive — get_or_create already sets it.)
    if not default_org.slug:
        default_org.slug = slugify(DEFAULT_SLUG) or DEFAULT_SLUG
        default_org.save(update_fields=['slug', 'updated_at'])


def reverse_noop(apps, schema_editor):
    """No reverse — deleting the default org would orphan users."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        # ⚠️ Replace with the actual migration name from Step 5
        ('accounts', '0009_create_organisation'),
    ]

    operations = [
        migrations.RunPython(assign_default_org, reverse_code=reverse_noop),
    ]