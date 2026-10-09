from .models import Organization


def ensure_organization(org_id: str, name: str = "") -> Organization:
    """Return the Organization for ``org_id``, creating it if needed and filling in a missing name."""
    org, created = Organization.objects.get_or_create(org_id=org_id, defaults={"name": name})
    if not created and name and not org.name:
        org.name = name
        org.save(update_fields=["name", "updated_at"])
    return org
