from django.urls import path
from .views import (
    RegisterView, LoginView, TokenRefreshView, ProfileView,
    PasswordResetRequestView, PasswordResetConfirmView, reset_password_form,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("profile/", ProfileView.as_view(), name="auth-profile"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    path("reset-password-form/", reset_password_form, name="reset-password-form"),
]
