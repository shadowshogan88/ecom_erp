from django.urls import path
from rest_framework.routers import DefaultRouter

from .api_views import DashboardSummaryAPIView, NotificationViewSet, RecentOrdersAPIView, SalesAnalyticsAPIView

router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="dashboard-notification")

urlpatterns = [
    path("summary/", DashboardSummaryAPIView.as_view(), name="dashboard-summary"),
    path("analytics/sales/", SalesAnalyticsAPIView.as_view(), name="dashboard-sales-analytics"),
    path("orders/recent/", RecentOrdersAPIView.as_view(), name="dashboard-recent-orders"),
]
urlpatterns += router.urls

