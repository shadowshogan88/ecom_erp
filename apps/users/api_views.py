from __future__ import annotations

from django.contrib.auth import authenticate
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .jwt_service import revoke_refresh_token, rotate_refresh_token
from .models import LoginActivity


def _client_meta(request) -> tuple[str | None, str]:
    ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR")
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]
    return (ip, ua)


class JWTCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        if not username or not password:
            return Response({"detail": "username and password required."}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request=request, username=username, password=password)
        if not user:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        from .jwt_service import create_access_token, create_refresh_token

        access = create_access_token(user=user)
        refresh = create_refresh_token(user=user)

        ip, ua = _client_meta(request)
        LoginActivity.objects.create(user=user, event=LoginActivity.Event.LOGIN, ip_address=ip, user_agent=ua)

        return Response(
            {
                "access": access,
                "refresh": refresh,
                "user": {"public_id": user.public_id, "username": user.username, "role": getattr(user, "role", "")},
            }
        )


class JWTRefreshAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh = request.data.get("refresh") or ""
        if not refresh:
            return Response({"detail": "refresh token required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            access, new_refresh = rotate_refresh_token(refresh_token=refresh)
        except Exception:
            return Response({"detail": "Invalid refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

        ip, ua = _client_meta(request)
        LoginActivity.objects.create(user=None, event=LoginActivity.Event.TOKEN_REFRESH, ip_address=ip, user_agent=ua)
        return Response({"access": access, "refresh": new_refresh})


class JWTLogoutAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh = request.data.get("refresh") or ""
        if refresh:
            revoke_refresh_token(refresh_token=refresh)

        ip, ua = _client_meta(request)
        LoginActivity.objects.create(user=None, event=LoginActivity.Event.LOGOUT, ip_address=ip, user_agent=ua)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({"public_id": user.public_id, "username": user.username, "role": getattr(user, "role", "")})

