from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .service import ControllerService, ActionResult
from typing import List, Dict
import asyncio
import logging

logger = logging.getLogger(__name__)

class ControllerView(APIView):
    """控制器API视图"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.controller = ControllerService()
        
    async def post(self, request):
        """处理动作执行请求
        
        请求体格式：
        {
            "actions": [
                {
                    "action": "动作名称",
                    "params": {
                        "参数名": "参数值"
                    }
                }
            ],
            "single_action": false  # 是否为单个动作
        }
        """
        try:
            actions = request.data.get('actions', [])
            single_action = request.data.get('single_action', False)
            
            if not actions:
                return Response(
                    {"error": "动作列表不能为空"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            if single_action:
                # 执行单个动作
                action = actions[0]
                result = await self.controller.execute_action(
                    action.get('action'),
                    **action.get('params', {})
                )
                return Response(self._format_result(result))
            else:
                # 执行多个动作
                results = await self.controller.execute_actions(actions)
                return Response([self._format_result(r) for r in results])
                
        except Exception as e:
            logger.error(f"执行动作失败: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    def _format_result(self, result: ActionResult) -> Dict:
        """格式化动作结果"""
        return {
            "content": result.extracted_content,
            "error": result.error,
            "done": result.is_done,
            "include_in_memory": result.include_in_memory
        }

class ActionListView(APIView):
    """动作列表API视图"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.controller = ControllerService()
        
    def get(self, request):
        """获取所有可用动作列表"""
        try:
            actions = []
            for name, info in self.controller.registry.items():
                actions.append({
                    "name": name,
                    "description": info["description"]
                })
            return Response({"actions": actions})
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
