from django.urls import path

from .api_views import (
    InventoryLowStockReportAPIView,
    ProfitLossReportAPIView,
    SalesReportAPIView,
    TopCustomersReportAPIView,
)

urlpatterns = [
    path("sales/", SalesReportAPIView.as_view(), name="report-sales"),
    path("inventory/low-stock/", InventoryLowStockReportAPIView.as_view(), name="report-low-stock"),
    path("customers/top/", TopCustomersReportAPIView.as_view(), name="report-top-customers"),
    path("profit-loss/", ProfitLossReportAPIView.as_view(), name="report-profit-loss"),
]

