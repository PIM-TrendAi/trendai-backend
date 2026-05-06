"""
Accounts views: Register, Login, Token Refresh, Profile (GET/PATCH).
All endpoints return consistent JSON with appropriate HTTP status codes.
"""
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiResponse

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods

from .models import User
from .serializers import (
    RegisterSerializer, LoginSerializer, UserProfileSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
)
from .recaptcha import verify_recaptcha


def get_tokens_for_user(user):
    """Returns a dict of access + refresh JWT tokens for a given user."""
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


class RegisterView(APIView):
    """POST /api/auth/register/ — Create a new user account."""
    permission_classes = [AllowAny]

    @extend_schema(request=RegisterSerializer, responses={201: UserProfileSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        recaptcha_token = serializer.validated_data.get("recaptcha_token")
        if not verify_recaptcha(recaptcha_token):
            return Response(
                {"error": "reCAPTCHA verification failed. Please try again."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = serializer.save()
        tokens = get_tokens_for_user(user)
        return Response(
            {**UserProfileSerializer(user).data, "tokens": tokens},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """POST /api/auth/login/ — Authenticate and receive JWT tokens."""
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        user = serializer.validated_data["user"]
        tokens = get_tokens_for_user(user)
        return Response(
            {**UserProfileSerializer(user).data, "tokens": tokens},
            status=status.HTTP_200_OK,
        )


def reset_password_form(request):
    """GET /api/auth/reset-password-form/?uid=...&token=... — HTML form for password reset."""
    uid = request.GET.get('uid', '')
    token = request.GET.get('token', '')

    if not uid or not token:
        return HttpResponse("Invalid or missing reset link.", status=400)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Reset Password</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
            .container {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); width: 100%; max-width: 400px; }}
            h1 {{ font-size: 28px; margin-bottom: 12px; }}
            p {{ color: #666; margin-bottom: 32px; font-size: 14px; }}
            input {{ width: 100%; padding: 12px; margin-bottom: 16px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; }}
            input:focus {{ outline: none; border-color: #667eea; }}
            button {{ width: 100%; padding: 12px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; }}
            button:hover {{ opacity: 0.9; }}
            .error {{ color: #e74c3c; font-size: 14px; margin-top: 12px; }}
            .success {{ color: #27ae60; font-size: 14px; margin-top: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Reset Password</h1>
            <p>Enter your new password below.</p>
            <form id="resetForm">
                <input type="password" id="password" placeholder="New Password (min 8 characters)" required minlength="8">
                <input type="password" id="confirmPassword" placeholder="Confirm Password" required>
                <button type="submit">Reset Password</button>
                <div id="message"></div>
            </form>
        </div>
        <script>
            document.getElementById('resetForm').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const password = document.getElementById('password').value;
                const confirmPassword = document.getElementById('confirmPassword').value;
                const messageEl = document.getElementById('message');

                if (password !== confirmPassword) {{
                    messageEl.innerHTML = '<div class="error">Passwords do not match</div>';
                    return;
                }}

                try {{
                    const response = await fetch('/api/auth/password-reset/confirm/', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            uid: '{uid}',
                            token: '{token}',
                            new_password: password,
                            confirm_password: confirmPassword
                        }})
                    }});
                    const data = await response.json();
                    if (response.ok) {{
                        messageEl.innerHTML = '<div class="success">✓ Password reset successful! Redirecting to login...</div>';
                        setTimeout(() => window.location.href = '/login', 2000);
                    }} else {{
                        messageEl.innerHTML = '<div class="error">Error: ' + (data.error || 'Failed to reset password') + '</div>';
                    }}
                }} catch (error) {{
                    messageEl.innerHTML = '<div class="error">Error: ' + error.message + '</div>';
                }}
            }});
        </script>
    </body>
    </html>
    """
    return HttpResponse(html)


class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/ — Send reset link to email."""
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetRequestSerializer)
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            print(f"[DEBUG] Serializer errors: {serializer.errors}")
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        recaptcha_token = serializer.validated_data.get("recaptcha_token")
        print(f"[DEBUG] reCAPTCHA token: {recaptcha_token}")
        if not verify_recaptcha(recaptcha_token):
            return Response(
                {"error": "reCAPTCHA verification failed. Please try again."},
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data["email"]
        user = User.objects.filter(email=email).first()

        if user:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_url = f"http://localhost:8000/api/auth/reset-password-form/?uid={uid}&token={token}"

            message = (
                f"Hello {user.name or 'there'},\n\n"
                "You requested a password reset for your TrendAI account.\n"
                f"Please use the following link to reset your password:\n\n{reset_url}\n\n"
                "If you didn't request this, you can safely ignore this email."
            )
            try:
                send_mail(
                    subject="Reset your TrendAI Password",
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
            except Exception as e:
                return Response({"error": f"Failed to send email: {str(e)}"}, status=500)

        return Response({"message": "If an account exists with this email, a reset link has been sent."}, status=200)


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset/confirm/ — Set new password using token."""
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetConfirmSerializer)
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        uid = serializer.validated_data["uid"]
        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Invalid reset link."}, status=400)

        if not default_token_generator.check_token(user, token):
            return Response({"error": "Invalid or expired token."}, status=400)

        user.set_password(new_password)
        user.save()
        return Response({"message": "Password reset successful. You can now log in."}, status=200)


class TokenRefreshView(APIView):
    """POST /api/auth/refresh/ — Refresh access token using refresh token."""
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"error": "Refresh token required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            return Response(
                {"access": str(token.access_token)},
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response({"error": "Invalid or expired refresh token."}, status=status.HTTP_401_UNAUTHORIZED)


class ProfileView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/auth/profile/ — Get or update authenticated user's profile."""
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
