from django.urls import path
from .views import ContextManagerView

urlpatterns = [
    path('context', ContextManagerView.as_view(), name='context-manager'),
] 