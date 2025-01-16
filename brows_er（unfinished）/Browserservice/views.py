from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .service import BrowserService
import asyncio

class BrowserControlView(APIView):
    """浏览器控制API视图"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.browser_service = BrowserService()
        
    def post(self, request):
        """处理浏览器控制请求
        
        请求体格式：
        {
            "action": "start|navigate|click|type|get_content|close",
            "params": {
                // 根据action不同而不同的参数
            }
        }
        """
        try:
            action = request.data.get('action')
            params = request.data.get('params', {})
            
            if not action:
                return Response(
                    {"error": "必须指定action"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 执行对应的异步操作
            result = asyncio.run(self._execute_action(action, params))
            return Response(result)
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    async def _execute_action(self, action: str, params: dict) -> dict:
        """执行浏览器操作
        
        Args:
            action: 操作类型
            params: 操作参数
        """
        try:
            if action == "start":
                headless = params.get('headless', False)
                self.browser_service.start_browser(headless=headless)
                return {"status": "success", "message": "浏览器启动成功"}
                
            elif action == "navigate":
                url = params.get('url')
                if not url:
                    raise ValueError("URL不能为空")
                result = await self.browser_service.navigate(url)
                return result
                
            elif action == "click":
                selector = params.get('selector')
                if not selector:
                    raise ValueError("选择器不能为空")
                await self.browser_service.click(selector)
                return {"status": "success", "message": "点击成功"}
                
            elif action == "type":
                selector = params.get('selector')
                text = params.get('text')
                if not selector or text is None:
                    raise ValueError("选择器和文本不能为空")
                await self.browser_service.type_text(selector, text)
                return {"status": "success", "message": "输入成功"}
                
            elif action == "get_content":
                content = await self.browser_service.get_page_content()
                return content
                
            elif action == "close":
                self.browser_service.close()
                return {"status": "success", "message": "浏览器已关闭"}
                
            else:
                raise ValueError(f"不支持的操作: {action}")
                
        except Exception as e:
            raise Exception(f"执行操作失败: {str(e)}")
