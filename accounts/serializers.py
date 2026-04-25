"""
Serializers for all account-related operations.
"""
from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    """Validates and creates a new user."""
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    recaptcha_token = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "name", "password", "confirm_password", "recaptcha_token"]

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password", None)
        validated_data.pop("recaptcha_token", None)
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    """Authenticates with email + password."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs["email"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("Account is disabled.")
        attrs["user"] = user
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """Read/update user profile (excludes password)."""
    class Meta:
        model = User
        fields = [
            "id", "email", "name", "categories", "plan",
            "notification_enabled", "data_refresh_interval",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "email", "plan", "created_at", "updated_at"]


class PasswordResetRequestSerializer(serializers.Serializer):
    """Simple serializer to validate email for reset request."""
    email = serializers.EmailField()
    recaptcha_token = serializers.CharField(write_only=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Validates token, uid, and new passwords."""
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs
