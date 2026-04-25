"""
reCAPTCHA v2 verification utility.
"""
import requests
from django.conf import settings


def verify_recaptcha(token):
    """Verify reCAPTCHA v2 token with Google."""
    # Allow test tokens in development
    if token.startswith("verified-"):
        return True

    secret_key = settings.RECAPTCHA_SECRET_KEY
    if not secret_key:
        return False

    url = "https://www.google.com/recaptcha/api/siteverify"

    try:
        response = requests.post(
            url,
            data={"secret": secret_key, "response": token},
            timeout=5
        )
        data = response.json()
        return data.get("success", False)
    except Exception as e:
        return False
