from __future__ import annotations
from typing import List, Optional, Type
from datetime import datetime
import logging
from dataclasses import dataclass
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage
)

from ..prompt.prompts import AgentMessagePrompt, SystemPrompt
from ...Browserservice.service import BrowserState
from ..service.service import ActionResult

logger = logging.getLogger(__name__)

@dataclass
class MessageMetadata:
    """消息元数据"""
    input_tokens: int = 0

class MessageHistory:
    """消息历史记录"""
    def __init__(self):
        self.messages: List[MessageWithMetadata] = []
        self.total_tokens: int = 0
        
    def add_message(self, message: BaseMessage, metadata: MessageMetadata) -> None:
        """添加消息"""
        self.messages.append(MessageWithMetadata(message, metadata))
        self.total_tokens += metadata.input_tokens
        
    def remove_message(self, index: int = -1) -> None:
        """移除消息"""
        if self.messages:
            removed = self.messages.pop(index)
            self.total_tokens -= removed.metadata.input_tokens

@dataclass
class MessageWithMetadata:
    """带元数据的消息"""
    message: BaseMessage
    metadata: MessageMetadata

class ContextManager:
    def __init__(
        self,
        llm: BaseChatModel,
        task: str,
        action_descriptions: str,
        system_prompt_class: Type[SystemPrompt],
        max_input_tokens: int = 128000,
        estimated_tokens_per_char: int = 3,
        image_tokens: int = 800,
        include_attributes: list[str] = [],
        max_error_length: int = 400,
        max_actions_per_step: int = 10,
        tool_call_in_content: bool = True,
    ):
        """初始化上下文管理器
        
        Args:
            llm: 语言模型实例
            task: 任务描述
            action_descriptions: 动作描述
            system_prompt_class: 系统提示词类
            max_input_tokens: 最大输入令牌数
            estimated_tokens_per_char: 每字符估计令牌数
            image_tokens: 图片令牌数
            include_attributes: 包含的属性列表
            max_error_length: 最大错误长度
            max_actions_per_step: 每步最大动作数
            tool_call_in_content: 工具调用是否在内容中
        """
        self.llm = llm
        self.system_prompt_class = system_prompt_class
        self.max_input_tokens = max_input_tokens
        self.history = MessageHistory()
        self.task = task
        self.action_descriptions = action_descriptions
        self.tokens_per_char = estimated_tokens_per_char
        self.image_tokens = image_tokens
        self.include_attributes = include_attributes
        self.max_error_length = max_error_length
        self.tool_call_in_content = tool_call_in_content

        # 初始化系统消息
        system_message = self.system_prompt_class(
            self.action_descriptions,
            current_date=datetime.now(),
            max_actions_per_step=max_actions_per_step
        ).get_system_message()
        self._add_message_with_tokens(system_message)
        self.system_prompt = system_message

        # 添加示例工具调用
        tool_calls = [{
            'name': 'AgentOutput',
            'args': {
                'current_state': {
                    'evaluation_previous_goal': '未知 - 没有之前的动作可评估',
                    'memory': '',
                    'next_goal': '从用户获取任务'
                },
                'action': []
            },
            'id': '',
            'type': 'tool_call'
        }]

        example_tool_call = AIMessage(
            content=str(tool_calls) if tool_call_in_content else '',
            tool_calls=[] if tool_call_in_content else tool_calls
        )
        self._add_message_with_tokens(example_tool_call)

        # 添加任务说明
        task_message = self._create_task_message(task)
        self._add_message_with_tokens(task_message)

    def _create_task_message(self, task: str) -> HumanMessage:
        """创建任务消息"""
        content = f'你的最终任务是: {task}。如果你完成了最终任务，立即停止并在下一步使用done动作完成任务。如果没有完成，则继续执行。'
        return HumanMessage(content=content)

    def add_state_message(
        self,
        state: BrowserState,
        result: Optional[List[ActionResult]] = None,
        step_info: Optional[dict] = None
    ) -> None:
        """添加浏览器状态消息"""
        # 处理需要保存到记忆的结果
        if result:
            for r in result:
                if r.include_in_memory:
                    if r.content:
                        msg = HumanMessage(content='动作结果: ' + str(r.content))
                        self._add_message_with_tokens(msg)
                    if r.error:
                        msg = HumanMessage(content='动作错误: ' + str(r.error)[-self.max_error_length:])
                        self._add_message_with_tokens(msg)
                    result = None

        # 添加状态消息
        state_message = AgentMessagePrompt(
            state,
            result,
            include_attributes=self.include_attributes,
            max_error_length=self.max_error_length,
            step_info=step_info
        ).get_user_message()
        self._add_message_with_tokens(state_message)

    def add_model_output(self, output: dict) -> None:
        """添加模型输出"""
        tool_calls = [{
            'name': 'AgentOutput',
            'args': output,
            'id': '',
            'type': 'tool_call'
        }]

        msg = AIMessage(
            content=str(tool_calls) if self.tool_call_in_content else '',
            tool_calls=[] if self.tool_call_in_content else tool_calls
        )
        self._add_message_with_tokens(msg)

    def get_messages(self) -> List[BaseMessage]:
        """获取当前消息列表"""
        self._trim_messages()
        return [m.message for m in self.history.messages]

    def _trim_messages(self) -> None:
        """裁剪消息以符合令牌限制"""
        diff = self.history.total_tokens - self.max_input_tokens
        if diff <= 0:
            return

        msg = self.history.messages[-1]

        # 处理图片消息
        if isinstance(msg.message.content, list):
            text = ''
            for item in msg.message.content:
                if 'image_url' in item:
                    msg.message.content.remove(item)
                    diff -= self.image_tokens
                    msg.metadata.input_tokens -= self.image_tokens
                    self.history.total_tokens -= self.image_tokens
                elif 'text' in item and isinstance(item, dict):
                    text += item['text']
            msg.message.content = text
            self.history.messages[-1] = msg

        if diff <= 0:
            return

        # 如果仍然超出限制，按比例删除文本
        proportion = diff / msg.metadata.input_tokens
        if proportion > 0.99:
            raise ValueError('达到最大令牌限制 - 历史记录过长')

        content = msg.message.content
        chars_to_remove = int(len(content) * proportion)
        content = content[:-chars_to_remove]

        self.history.remove_message(index=-1)
        new_msg = HumanMessage(content=content)
        self._add_message_with_tokens(new_msg)

    def _add_message_with_tokens(self, message: BaseMessage) -> None:
        """添加带令牌计数的消息"""
        token_count = self._count_tokens(message)
        metadata = MessageMetadata(input_tokens=token_count)
        self.history.add_message(message, metadata)

    def _count_tokens(self, message: BaseMessage) -> int:
        """计算消息中的令牌数"""
        tokens = 0
        if isinstance(message.content, list):
            for item in message.content:
                if 'image_url' in item:
                    tokens += self.image_tokens
                elif isinstance(item, dict) and 'text' in item:
                    tokens += self._count_text_tokens(item['text'])
        else:
            tokens += self._count_text_tokens(message.content)
        return tokens

    def _count_text_tokens(self, text: str) -> int:
        """计算文本中的令牌数"""
        try:
            return self.llm.get_num_tokens(text)
        except:
            return len(text) // self.tokens_per_char
