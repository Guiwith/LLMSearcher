from django.urls import path
from .views import DOMAnalysisView

urlpatterns = [
    path('dom/analyze', DOMAnalysisView.as_view(), name='dom-analyze'),
] 