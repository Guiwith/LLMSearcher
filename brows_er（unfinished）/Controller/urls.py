from django.urls import path
from .views import ControllerView, ActionListView

urlpatterns = [
    path('controller/execute', ControllerView.as_view(), name='controller-execute'),
    path('controller/actions', ActionListView.as_view(), name='action-list'),
] 