from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import openai
import json
import time
import requests
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

class LLMClient:
    """统一的 LLM 客户端接口"""
    def __init__(self, base_url="http://localhost:11434", model="qwen:7b", 
                 timeout=10, max_retries=3):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        
    def _make_request(self, endpoint, payload):
        """带重试机制的请求"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    f"{self.base_url}{endpoint}",
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                print(f"请求失败，正在重试 ({attempt + 1}/{self.max_retries}): {e}")
                time.sleep(1)
        
    def ChatCompletion(self):
        return self
        
    def create(self, messages, **kwargs):
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": kwargs.get('temperature', 0.7),
                    "stream": False
                },
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                print(f"API请求失败: 状态码 {response.status_code}")
                print(f"响应内容: {response.text}")
                response.raise_for_status()
                
            result = response.json()
            return result
            
        except Exception as e:
            print(f"LLM API 调用错误: {e}")
            print(f"请求URL: {self.base_url}/v1/chat/completions")
            print(f"请求模型: {self.model}")
            return {
                'choices': [{
                    'message': {
                        'content': '{}'
                    }
                }]
            }

class WorkAssistant:
    def __init__(self, api_base="http://localhost:11434", model="qwen:7b"):
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service)
        self.driver.maximize_window()
        self.llm_client = LLMClient(base_url=api_base, model=model)
        self.current_task = None
        self.collected_info = []
        self.is_paused = False
        
    def pause(self):
        """暂停执行"""
        self.is_paused = True
        
    def resume(self):
        """恢复执行"""
        self.is_paused = False
        
    def get_page_elements(self):
        """获取页面所有可交互元素及其位置信息"""
        return self.driver.execute_script("""
            function getElementInfo(element) {
                const rect = element.getBoundingClientRect();
                return {
                    tag: element.tagName.toLowerCase(),
                    text: element.textContent.trim(),
                    href: element.href || '',
                    position: {
                        x: rect.left + window.pageXOffset,
                        y: rect.top + window.pageYOffset,
                        width: rect.width,
                        height: rect.height
                    },
                    isClickable: (
                        element.tagName === 'A' || 
                        element.tagName === 'BUTTON' ||
                        element.onclick != null ||
                        window.getComputedStyle(element).cursor === 'pointer'
                    )
                };
            }
            
            const elements = document.querySelectorAll('a, button, input, [role="button"], [onclick]');
            return Array.from(elements).map(getElementInfo);
        """)

    def ask_llm(self, task, page_elements):
        """询问LLM下一步应该点击什么"""
        # 首先分析任务
        task_analysis_prompt = f"""
        请分析以下任务并提取关键信息：
        {task}
        
        返回JSON格式：
        {{
            "keywords": "搜索关键词",
            "target_info": "需要找到的具体信息",
            "success_criteria": "任务完成的判断标准",
            "target_url": "目标网站的域名关键词"
        }}
        """
        
        analysis = self.llm_client.ChatCompletion().create(
            messages=[{
                "role": "system",
                "content": "你是一个任务分析助手，帮助提取任务中的关键信息。对于需要访问特定网站的任务，请确保提供目标网站的域名关键词。"
            }, {
                "role": "user",
                "content": task_analysis_prompt
            }]
        )
        
        try:
            analysis_content = analysis['choices'][0]['message']['content'].strip()
            if '```' in analysis_content:
                analysis_content = analysis_content.split('```')[1]
                if analysis_content.startswith('json'):
                    analysis_content = analysis_content[4:]
            analysis_content = analysis_content.strip()
            task_info = json.loads(analysis_content)
            
            # 根据当前页面状态决定下一步操作
            action_prompt = f"""
            当前任务：
            - 搜索关键词：{task_info['keywords']}
            - 目标信息：{task_info['target_info']}
            - 完成标准：{task_info['success_criteria']}
            - 目标网站：{task_info['target_url']}
            
            当前页面URL：{self.driver.current_url}
            
            当前页面可交互元素：
            {json.dumps(page_elements, ensure_ascii=False, indent=2)}
            
            请严格按照以下规则决定下一步操作：
            
            1. 如果在百度搜索页面且有搜索结果：
               - 查找包含目标网站域名的链接
               - 返回点击该链接的操作
            
            2. 如果在百度首页：
               - 返回搜索操作
            
            3. 如果已经到达目标网站：
               - 返回完成状态
            
            必须且只能返回以下JSON格式之一：
            
            1. 需要搜索时：
            {{"complete": false, "element_index": 0, "reason": "搜索相关信息", "need_input": true, "input_text": "具体的搜索关键词"}}
            
            2. 需要点击某个元素时：
            {{"complete": false, "element_index": 数字, "reason": "点击原因", "need_input": false}}
            
            3. 仅当到达目标网站时：
            {{"complete": true, "result": "成功访问目标网站"}}
            
            注意：
            1. 在百度搜索结果页面时，优先查找并点击目标网站的官方链接
            2. 只有当当前URL包含目标网站域名时，才能返回complete=true
            3. 如果找不到合适的链接，继续返回搜索操作
            """
            
            response = self.llm_client.ChatCompletion().create(
                messages=[{
                    "role": "system",
                    "content": "你是一个自动化助手。在搜索结果页面时，应该查找并点击目标网站的链接。只有成功访问到目标网站时，才能标记任务完成。"
                }, {
                    "role": "user",
                    "content": action_prompt
                }]
            )
            
            content = response['choices'][0]['message']['content'].strip()
            if '```' in content:
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
            content = content.strip()
            
            result = json.loads(content)
            
            # 验证任务完成状态
            if result.get("complete"):
                current_url = self.driver.current_url.lower()
                target_url = task_info['target_url'].lower()
                if target_url not in current_url:
                    # 如果在搜索结果页面，尝试找到并点击目标链接
                    if "www.baidu.com" in current_url:
                        for idx, element in enumerate(page_elements):
                            if target_url in element.get('href', '').lower():
                                return {
                                    "complete": False,
                                    "element_index": idx,
                                    "reason": f"点击{task_info['target_url']}的链接",
                                    "need_input": False
                                }
                
                    # 如果没找到合适的链接，继续搜索
                    result['complete'] = False
                    result['element_index'] = 0
                    result['reason'] = "继续搜索目标网站"
                    result['need_input'] = True
                    result['input_text'] = task_info['keywords']
                
            return result
            
        except Exception as e:
            print(f"解析LLM响应时出错: {e}")
            return {
                "complete": False,
                "element_index": 0,
                "reason": "解析错误，使用搜索功能",
                "need_input": True,
                "input_text": task
            }
            
    def extract_information(self):
        """提取当前页面的相关信息"""
        # 获取页面文本内容
        page_text = self.driver.find_element(By.TAG_NAME, "body").text
        
        # 让LLM提取相关信息
        prompt = f"""
        任务背景: {self.current_task}
        页面内容: {page_text}
        
        请提取与任务相关的关键信息。
        """
        
        response = self.llm_client.ChatCompletion().create(
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            # 直接返回内容，不需要解析为JSON
            return response['choices'][0]['message']['content']
        except Exception as e:
            print(f"提取信息时出错: {e}")
            return "无法提取有效信息"

    def execute_task(self, task):
        """执行具体任务"""
        self.driver.get("https://www.baidu.com")  # 示例起始页面
        
        while True:
            time.sleep(2)
            elements = self.get_page_elements()
            action = self.ask_llm(task, elements)
            
            if action.get("complete"):
                info = self.extract_information()
                self.collected_info.append(info)
                print(f"任务完成！找到信息：{info}")
                return self.collected_info
            
            element_index = action["element_index"]
            target_element = elements[element_index]
            
            try:
                # 找到对应的Selenium元素，使用更多的定位方式
                element = None
                locator_strategies = [
                    (By.XPATH, f"//*[contains(text(), '{target_element['text']}')]"),
                    (By.XPATH, f"//a[contains(@href, '{target_element['href']}')]"),
                    (By.CSS_SELECTOR, f"[title*='{target_element['text']}']"),
                    (By.LINK_TEXT, target_element['text'])
                ]
                
                for strategy, locator in locator_strategies:
                    try:
                        element = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((strategy, locator))
                        )
                        if element:
                            break
                    except:
                        continue
                
                if not element:
                    print(f"无法找到元素: {target_element['text']}")
                    return
                
                # 确保元素可见和可点击
                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(0.5)  # 等待滚动完成
                
                # 尝试不同的点击方法
                click_methods = [
                    lambda: element.click(),
                    lambda: ActionChains(self.driver).move_to_element(element).click().perform(),
                    lambda: self.driver.execute_script("arguments[0].click();", element)
                ]
                
                for click_method in click_methods:
                    try:
                        click_method()
                        break
                    except:
                        continue
                
                time.sleep(2)  # 等待页面加载
                
            except Exception as e:
                print(f"点击操作失败: {e}")
                continue  # 继续下一次尝试

    def close(self):
        self.driver.quit()

    def is_task_complete(self, task, current_state):
        """询问LLM任务是否完成"""
        prompt = f"""
        任务: {task}
        当前状态: {current_state}
        请判断任务是否已经完成？
        只返回 true 或 false
        """
        response = self.ask_llm(prompt)
        return response.lower() == "true"

    def safe_click(self, element, max_retries=3):
        """安全的点击操作"""
        for i in range(max_retries):
            try:
                element.click()
                return True
            except Exception as e:
                print(f"点击失败，尝试第{i+1}次: {e}")
                time.sleep(1)
        return False

    def get_element_attributes(self, element):
        """获取元素的详细属性"""
        return {
            'aria-label': element.get_attribute('aria-label'),
            'title': element.get_attribute('title'),
            'role': element.get_attribute('role'),
            'class': element.get_attribute('class'),
            # 添加更多需要的属性
        }

# 使用示例
def main():
    # 默认使用本地 Ollama
    assistant = WorkAssistant()
    
    # 或者指定其他 API 端点
    # assistant = WorkAssistant(api_base="http://your-vllm-server:8000")
    
    try:
        task = "在百度上搜索'Python教程'，然后点击第一个非广告结果"
        assistant.execute_task(task)
    finally:
        assistant.close()

if __name__ == "__main__":
    main()
