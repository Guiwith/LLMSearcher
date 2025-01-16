import requests
import json
from typing import Dict, List, Optional, Union

class LLMService:
    def __init__(self, base_url: str = "http://172.31.118.255:11434"):
        """初始化LLM服务
        
        Args:
            base_url: Ollama服务的基础URL
        """
        self.base_url = base_url
        self.api_url = f"{base_url}/api/chat"
        
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "glm4:latest",
        temperature: float = 0.7,
        stream: bool = False,
        **kwargs
    ) -> Dict:
        """创建聊天完成请求
        
        Args:
            messages: 消息历史列表
            model: 模型名称
            temperature: 温度参数
            stream: 是否使用流式响应
            **kwargs: 其他参数
        
        Returns:
            Dict: OpenAI格式的响应
        """
        try:
            payload = {
                "model": model,
                "messages": messages,
                "stream": stream,
                "temperature": temperature,
                **kwargs
            }
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                # 将Ollama响应转换为OpenAI格式
                result = response.json()
                return {
                    "id": "chatcmpl-" + model,
                    "object": "chat.completion",
                    "created": result.get("created", 0),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": result.get("message", {}).get("content", "")
                        },
                        "finish_reason": "stop"
                    }],
                    "usage": result.get("usage", {})
                }
            else:
                raise Exception(f"API调用失败: {response.status_code} - {response.text}")
                
        except Exception as e:
            raise Exception(f"LLM服务错误: {str(e)}")
    
    def get_models(self) -> List[Dict]:
        """获取可用模型列表
        
        Returns:
            List[Dict]: 可用模型列表
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                return [{"id": model["name"], "name": model["name"]} for model in models]
            else:
                raise Exception(f"获取模型列表失败: {response.status_code} - {response.text}")
        except Exception as e:
            raise Exception(f"获取模型列表错误: {str(e)}")
