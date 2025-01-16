from django.urls import path
from .views import AgentView

urlpatterns = [
    path('agent', AgentView.as_view(), name='agent'),
] 