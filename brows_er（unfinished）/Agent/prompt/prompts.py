from datetime import datetime
from typing import List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from ...Browserservice.service import BrowserState
from ..service.service import ActionResult

class SystemPrompt:
    def __init__(
        self, 
        action_description: str, 
        current_date: datetime, 
        max_actions_per_step: int = 10
    ):
        self.default_action_description = action_description
        self.current_date = current_date
        self.max_actions_per_step = max_actions_per_step

    def important_rules(self) -> str:
        """返回Agent的重要规则"""
        return """
1. 响应格式：必须始终使用以下JSON格式响应：
   {
     "current_state": {
       "evaluation_previous_goal": "成功|失败|未知 - 分析当前元素和图像，检查之前的目标/动作是否按预期完成。忽略动作结果，以网页为准。同时说明是否出现意外情况（如输入框的新建议）",
       "memory": "描述已完成的操作和需要记住的信息",
       "next_goal": "下一步动作需要完成的目标"
     },
     "action": [
       {
         "动作名称": {
           // 动作特定参数
         }
       }
     ]
   }

2. 动作序列：
   - 可以指定多个按顺序执行的动作
   - 每个动作项只能包含一个动作名称
   - 常见动作序列示例：
     表单填写: [
       {"input_text": {"index": 1, "text": "用户名"}},
       {"input_text": {"index": 2, "text": "密码"}},
       {"click_element": {"index": 3}}
     ]

3. 元素交互规则：
   - 只能使用元素列表中存在的索引
   - 每个元素都有唯一的索引号（例如"33[:]<button>"）
   - 带有"_[:]"的元素是不可交互的（仅用于上下文）

4. 导航和错误处理：
   - 如果找不到合适的元素，使用其他功能完成任务
   - 遇到困难时尝试替代方案
   - 处理弹窗/cookie提示时选择接受或关闭
   - 使用滚动查找所需元素

5. 任务完成：
   - 任务完成时使用done动作作为最后一个动作
   - 不要臆想不存在的动作
   - 如果任务需要特定信息，确保在done函数中包含所有内容
   - 如果步骤即将用完，考虑加快速度，始终使用done作为最后动作

6. 视觉上下文：
   - 提供图像时，用于理解页面布局
   - 边界框和标签对应元素索引
   - 每个边界框及其标签使用相同颜色
   - 标签通常在边界框内右上角
   - 视觉上下文帮助验证元素位置和关系

7. 表单填写：
   - 填写输入字段后如果动作序列中断，通常是因为出现建议列表
   - 需要先从建议列表中选择正确的元素

8. 动作执行顺序：
   - 按列表顺序执行动作
   - 每个动作应该是上一个动作的逻辑延续
   - 页面变化会中断序列并返回新状态
   - 仅内容消失则序列继续
   - 只提供到预期页面变化前的动作序列
   - 追求效率，例如一次性填写表单
   - 仅在合理时使用多个动作
"""

    def input_format(self) -> str:
        """返回输入格式说明"""
        return """
输入结构：
1. 当前URL：当前网页地址
2. 可用标签页：打开的浏览器标签页列表
3. 可交互元素：格式如下：
   索引[:]<元素类型>元素文本</元素类型>
   - 索引：用于交互的数字标识符
   - 元素类型：HTML元素类型（button、input等）
   - 元素文本：可见文本或元素描述

示例：
33[:]<button>提交表单</button>
_[:] 不可交互文本

注意：
- 只有带数字索引的元素可以交互
- _[:] 元素提供上下文但不能交互
"""

    def get_system_message(self) -> SystemMessage:
        """获取系统提示信息"""
        time_str = self.current_date.strftime('%Y-%m-%d %H:%M')
        
        return SystemMessage(content=f"""你是一个精确的浏览器自动化代理，通过结构化命令与网站交互。你的职责是：
1. 分析提供的网页元素和结构
2. 规划完成给定任务的动作序列
3. 使用有效的JSON格式响应，包含动作序列和状态评估

当前日期和时间: {time_str}

{self.input_format()}

{self.important_rules()}

可用函数：
{self.default_action_description}

记住：你的响应必须是符合指定格式的有效JSON。序列中的每个动作都必须有效。""")


class AgentMessagePrompt:
    def __init__(
        self,
        state: BrowserState,
        result: Optional[List[ActionResult]] = None,
        include_attributes: list[str] = [],
        max_error_length: int = 400,
        step_info: Optional[dict] = None,
    ):
        self.state = state
        self.result = result
        self.max_error_length = max_error_length
        self.include_attributes = include_attributes
        self.step_info = step_info

    def get_user_message(self) -> HumanMessage:
        """获取用户消息"""
        if self.step_info:
            step_info_description = f'当前步骤: {self.step_info["current_step"]}/{self.step_info["max_steps"]}'
        else:
            step_info_description = ''

        elements_text = self.state.get_clickable_elements_text(
            include_attributes=self.include_attributes
        )
        if elements_text:
            extra = '... 内容截断 - 使用extract_content或scroll获取更多 ...'
            elements_text = f'{extra}\n{elements_text}\n{extra}'
        else:
            elements_text = '空白页面'

        state_description = f"""
{step_info_description}
当前URL: {self.state.url}
可用标签页:
{self.state.tabs}
当前页面可交互元素:
{elements_text}
"""

        if self.result:
            for i, result in enumerate(self.result):
                if result.content:
                    state_description += f'\n动作结果 {i + 1}/{len(self.result)}: {result.content}'
                if result.error:
                    error = result.error[-self.max_error_length:]
                    state_description += f'\n动作错误 {i + 1}/{len(self.result)}: ...{error}'

        if self.state.screenshot:
            return HumanMessage(
                content=[
                    {'type': 'text', 'text': state_description},
                    {
                        'type': 'image_url',
                        'image_url': {'url': f'data:image/png;base64,{self.state.screenshot}'},
                    },
                ]
            )

        return HumanMessage(content=state_description)
