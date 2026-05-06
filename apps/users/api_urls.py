from django.urls import path

from .api_views import JWTCreateAPIView, JWTLogoutAPIView, JWTRefreshAPIView, MeAPIView

urlpatterns = [
    path("jwt/create/", JWTCreateAPIView.as_view(), name="jwt-create"),
    path("jwt/refresh/", JWTRefreshAPIView.as_view(), name="jwt-refresh"),
    path("jwt/logout/", JWTLogoutAPIView.as_view(), name="jwt-logout"),
    path("me/", MeAPIView.as_view(), name="me"),
]

