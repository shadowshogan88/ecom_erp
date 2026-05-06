from __future__ import annotations

from copy import copy as shallow_copy


def patch_django_template_basecontext_copy() -> None:
    """
    Patch Django's template Context copying for Python 3.14+ with Django 4.2.x.

    Django 4.2's BaseContext.__copy__ uses `copy(super())`, which can return a
    `super` proxy object on Python 3.14, breaking template rendering in admin.

    This patch replaces BaseContext.__copy__ with an implementation that:
    - allocates without calling __init__ (works for RequestContext)
    - copies __dict__ shallowly
    - copies the context dict stack shallowly
    """
    try:
        from django.template.context import BaseContext
    except Exception:
        # If Django isn't importable yet (or in a non-Django context), no-op.
        return

    if getattr(BaseContext.__copy__, "_patched_by_project", False):
        return

    def _basecontext_copy(self):  # type: ignore[no-untyped-def]
        duplicate = self.__class__.__new__(self.__class__)
        if hasattr(self, "__dict__"):
            duplicate.__dict__ = self.__dict__.copy()
        duplicate.dicts = self.dicts[:]
        return duplicate

    _basecontext_copy._patched_by_project = True  # type: ignore[attr-defined]
    BaseContext.__copy__ = _basecontext_copy  # type: ignore[assignment]

