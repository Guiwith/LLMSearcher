from django.urls import path
from .views import BrowserControlView

urlpatterns = [
    path('browser/control', BrowserControlView.as_view(), name='browser-control'),
] 