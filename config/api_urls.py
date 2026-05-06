from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path("auth/token/", obtain_auth_token, name="api-token"),
    path("auth/", include("apps.users.api_urls")),
    path("products/", include("apps.products.api_urls")),
    path("orders/", include("apps.orders.api_urls")),
    path("payments/", include("apps.payments.api_urls")),
    path("shipping/", include("apps.shipping.api_urls")),
    path("dashboard/", include("apps.dashboard.api_urls")),
    path("reports/", include("apps.reports.api_urls")),
]
