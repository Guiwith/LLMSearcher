from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .service import LLMService
from django.conf import settings

class ChatCompletionView(APIView):
    """聊天完成API视图"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 从settings中获取base_url，如果没有则使用默认值
        base_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434')
        self.llm_service = LLMService(base_url=base_url)

    def post(self, request):
        """处理聊天完成请求
        
        请求体格式：
        {
            "model": "llama2",
            "messages": [{"role": "user", "content": "你好"}],
            "temperature": 0.7,
            "stream": false
        }
        """
        try:
            # 获取请求参数
            model = request.data.get('model', 'llama2')
            messages = request.data.get('messages', [])
            temperature = request.data.get('temperature', 0.7)
            stream = request.data.get('stream', False)
            
            # 参数验证
            if not messages:
                return Response(
                    {"error": "消息不能为空"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 调用LLM服务
            response = self.llm_service.chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                stream=stream
            )
            
            return Response(response)
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ModelsView(APIView):
    """获取可用模型列表的API视图"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        base_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434')
        self.llm_service = LLMService(base_url=base_url)

    def get(self, request):
        """获取可用模型列表"""
        try:
            models = self.llm_service.get_models()
            return Response({
                "data": models
            })
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
