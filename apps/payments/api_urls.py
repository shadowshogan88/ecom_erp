from django.urls import path
from rest_framework.routers import DefaultRouter

from .api_views import MyPaymentViewSet, PaymentViewSet

router = DefaultRouter()
router.register(r"manage", PaymentViewSet, basename="payment")
router.register(r"my", MyPaymentViewSet, basename="my-payment")

urlpatterns = []
urlpatterns += router.urls

