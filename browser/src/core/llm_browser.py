import requests
from typing import List, Dict
import json
from .web_crawler import WebCrawler

class LLMBrowser:
    def __init__(self, model: str = "glm4:latest"):
        self.llm_url = "http://172.31.118.255:11434/v1/chat/completions"
        self.headers = {"Content-Type": "application/json"}
        self.model = model
        self.web_crawler = WebCrawler()
        
    def _call_llm(self, prompt: str) -> str:
        """调用Ollama API"""
        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}]
            }
            response = requests.post(self.llm_url, headers=self.headers, json=payload)
            return response.json()["choices"][0]["message"]["content"]
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接到Ollama服务，请确保Ollama已启动且运行在端口11434")
        except Exception as e:
            raise Exception(f"调用LLM时发生错误: {str(e)}")
    
    def analyze_query(self, user_query: str) -> List[str]:
        """分析用户需求"""
        prompt = f"""请分析以下需求,只回答1个最核心的用户可能想搜索的搜索关键词。
        当前需求内容：{user_query}
        请严格按照以下格式返回关键词，不要包含序号、逗号或其他文字：
        关键词"""
        
        response = self._call_llm(prompt)
        return self._parse_keywords(response)
    
    def search_web(self, keywords: List[str]) -> List[Dict]:
        """执行网页搜索"""
        return self.web_crawler.search_web(keywords)
    
    def select_pages(self, search_results: List[Dict], user_query: str) -> List[str]:
        """选择最相关的页面"""
        prompt = f"""基于用户需求，从搜索结果中选择最相关的页面。
        用户需求：{user_query}
        搜索结果：{json.dumps(search_results, ensure_ascii=False)}
        请只返回选中页面的URL，每行一个。"""
        
        response = self._call_llm(prompt)
        urls = [url.strip() for url in response.split('\n') if url.strip().startswith('http')]
        return urls[:3]  # 最多返回前3个URL
    
    def crawl_page_content(self, url: str) -> Dict:
        """爬取页面内容"""
        return self.web_crawler.crawl_page_content(url)
    
    def summarize_content(self, content: str, user_query: str) -> str:
        """总结内容"""
        prompt = f"""请根据用户需求，总结以下内容的要点：
        用户需求：{user_query}
        
        内容：
        {content[:8000]}  # 限制内容长度
        
        请提供简洁的总结："""
        
        return self._call_llm(prompt)
    
    def _parse_keywords(self, llm_response: str) -> List[str]:
        """解析LLM返回的关键词"""
        try:
            response_text = llm_response.strip()
            response_text = response_text.replace(',', ' ').replace('，', ' ')
            keywords = [k.strip() for k in response_text.split() if k.strip()]
            if keywords:
                keywords = [keywords[0]]
            else:
                raise ValueError("未能从LLM响应中提取到关键词")
            return keywords
        except Exception as e:
            raise Exception(f"解析关键词时发生错误: {str(e)}") 