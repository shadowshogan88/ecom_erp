from django.urls import include, path

urlpatterns = [
    path("", include("apps.products.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.users.urls")),
    # Backward-compatible alias (older links may still point here)
    path("dashboard/", include("apps.dashboard.urls")),
    # Admin (custom ERP-style dashboard, staff-only) - keep this LAST so reverse() prefers /dashboard/admin/
    path("dashboard/admin/", include("apps.dashboard.urls")),
]
