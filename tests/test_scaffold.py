"""Basic scaffold smoke test."""

import pytest
from django.conf import settings


@pytest.mark.django_db
def test_django_scaffold_settings() -> None:
    """Verify that Django settings are configured and accessible."""
    assert settings.configured
    assert "stations" in settings.INSTALLED_APPS
    assert "api" in settings.INSTALLED_APPS
    assert "maps" in settings.INSTALLED_APPS
