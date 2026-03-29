"""
Accounts app — Custom User model, registration, login, profile management.
Uses email as the primary identifier (no username).
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, name, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model with email authentication and content categories."""

    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=150)
    # Stores selected content categories as a JSON list, e.g. ["tech", "finance"]
    categories = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    # Plan: free | pro
    plan = models.CharField(max_length=20, default="free")
    notification_enabled = models.BooleanField(default=True)
    # Data refresh interval in minutes
    data_refresh_interval = models.IntegerField(default=15)
    # YouTube OAuth credentials
    youtube_access_token = models.TextField(blank=True, default="")
    youtube_refresh_token = models.TextField(blank=True, default="")
    youtube_channel_id = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email
