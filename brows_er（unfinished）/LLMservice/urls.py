from django.urls import path
from .views import ChatCompletionView, ModelsView

urlpatterns = [
    path('v1/chat/completions', ChatCompletionView.as_view(), name='chat-completions'),
    path('v1/models', ModelsView.as_view(), name='models'),
] 