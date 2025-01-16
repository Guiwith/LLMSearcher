from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from typing import Dict, Optional
import logging

from .service import ContextManager
from ..prompt.prompts import SystemPrompt
from ...LLMservice.service import LLMService
from ...Browserservice.service import BrowserState

logger = logging.getLogger(__name__)

class ContextManagerView(APIView):
    """上下文管理器API视图"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.llm_service = LLMService()
        self.contexts: Dict[str, ContextManager] = {}  # 存储不同会话的上下文
        
    async def post(self, request):
        """创建或更新上下文
        
        请求体格式：
        {
            "session_id": "会话ID",
            "task": "任务描述",
            "action_descriptions": "动作描述",
            "state": {
                "url": "当前URL",
                "tabs": ["标签页1", "标签页2"],
                "elements": [...],
                "screenshot": "base64图片"
            },
            "config": {
                "max_input_tokens": 128000,
                "include_attributes": [],
                "max_error_length": 400,
                "max_actions_per_step": 10
            }
        }
        """
        try:
            session_id = request.data.get('session_id')
            task = request.data.get('task')
            action_descriptions = request.data.get('action_descriptions')
            state_data = request.data.get('state')
            config = request.data.get('config', {})
            
            if not all([session_id, task, action_descriptions, state_data]):
                return Response(
                    {"error": "缺少必要参数"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            # 创建或获取上下文管理器
            if session_id not in self.contexts:
                context_manager = ContextManager(
                    llm=self.llm_service,
                    task=task,
                    action_descriptions=action_descriptions,
                    system_prompt_class=SystemPrompt,
                    **config
                )
                self.contexts[session_id] = context_manager
            else:
                context_manager = self.contexts[session_id]
                
            # 更新状态
            browser_state = BrowserState(**state_data)
            context_manager.add_state_message(browser_state)
            
            return Response({
                "session_id": session_id,
                "message_count": len(context_manager.history.messages),
                "total_tokens": context_manager.history.total_tokens
            })
            
        except Exception as e:
            logger.error(f"上下文管理失败: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    async def get(self, request):
        """获取上下文状态
        
        查询参数：
        - session_id: 会话ID
        """
        try:
            session_id = request.query_params.get('session_id')
            if not session_id:
                # 返回所有会话的概览
                return Response({
                    "sessions": [
                        {
                            "session_id": sid,
                            "task": context.task,
                            "message_count": len(context.history.messages),
                            "total_tokens": context.history.total_tokens
                        } for sid, context in self.contexts.items()
                    ]
                })
                
            # 返回特定会话的详细信息
            context = self.contexts.get(session_id)
            if not context:
                return Response(
                    {"error": f"会话 {session_id} 不存在"},
                    status=status.HTTP_404_NOT_FOUND
                )
                
            messages = context.get_messages()
            return Response({
                "session_id": session_id,
                "task": context.task,
                "message_count": len(messages),
                "total_tokens": context.history.total_tokens,
                "messages": [
                    {
                        "type": msg.__class__.__name__,
                        "content": msg.content
                    } for msg in messages
                ]
            })
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    async def delete(self, request):
        """删除上下文
        
        查询参数：
        - session_id: 会话ID
        """
        try:
            session_id = request.query_params.get('session_id')
            if not session_id:
                return Response(
                    {"error": "必须提供session_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            if session_id in self.contexts:
                del self.contexts[session_id]
                return Response({"status": "success"})
            else:
                return Response(
                    {"error": f"会话 {session_id} 不存在"},
                    status=status.HTTP_404_NOT_FOUND
                )
                
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
