from django.urls import path
from .views import GenerateScriptView, SavedScriptListView

urlpatterns = [
    path("", SavedScriptListView.as_view(), name="script-list"),
    path("generate/", GenerateScriptView.as_view(), name="script-generate"),
]
