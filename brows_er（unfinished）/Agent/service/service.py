from typing import Dict, List, Optional, Any
import logging
import uuid
from dataclasses import dataclass
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage

from ...LLMservice.service import LLMService
from ...Browserservice.service import BrowserService
from ...DomTree.service import DOMService
from ...Controller.service import ControllerService

logger = logging.getLogger(__name__)

@dataclass
class ActionResult:
    """动作执行结果"""
    content: Optional[str] = None
    error: Optional[str] = None
    is_done: bool = False
    include_in_memory: bool = False

class Agent:
    def __init__(
        self,
        task: str,
        llm: BaseChatModel,
        browser_service: Optional[BrowserService] = None,
        controller: Optional[ControllerService] = None,
        use_vision: bool = True,
        max_steps: int = 10,
        max_failures: int = 3,
        retry_delay: int = 10,
        max_actions_per_step: int = 5
    ):
        """初始化Agent
        
        Args:
            task: 任务描述
            llm: 语言模型实例
            browser_service: 浏览器服务实例
            controller: 控制器服务实例
            use_vision: 是否使用视觉功能
            max_steps: 最大步骤数
            max_failures: 最大失败次数
            retry_delay: 重试延迟(秒)
            max_actions_per_step: 每步最大动作数
        """
        self.agent_id = str(uuid.uuid4())
        self.task = task
        self.llm = llm
        self.use_vision = use_vision
        
        # 服务初始化
        self.browser_service = browser_service or BrowserService()
        self.controller = controller or ControllerService()
        self.dom_service = DOMService(self.browser_service.page)
        
        # 运行参数
        self.max_steps = max_steps
        self.max_failures = max_failures
        self.retry_delay = retry_delay
        self.max_actions_per_step = max_actions_per_step
        
        # 状态追踪
        self.steps = 0
        self.failures = 0
        self.history: List[Dict] = []
        self._last_result = None
        
    async def run(self) -> List[ActionResult]:
        """运行Agent完成任务"""
        logger.info(f"🚀 开始任务: {self.task}")
        
        try:
            while not self._should_stop():
                try:
                    result = await self.step()
                    if result and result[-1].is_done:
                        logger.info("✅ 任务完成")
                        return result
                except Exception as e:
                    self.failures += 1
                    logger.error(f"步骤执行失败: {str(e)}")
                    if self.failures >= self.max_failures:
                        raise Exception(f"达到最大失败次数: {self.max_failures}")
                    
            return self._last_result or []
            
        finally:
            await self._cleanup()
            
    async def step(self) -> List[ActionResult]:
        """执行单个步骤"""
        logger.info(f"\n📍 步骤 {self.steps + 1}")
        
        try:
            # 获取当前状态
            state = await self.dom_service.analyze_page()
            
            # 准备LLM输入
            messages = self._prepare_messages(state)
            
            # 获取下一个动作
            actions = await self._get_next_actions(messages)
            
            # 执行动作
            results = await self.controller.execute_actions(actions)
            
            # 更新状态
            self._last_result = results
            self.steps += 1
            self.history.append({
                "step": self.steps,
                "state": state,
                "actions": actions,
                "results": results
            })
            
            return results
            
        except Exception as e:
            logger.error(f"步骤执行错误: {str(e)}")
            return [ActionResult(error=str(e))]
            
    async def _get_next_actions(self, messages: List[BaseMessage]) -> List[Dict]:
        """从LLM获取下一步动作"""
        try:
            response = await self.llm.agenerate(messages)
            actions = self._parse_actions(response.generations[0][0].text)
            return actions[:self.max_actions_per_step]
        except Exception as e:
            raise Exception(f"获取动作失败: {str(e)}")
            
    def _prepare_messages(self, state: Dict) -> List[BaseMessage]:
        """准备发送给LLM的消息"""
        messages = [
            SystemMessage(content=f"你是一个网页自动化助手。当前任务: {self.task}"),
            SystemMessage(content="可用动作: " + str(self.controller.get_available_actions()))
        ]
        
        if self._last_result:
            messages.append(SystemMessage(content="上一步结果: " + str(self._last_result)))
            
        messages.append(SystemMessage(content="当前页面状态: " + str(state)))
        
        return messages
        
    def _should_stop(self) -> bool:
        """检查是否应该停止执行"""
        return (
            self.steps >= self.max_steps or
            self.failures >= self.max_failures
        )
        
    async def _cleanup(self):
        """清理资源"""
        try:
            await self.browser_service.close()
        except Exception as e:
            logger.error(f"清理资源失败: {str(e)}")