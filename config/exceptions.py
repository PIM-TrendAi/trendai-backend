"""
Custom exception handler for consistent error responses across the API.
All errors return: { "error": "message", "details": {...} }
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def _extract_error_message(details):
    if isinstance(details, list):
        if not details:
            return None
        first = details[0]
        return str(first)

    if isinstance(details, dict):
        for value in details.values():
            message = _extract_error_message(value)
            if message:
                return message
        return None

    if details is None:
        return None

    return str(details)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        error_data = {
            "error": "An error occurred.",
            "details": response.data,
        }
        # Provide a human-readable message for common cases
        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            error_data["error"] = "Authentication required."
        elif response.status_code == status.HTTP_403_FORBIDDEN:
            error_data["error"] = "Permission denied."
        elif response.status_code == status.HTTP_404_NOT_FOUND:
            error_data["error"] = "Resource not found."
        elif response.status_code == status.HTTP_400_BAD_REQUEST:
            extracted = _extract_error_message(response.data)
            error_data["error"] = extracted or "Invalid request data."

        response.data = error_data

    return response
