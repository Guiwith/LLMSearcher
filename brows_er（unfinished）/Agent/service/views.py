from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from typing import Dict, List, Optional
import logging
from langchain_core.language_models import BaseChatModel

from .service import Agent
from ...LLMservice.service import LLMService
from ...Browserservice.service import BrowserService
from ...Controller.service import ControllerService

logger = logging.getLogger(__name__)

class AgentView(APIView):
    """Agent API视图"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.llm_service = LLMService()
        self.agents: Dict[str, Agent] = {}  # 存储运行中的agents
        
    async def post(self, request):
        """创建并运行新的Agent任务
        
        请求体格式：
        {
            "task": "要执行的任务描述",
            "use_vision": true,
            "max_steps": 10,
            "max_failures": 3,
            "retry_delay": 10,
            "max_actions_per_step": 5
        }
        """
        try:
            task = request.data.get('task')
            if not task:
                return Response(
                    {"error": "必须提供任务描述"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            # 创建新的Agent实例
            agent = Agent(
                task=task,
                llm=self.llm_service,
                use_vision=request.data.get('use_vision', True),
                max_steps=request.data.get('max_steps', 10),
                max_failures=request.data.get('max_failures', 3),
                retry_delay=request.data.get('retry_delay', 10),
                max_actions_per_step=request.data.get('max_actions_per_step', 5)
            )
            
            # 存储Agent实例
            self.agents[agent.agent_id] = agent
            
            # 运行Agent
            results = await agent.run()
            
            # 格式化响应
            response_data = {
                "agent_id": agent.agent_id,
                "task": task,
                "steps_taken": agent.steps,
                "results": [
                    {
                        "content": r.content,
                        "error": r.error,
                        "is_done": r.is_done
                    } for r in results
                ],
                "status": "completed" if results and results[-1].is_done else "failed"
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Agent执行失败: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    async def get(self, request):
        """获取Agent状态
        
        查询参数：
        - agent_id: Agent ID
        """
        try:
            agent_id = request.query_params.get('agent_id')
            if not agent_id:
                # 返回所有Agent的状态
                return Response({
                    "agents": [
                        {
                            "agent_id": aid,
                            "task": agent.task,
                            "steps": agent.steps,
                            "status": "running" if agent.steps < agent.max_steps else "completed"
                        } for aid, agent in self.agents.items()
                    ]
                })
                
            # 返回特定Agent的状态
            agent = self.agents.get(agent_id)
            if not agent:
                return Response(
                    {"error": f"Agent {agent_id} 不存在"},
                    status=status.HTTP_404_NOT_FOUND
                )
                
            return Response({
                "agent_id": agent_id,
                "task": agent.task,
                "steps_taken": agent.steps,
                "history": agent.history,
                "status": "running" if agent.steps < agent.max_steps else "completed"
            })
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    async def delete(self, request):
        """停止并清理Agent
        
        查询参数：
        - agent_id: Agent ID
        """
        try:
            agent_id = request.query_params.get('agent_id')
            if not agent_id:
                return Response(
                    {"error": "必须提供agent_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            agent = self.agents.get(agent_id)
            if not agent:
                return Response(
                    {"error": f"Agent {agent_id} 不存在"},
                    status=status.HTTP_404_NOT_FOUND
                )
                
            # 清理资源
            await agent._cleanup()
            del self.agents[agent_id]
            
            return Response({"status": "success"})
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
