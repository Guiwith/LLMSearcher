from typing import Dict, List, Optional, Union
import logging
import asyncio
from dataclasses import dataclass

from ..Browserservice.service import BrowserService
from ..DomTree.service import DOMService

logger = logging.getLogger(__name__)

@dataclass
class ActionResult:
    """动作执行结果"""
    extracted_content: Optional[str] = None
    error: Optional[str] = None
    is_done: bool = False
    include_in_memory: bool = False

class ControllerService:
    def __init__(self):
        """初始化控制器服务"""
        self.browser_service = BrowserService()
        self.dom_service = None
        self.registry = {}
        self._register_default_actions()
        
    def _register_default_actions(self):
        """注册默认动作"""
        
        @self.action("在当前标签页中搜索Google")
        async def search_google(query: str) -> ActionResult:
            url = f"https://www.google.com/search?q={query}"
            await self.browser_service.navigate(url)
            msg = f"🔍 搜索Google: {query}"
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)
            
        @self.action("导航到指定URL")
        async def navigate_to(url: str) -> ActionResult:
            await self.browser_service.navigate(url)
            msg = f"🔗 导航到: {url}"
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)
            
        @self.action("点击元素")
        async def click_element(index: int) -> ActionResult:
            try:
                state = await self.dom_service.analyze_page()
                if index not in state["interactive_elements"]:
                    raise Exception(f"元素索引 {index} 不存在")
                    
                element = state["interactive_elements"][index]
                await self.browser_service.click(element["xpath"])
                msg = f"🖱️ 点击元素 {index}: {element.get('text', '')}"
                logger.info(msg)
                return ActionResult(extracted_content=msg, include_in_memory=True)
            except Exception as e:
                return ActionResult(error=str(e))
                
        @self.action("输入文本")
        async def input_text(index: int, text: str) -> ActionResult:
            try:
                state = await self.dom_service.analyze_page()
                if index not in state["interactive_elements"]:
                    raise Exception(f"元素索引 {index} 不存在")
                    
                element = state["interactive_elements"][index]
                await self.browser_service.type_text(element["xpath"], text)
                msg = f"⌨️ 在元素 {index} 中输入: {text}"
                logger.info(msg)
                return ActionResult(extracted_content=msg, include_in_memory=True)
            except Exception as e:
                return ActionResult(error=str(e))
                
        @self.action("滚动页面")
        async def scroll_page(amount: Optional[int] = None) -> ActionResult:
            try:
                page = await self.browser_service.get_current_page()
                if amount:
                    await page.evaluate(f"window.scrollBy(0, {amount});")
                else:
                    await page.keyboard.press("PageDown")
                    
                scroll_amount = f"{amount}像素" if amount else "一页"
                msg = f"🔍 向下滚动 {scroll_amount}"
                logger.info(msg)
                return ActionResult(extracted_content=msg, include_in_memory=True)
            except Exception as e:
                return ActionResult(error=str(e))
                
        @self.action("提取页面内容")
        async def extract_content(include_links: bool = False) -> ActionResult:
            try:
                page = await self.browser_service.get_current_page()
                content = await self.dom_service.get_page_content()
                msg = f"📄 提取页面内容:\n{content}"
                logger.info(msg)
                return ActionResult(extracted_content=msg)
            except Exception as e:
                return ActionResult(error=str(e))

    def action(self, description: str):
        """动作注册装饰器"""
        def decorator(func):
            self.registry[func.__name__] = {
                "description": description,
                "function": func
            }
            return func
        return decorator
        
    async def execute_action(self, action_name: str, **params) -> ActionResult:
        """执行指定动作"""
        if action_name not in self.registry:
            return ActionResult(error=f"未知动作: {action_name}")
            
        try:
            action = self.registry[action_name]["function"]
            result = await action(**params)
            return result
        except Exception as e:
            logger.error(f"执行动作 {action_name} 失败: {str(e)}")
            return ActionResult(error=str(e))
            
    async def execute_actions(self, actions: List[Dict]) -> List[ActionResult]:
        """执行多个动作"""
        results = []
        
        for action in actions:
            action_name = action.get("action")
            params = action.get("params", {})
            
            result = await self.execute_action(action_name, **params)
            results.append(result)
            
            if result.error or result.is_done:
                break
                
            await asyncio.sleep(1)  # 动作之间的延迟
            
        return results 