from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .service import DOMService
from ..Browserservice.service import BrowserService
import asyncio

class DOMAnalysisView(APIView):
    """DOM分析API视图"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.browser_service = None
        self.dom_service = None
        
    async def _init_services(self):
        """初始化服务"""
        if not self.browser_service:
            self.browser_service = BrowserService()
            self.browser_service.start_browser()
            self.dom_service = DOMService(self.browser_service.page)

    async def post(self, request):
        """处理DOM分析请求
        
        请求体格式：
        {
            "url": "要分析的页面URL",
            "highlight_elements": true,
            "analyze_type": "full|interactive|structure"
        }
        """
        try:
            url = request.data.get('url')
            highlight_elements = request.data.get('highlight_elements', True)
            analyze_type = request.data.get('analyze_type', 'full')
            
            if not url:
                return Response(
                    {"error": "URL不能为空"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            await self._init_services()
            
            # 导航到目标页面
            await self.browser_service.navigate(url)
            
            # 分析页面DOM
            analysis_result = await self.dom_service.analyze_page(
                highlight_elements=highlight_elements
            )
            
            # 根据分析类型返回不同的结果
            if analyze_type == 'interactive':
                return Response({
                    "interactive_elements": analysis_result["interactive_elements"]
                })
            elif analyze_type == 'structure':
                return Response({
                    "dom_tree": analysis_result["dom_tree"]
                })
            else:  # full
                return Response(analysis_result)
                
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    async def delete(self, request):
        """清理资源"""
        try:
            if self.browser_service:
                self.browser_service.close()
                self.browser_service = None
                self.dom_service = None
            return Response({"status": "success"})
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
