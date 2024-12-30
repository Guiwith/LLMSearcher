from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import time
import requests
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from selenium.common.exceptions import TimeoutException
from datetime import datetime
import re
import functools

# 定义任务相关的数据结构
class ActionType(Enum):
    """严格定义所有可能的动作类型"""
    SEARCH = "search"
    CLICK_RESULT = "click_result"
    CLICK_NEXT = "click_next"     # 点击下一个搜索结果
    EXTRACT_TEXT = "extract_text"
    BACK = "back"                 # 返回上一页
    VERIFY = "verify"            # 验证当前页面

@dataclass
class SearchParams:
    """搜索操作参数"""
    keywords: str

@dataclass
class ClickParams:
    """点击操作参数"""
    index: str = "0"  # 默认点击第一个结果
    link_text: str = ""  # 允许空的链接文本

@dataclass
class ExtractParams:
    """提取操作参数"""
    selector: str
    attribute: str = "text"
    keywords: str = ""

@dataclass
class Step:
    """单个任务步骤"""
    action: ActionType
    params: Union[SearchParams, ClickParams, ExtractParams]
    retry_count: int = 0
    max_retries: int = 3

@dataclass
class TaskPlan:
    """任务计划"""
    steps: List[Step]
    task_id: str
    created_at: float

@dataclass
class SearchConfig:
    """搜索配置"""
    deep_search: bool = False  # 是否启用深度搜索
    max_pages: int = 3        # 最大搜索页数
    max_results: int = 5      # 每页最大结果数
    max_depth: int = 2        # 最大深度
    quality_threshold: float = 0.6  # 质量评分阈值

class TaskParser:
    """任务解析器"""
    @classmethod
    def get_prompt_template(cls, task: str) -> List[Dict[str, str]]:
        """获取提示词模板"""
        return [
            {
                "role": "system",
                "content": """你是一个搜索任务规划器。必须严格按照以下规则输出JSON：

输出格式规范：
{
  "steps": [
    {
      "action": "search",
      "params": {
        "keywords": "具体的搜索关键词"
      }
    },
    {
      "action": "click_result",
      "params": {
        "index": "0"
      }
    },
    {
      "action": "extract_text",
      "params": {
        "selector": ".content",
        "attribute": "text"
      }
    },
    {
      "action": "back",
      "params": {}
    }
  ]
}

严格规则：
1. 动作类型限制：
- search: 执行搜索，必须包含 keywords 参数
- click_result: 点击结果，必须包含 index 参数（从0开始）
- extract_text: 提取文本，必须包含 selector 和 attribute 参数
- back: 返回上一页，无需参数

2. 参数规范：
search:
- keywords: 必须是具体的中文搜索词，不能包含占位符
- 禁止使用 [xxx] 这样的占位符

click_result:
- index: 必须是字符串格式的数字，如 "0", "1", "2"
- 禁止使用变量或计算表达式

extract_text:
- selector: 必须是有效的CSS选择器，如 ".content", "article", ".text"
- attribute: 必须是 "text"

3. 禁止事项：
- 不能使用未定义的动作类型
- 不能省略任何必需的参数
- 不能添加未定义的参数
- 不能使用特殊字符或HTML标签
- 不能包含注释
- 不能使用换行或缩进
- 不能使用markdown代码块

4. 搜索关键词规则：
- 必须使用中文
- 必须具体明确
- 必须包含完整信息
- 禁止使用模糊词语
- 长度不超过50个字符

示例任务：搜索最新的AI新闻
正确示例：
{"steps":[{"action":"search","params":{"keywords":"人工智能最新发展新闻 2024"}},{"action":"click_result","params":{"index":"0"}},{"action":"extract_text","params":{"selector":".article","attribute":"text"}},{"action":"back","params":{}}]}

错误示例：
{"steps":[{"action":"search","params":{"keywords":"[网站名]的AI新闻"}},{"action":"click","params":{"index":0}},{"action":"extract","params":{"selector":"div"}}]}"""
            },
            {
                "role": "user",
                "content": task
            }
        ]

    @staticmethod
    def parse_llm_response(response: str) -> List[Step]:
        """解析LLM返回的JSON为Step列表"""
        try:
            # 1. 清理响应文本
            def clean_response(text):
                """清理和修复JSON响应，确保生成有效的JSON格式"""
                try:
                    # 1. 初始清理
                    def initial_clean(text):
                        # 移除markdown代码块标记
                        text = re.sub(r'```.*?\n|```', '', text)
                        # 移除所有空白字符
                        text = re.sub(r'\s+', '', text)
                        # 移除可能的注释
                        text = re.sub(r'//.*?(?=\n|\r|$)|/\*.*?\*/', '', text)
                        return text
                    
                    # 2. 提取JSON结构
                    def extract_json(text):
                        # 尝试找到完整的JSON结构
                        pattern = r'\{.*"steps"\s*:\s*\[.*?\]\s*\}'
                        match = re.search(pattern, text, re.DOTALL)
                        if match:
                            return match.group(0)
                        return text
                    
                    # 3. 修复常见的JSON错误
                    def fix_json_structure(text):
                        
                        # 确保键名有引号
                        text = re.sub(r'([{,])(\w+):', r'\1"\2":', text)
                        
                        # 修复布尔值格式
                        text = text.replace('True', 'true').replace('False', 'false')
                        
                        # 修复可能的中文引号
                        text = text.replace('"', '"').replace('"', '"')
                        
                        return text
                    
                    # 4. 修复steps数组结构
                    def fix_steps_array(text):
                        # 确保steps数组存在且格式正确
                        if '"steps":[' in text:
                            # 计算左右方括号的数量
                            left_brackets = text.count('[')
                            right_brackets = text.count(']')
                            
                            # 如果方括号不匹配，添加缺失的右方括号
                            if left_brackets > right_brackets:
                                text += ']' * (left_brackets - right_brackets)
                            
                            # 确保JSON对象正确闭合
                            if not text.endswith('}'):
                                text += '}'
                        
                        return text
                    
                    # 5. 验证最终的JSON结构
                    def validate_json(text):
                        try:
                            # 尝试解析JSON
                            data = json.loads(text)
                            
                            # 确保有steps键且为数组
                            if not isinstance(data.get('steps', None), list):
                                raise ValueError("Missing or invalid 'steps' array")
                            
                            # 验证每个步骤的结构
                            for step in data['steps']:
                                if not isinstance(step, dict):
                                    continue
                                
                                # 确保action和params存在
                                if 'action' not in step:
                                    continue
                                
                                # 如果没有params，添加空对象
                                if 'params' not in step:
                                    step['params'] = {}
                            
                            # 重新序列化为格式化的JSON
                            return json.dumps(data)
                            
                        except json.JSONDecodeError as e:
                            print(f"JSON验证失败: {e}")
                            raise
                    
                    # 执行清理流程
                    text = initial_clean(text)
                    text = extract_json(text)
                    text = fix_json_structure(text)
                    text = fix_steps_array(text)
                    
                    # 打印中间结果（用于调试）
                    print(f"清理后的JSON: {text}")
                    
                    # 最终验证
                    text = validate_json(text)
                    
                    return text
                    
                except Exception as e:
                    print(f"JSON清理失败: {e}")
                    print(f"原始文本: {text}")
                    raise ValueError(f"无法生成有效的JSON: {str(e)}")

            # 2. 清理并解析JSON
            cleaned_response = clean_response(response)
            print(f"清理后的JSON: {cleaned_response}")
            data = json.loads(cleaned_response)

            # 3. 验证JSON结构
            if not isinstance(data, dict) or "steps" not in data:
                raise ValueError("JSON结构不正确")

            # 4. 解析步骤
            steps = []
            for step_data in data["steps"]:
                if not isinstance(step_data, dict):
                    continue
                
                action_name = step_data.get("action")
                if not action_name:
                    continue
                
                try:
                    action = ActionType(action_name)
                    params = step_data.get("params", {})
                    
                    # 确保params中的所有值都是字符串
                    if isinstance(params, dict):
                        params = {
                            key: str(value) if value is not None else ""
                            for key, value in params.items()
                        }
                    
                    # 为不同的动作类型设置默认参数
                    if action == ActionType.CLICK_RESULT:
                        # 为 click_result 添加默认参数
                        params["index"] = str(params.get("index", "0"))
                        # 如果 link_text 为空，使用默认值
                        if not params.get("link_text"):
                            params["link_text"] = ".*"  # 使用通配符匹配任何标题
                    
                    # 创建对应的Step对象
                    if action == ActionType.EXTRACT_TEXT:
                        step = Step(action=action, params=ExtractParams(**params))
                    elif action == ActionType.CLICK_RESULT:
                        step = Step(action=action, params=ClickParams(**params))
                    elif action == ActionType.SEARCH:
                        step = Step(action=action, params=SearchParams(**params))
                    elif action == ActionType.BACK:
                        step = Step(action=action, params={})
                    else:
                        continue
                    
                    steps.append(step)
                except Exception as e:
                    print(f"步骤解析错误: {e}")
                    continue

            if not steps:
                raise ValueError("未能解析出有效的步骤")
            
            return steps
            
        except Exception as e:
            raise ValueError(f"任务解析失败: {str(e)}\n原始响应: {response}")

class LLMClient:
    """统一的 LLM 客户端接口"""
    def __init__(self, base_url="http://172.31.118.255:11434", model="glm4:latest", 
                 timeout=30, max_retries=3):
        self.base_url = base_url.rstrip('/')
        self.model = model.strip()
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
        """发送请求到LLM服务"""
        try:
            response = self.session.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": kwargs.get('temperature', 0.7),
                    "stream": False
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"请求失败: {e}")
            raise
    
    def _get_default_response(self):
        """返回默认的响应格式"""
        return {
            'choices': [{
                'message': {
                    'content': json.dumps({
                        "complete": False,
                        "element_index": 0,
                        "reason": "继续搜索",
                        "need_input": True,
                        "input_text": "百度搜索"
                    })
                }
            }]
        }

def retry_on_error(max_retries=3, delay=1):
    """重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    print(f" {attempt + 1} 次尝试失败: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(delay)
            raise last_error
        return wrapper
    return decorator

class WorkAssistant:
    def __init__(self, api_base: str = "http://localhost:11434", 
                 model: str = "glm4:latest",
                 log_level: int = logging.INFO,
                 auto_close_browser: bool = True,
                 headless: bool = False,
                 search_config: Optional[SearchConfig] = None):
        # 创建 LLMClient 实例
        self.llm_client = LLMClient(base_url=api_base, model=model)
        
        # 初始化其他属性
        self.setup_logging(log_level)
        self.collected_info = []
        self.current_task = None
        self.task_parser = TaskParser()
        self.driver = None
        self.wait = None
        self.auto_close_browser = auto_close_browser
        self.headless = headless
        self.search_config = search_config or SearchConfig()

    def setup_logging(self, log_level: int) -> None:
        """设置日志系统"""
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_driver(self) -> None:
        """设置浏器驱动"""
        try:
            chrome_options = webdriver.ChromeOptions()
            
            # 基本设置
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # SSL设置
            chrome_options.add_argument('--ignore-ssl-errors=yes')
            chrome_options.add_argument('--ignore-certificate-errors')
            
            # 性能优化
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-software-rasterizer')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-notifications')
            chrome_options.add_argument('--disable-popup-blocking')
            
            # 无头模式特定设置
            if self.headless:
                chrome_options.add_argument('--headless=new')  # 使用新版无头模式
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_argument('--start-maximized')
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_argument('--enable-javascript')
                chrome_options.add_argument('--hide-scrollbars')
                
                # 添加用户代理
                chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                
                # 禁用图片加载以提高速度
                chrome_options.add_argument('--blink-settings=imagesEnabled=false')
                
                # 设置 DOM 大小限制
                chrome_options.add_argument('--dom-automation')
                chrome_options.add_argument('--remote-debugging-port=9222')
            
            # 创建驱动
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # 设置窗口大小和位置
            if self.headless:
                self.driver.set_window_size(1920, 1080)
                self.driver.set_window_position(0, 0)
            
            # 设置超时和等待
            self.driver.set_page_load_timeout(30)
            self.driver.implicitly_wait(10)
            self.wait = WebDriverWait(self.driver, 10)
            
            # 设置 JavaScript 执行超时
            self.driver.set_script_timeout(30)
            
            # 初始化动作链
            self.actions = ActionChains(self.driver)
            
            # 验证浏览器是否正常工作
            self.driver.get("https://www.baidu.com")
            if "百度一下" not in self.driver.page_source:
                raise Exception("浏览器初始化失败：无法加载百度首页")
            
        except Exception as e:
            self.logger.error(f"浏览器驱动初始化失败: {e}")
            if self.driver:
                self.driver.quit()
            raise

    def parse_task(self, task: str) -> List[Step]:
        """解析用户任务"""
        try:
            messages = self.task_parser.get_prompt_template(task)
            response = self.create(messages=messages)
            content = response['choices'][0]['message']['content']
            return self.task_parser.parse_llm_response(content)
        except Exception as e:
            self.logger.error(f"任务解析失败: {e}")
            raise

    def execute_step(self, step: Step) -> bool:
        """执行单个步骤，返回是否成功"""
        self.logger.info(f"执行步骤: {step}")
        try:
            if step.action == ActionType.SEARCH:
                return self._execute_search(step.params)
            elif step.action == ActionType.CLICK_RESULT:
                return self._execute_click_result(step.params)
            elif step.action == ActionType.EXTRACT_TEXT:
                return self._execute_extract_text(step.params)
            elif step.action == ActionType.BACK:
                return self._execute_back()
            else:
                self.logger.error(f"未知的动作类型: {step.action}")
                return False
        except Exception as e:
            self.logger.error(f"步骤执行失败: {e}")
            return False

    def create(self, messages, **kwargs):
        """代理到 LLMClient 的 create 方法"""
        return self.llm_client.create(messages=messages, **kwargs)

    def _execute_search(self, params: SearchParams) -> bool:
        """执行搜索操作"""
        try:
            # 确保在百度首页
            if "www.baidu.com" not in self.driver.current_url:
                self.driver.get("https://www.baidu.com")
                # 等待页面加载完成
                WebDriverWait(self.driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                time.sleep(2)
            
            # 基本搜索逻辑
            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "kw"))
            )
            
            # 使用 JavaScript 清除和设置搜索框的值
            self.driver.execute_script("arguments[0].value = '';", search_box)
            self.driver.execute_script(f"arguments[0].value = '{params.keywords}';", search_box)
            
            # 使用 JavaScript 点击搜索按钮
            search_button = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "su"))
            )
            self.driver.execute_script("arguments[0].click();", search_button)
            
            # 等待搜索结果加载
            WebDriverWait(self.driver, 10).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, ".result,.c-container")) > 0
            )
            
            # 存储原始搜索结果页面的窗口句柄
            search_results_handle = self.driver.current_window_handle
            processed_urls = set()  # 用于跟踪已处理的URL
            all_results = []
            current_page = 1
            results_count = 0  # 用于跟踪处理的结果数量

            while current_page <= self.search_config.max_pages and results_count < self.search_config.max_results:
                try:
                    # 确保在搜索结果页面
                    if self.driver.current_window_handle != search_results_handle:
                        self.driver.switch_to.window(search_results_handle)
                    
                    # 等待页面加载完成
                    time.sleep(2)
                    
                    # 获取当前页面的所有结果
                    results = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".result,.c-container"))
                    )
                    
                    self.logger.info(f"当前页面找到 {len(results)} 个结果")

                    # 处理每个搜索结果
                    for result in results:
                        if results_count >= self.search_config.max_results:
                            break
                            
                        try:
                            # 跳过广告
                            if "广告" in result.text:
                                continue

                            # 获取链接URL
                            link = WebDriverWait(result, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href]"))
                            )
                            url = link.get_attribute("href")
                            
                            # 跳过已处理的URL
                            if not url or url in processed_urls:
                                continue
                                
                            processed_urls.add(url)
                            results_count += 1
                            
                            # 获取标题文本
                            title = link.text or "无标题"
                            self.logger.info(f"处理第 {results_count} 个结果: {title} ({url})")
                            
                            # 在新标签页中打开链接
                            self.driver.execute_script(f'window.open("{url}", "_blank");')
                            time.sleep(1)
                            
                            # 切换到新标签页
                            self.driver.switch_to.window(self.driver.window_handles[-1])
                            
                            try:
                                # 等待页面加载
                                WebDriverWait(self.driver, 10).until(
                                    lambda d: d.execute_script("return document.readyState") == "complete"
                                )
                                
                                # 提取内容
                                content = self.driver.find_element(By.TAG_NAME, "body").text
                                quality_score = self.evaluate_content_quality(content, params.keywords)
                                
                                if quality_score >= self.search_config.quality_threshold:
                                    all_results.append({
                                        "url": url,
                                        "data": content[:5000],
                                        "quality_score": quality_score,
                                        "title": title
                                    })
                                    
                            finally:
                                # 关闭当前标签页
                                self.driver.close()
                                # 切回搜索结果页
                                self.driver.switch_to.window(search_results_handle)

                        except Exception as e:
                            self.logger.warning(f"处理搜索结果失败: {e}")
                            # 确保返回搜索结果页
                            if self.driver.current_window_handle != search_results_handle:
                                self.driver.close()
                                self.driver.switch_to.window(search_results_handle)
                            continue

                    # 检查是否需要翻页
                    if current_page < self.search_config.max_pages and results_count < self.search_config.max_results:
                        try:
                            next_button = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.ID, "page-next"))
                            )
                            if next_button.is_displayed() and next_button.is_enabled():
                                next_button.click()
                                current_page += 1
                                time.sleep(2)
                            else:
                                break
                        except:
                            break
                    else:
                        break

                except Exception as e:
                    self.logger.error(f"处理搜索页面失败: {e}")
                    break

            # 按质量分数排序并保存结果
            all_results.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
            self.collected_info.extend(all_results)
            
            return True
            
        except Exception as e:
            self.logger.error(f"搜索操作失败: {e}")
            return False

    def verify_url(self, target_text: str, current_url: str) -> bool:
        """使用LLM验证当前URL是否符合目标要求"""
        try:
            prompt = [
                {
                    "role": "system",
                    "content": """你是一个URL验证助手。判断当前页面是否是用户想要访问的目标网站。必须严格按照以下格式输出：
{"is_correct":true/false,"reason":"原因"}

规则：
1. 输出格式：
- 必须是合法的JSON
- 必须包含is_correct和reason字段
- is_correct必须是布尔值
- reason必须是字符串

2. 验证规则：
- 检查名否匹配
- 检查是否是官方网站
- 检查是否是目标网站的主域名
- 如果不确定，返回false

示例1：
输入：目标:bilibili URL:www.bilibili.com
输出：{"is_correct":true,"reason":"这是哔哩哔哩官方网站"}

示例2：
输入：目标:知乎 URL:www.zhihu.com
输出：{"is_correct":true,"reason":"是知乎官方网站"}

示例3：
输入：目标:百度 URL:news.baidu.com
输出：{"is_correct":false,"reason":"这是百度新闻子域名，不是主站"}

禁止事项：
- 不能有多余空格
- 不能有换行
- 不能有注释
- 不能改变JSON结构
- 不能添加其他字段"""
                },
                {
                    "role": "user",
                    "content": f"目标:{target_text} URL:{current_url}"
                }
            ]
            
            # 添加重试机制
            for attempt in range(3):
                try:
                    response = self.create(messages=prompt)
                    content = response['choices'][0]['message']['content'].strip()
                    
                    # 清理JSON字符串
                    def clean_json(text):
                        # 移除所有空白字符
                        text = re.sub(r'\s+', '', text)
                        # 移除可能的markdown代码块标记
                        text = re.sub(r'^```.*?\n|```$', '', text)
                        # 确保布尔值是小写的
                        text = text.replace('True', 'true').replace('False', 'false')
                        # 修复可能的中文引号
                        text = text.replace('"', '"').replace('"', '"')
                        # 修复可能的错误逗号
                        text = re.sub(r',}', '}', text)
                        return text
                    
                    content = clean_json(content)
                    
                    # 记录处理后的JSON
                    self.logger.debug(f"处理后的JSON: {content}")
                    
                    try:
                        result = json.loads(content)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"JSON解析错误: {str(e)}")
                        self.logger.error(f"问题JSON: {content}")
                        raise
                    
                    return bool(result.get('is_correct', False))
                    
                except Exception as e:
                    if attempt == 2:  # 最后一次尝试
                        self.logger.error(f"URL验证失败: {e}")
                        return False
                    time.sleep(1)  # 等待1秒后重试
            
            return False
            
        except Exception as e:
            self.logger.error(f"URL验证失败: {e}")
            return False

    def should_click_result(self, target_text: str, current_title: str) -> bool:
        """使用LLM判断是否应该点击搜索结果"""
        try:
            prompt = [
                {
                    "role": "system",
                    "content": """你是一个搜索结果匹配专家。判断搜索结果是否符合用户需求。必须严格按照以下格式输出：
{"should_click":true/false,"reason":"原因"}

判断规则：
1. 内容相关性：标题是否包含相关信息
2. 来源可靠性：是否是可靠的站
3. 信息完整性：是否包含完整信息

示例1：
目标:Python教程 标题:Python编程教程 - 免费
输出:{"should_click":true,"reason":"标题完全符合要求，是Python教程"}

示例2：
目标:编程入门 标题:广告 - 编程培训速成
输出:{"should_click":false,"reason":"广告内容，不可靠"}

示例3：
目标:Python文档 标题:Python官方文档中文版
输出:{"should_click":true,"reason":"官方文档，可靠且相关"}"""
                },
                {
                    "role": "user",
                    "content": f"目标:{target_text} 标题:{current_title}"
                }
            ]
            
            response = self.create(messages=prompt)
            content = response['choices'][0]['message']['content'].strip()
            
            # 清理和解析JSON
            content = re.sub(r'\s+', '', content)
            content = re.sub(r'```.*?\n|```', '', content)
            result = json.loads(content)
            
            return bool(result.get('should_click', False))
            
        except Exception as e:
            self.logger.error(f"结果配判断失败: {e}")
            return False

    def _execute_click_result(self, params: ClickParams) -> bool:
        """执行点击搜索结果操作"""
        try:
            # 强制等待页面加载
            time.sleep(3)
            
            # 等待搜索结果加载完成
            results = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".result,.c-container"))
            )
            
            self.logger.info(f"找到 {len(results)} 个搜索结果")
            
            # 过滤广告结果
            valid_results = []
            for result in results:
                try:
                    if "广告" not in result.text:
                        valid_results.append(result)
                except:
                    continue
            
            if not valid_results:
                self.logger.warning("未找到有效的搜索结果")
                return False
            
            # 获取目标结果
            index = min(int(params.index), len(valid_results) - 1)
            target_result = valid_results[index]
            
            # 滚动到元素位置
            self.driver.execute_script("arguments[0].scrollIntoView(true);", target_result)
            time.sleep(1)
            
            # 获取链接元素
            link = WebDriverWait(target_result, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href]"))
            )
            
            # 获取链接URL
            url = link.get_attribute("href")
            if not url:
                return False
            
            # 在新标签页中打开链接
            self.driver.execute_script(f'window.open("{url}", "_blank");')
            time.sleep(2)
            
            # 切换到新标签页
            self.driver.switch_to.window(self.driver.window_handles[-1])
            
            # 等待新页面加载
            WebDriverWait(self.driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"点击搜索结果失败: {e}")
            return False

    def _execute_extract_text(self, params: ExtractParams) -> bool:
        """执行提取文本操作"""
        try:
            # 等待页面加载
            time.sleep(2)
            
            # 常用选择器列表
            selectors = [
                params.selector,
                "article",
                ".article",
                ".content",
                "#content",
                "main",
                ".main-content",
                ".post-content",
                ".entry-content",
                ".text",
                "p",
                "body"
            ]
            
            # 尝试每个选择器
            for selector in selectors:
                try:
                    elements = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                    )
                    
                    if elements:
                        texts = []
                        for element in elements:
                            try:
                                text = element.text if params.attribute == "text" else element.get_attribute(params.attribute)
                                if text and text.strip():
                                    texts.append(text.strip())
                            except:
                                continue
                        
                        if texts:
                            self.collected_info.append({
                                "type": "text",
                                "data": "\n".join(texts)[:5000],
                                "url": self.driver.current_url,
                                "timestamp": datetime.now().isoformat()
                            })
                            return True
                            
                except Exception as e:
                    self.logger.debug(f"使用选择器 {selector} 提取失败: {e}")
                    continue
            
            self.logger.warning("未能找到有效文本")
            return False
            
        except Exception as e:
            self.logger.error(f"提取文本失败: {e}")
            return False

    def _execute_back(self) -> bool:
        """执行返回上一页操作"""
        try:
            self.driver.back()
            return True
        except Exception as e:
            self.logger.error(f"返回上一页失败: {e}")
            return False

    @retry_on_error(max_retries=3)
    def plan_task(self, user_task: str) -> str:
        """让模型规划任务步骤"""
        prompt = [
            {
                "role": "system",
                "content": """你是一个任务规划手。必须严格按照以下规则输出：

1. 输出格式必须是：
让我帮你规划任务
1. 搜索"关键词"
2. 进入[网站名]
3. 提取[体内容]
4. 返回搜索页（如果有多个网站）
5. 重复上述步骤（如果有多个网站）

2. 严格规则：
- 搜索词必须简短精确（2-4个词）
- 每个网站单独处理
- 必须顺序执行
- 禁止添加任何说明文字

3. 示例1：
输入：收集bilibili和优酷的首页视频标题
输出：
让我帮你规划任务：
1. 搜索"哔哩哔哩 bilibili"
2. 进入B站官网
3. 提取首页视频标题
4. 返回搜索页
5. 搜索"优酷视频官网"
6. 进入优酷官网
7. 提取首页视频标题

示例2：
输入：查找知乎和百度知道上关于Python的热门问题
输出：
让我帮你规划任务：
1. 搜索"知乎"
2. 进入知乎官网
3. 提取Python相关热门问题
4. 返回搜索页
5. 搜索"百度知道"
6. 进入百度知道
7. 提取Python相关热门问题

示例3：
输入：获取淘宝和京东的iPhone15价格
输出：
让我帮你规划任务：
1. 搜索"淘宝网"
2. 进入淘宝官网
3. 提取iPhone15价格信息
4. 返回搜索页
5. 搜索"京东商城"
6. 进入京东官网
7. 提取iPhone15价格信息

4. 禁止事项：
- 不能包含额外解释
- 不能有多余的标点
- 不能改变步骤格式
- 不能省略任何步骤"""
            },
            {
                "role": "user",
                "content": user_task
            }
        ]
        try:
            response = self.create(messages=prompt)
            planned_task = response['choices'][0]['message']['content']
            return planned_task
        except Exception as e:
            self.logger.error(f"任务规划失败: {e}")
            raise

    def execute_task(self, task: str) -> str:
        """执行完整任务流程并返回整理后的内容"""
        try:
            # 先进行任务规划
            planned_task = self.plan_task(task)
            self.logger.info(f"任务规划结果: {planned_task}")
            
            # 在执行任务前初始化浏览器
            self.setup_driver()
            self.driver.get("https://www.baidu.com")
            
            # 解析任务
            steps = self.parse_task(planned_task)
            self.current_task = TaskPlan(
                steps=steps,
                task_id=str(time.time()),
                created_at=time.time()
            )
            
            # 执行每个步骤
            for step in steps:
                success = self.execute_step(step)
                if not success:
                    self.logger.error(f"步骤执行失败: {step}")
                    break
            
            # 如果收集到信息则进行整理
            if self.collected_info:
                result = self.format_collected_info(self.collected_info, task)
            else:
                result = "未能集到任何信息"
            
            # 根据设置决定是否关闭浏览器
            if self.auto_close_browser:
                self.close()
                
            return result
            
        except Exception as e:
            self.logger.error(f"任务执行失败: {e}")
            # 发生错误时也根据设置决定是否关闭浏览器
            if self.auto_close_browser:
                self.close()
            raise

    def close(self) -> None:
        """清理资源"""
        if hasattr(self, 'driver') and self.driver is not None:
            try:
                self.driver.quit()
            except Exception as e:
                self.logger.error(f"关闭浏览器失败: {e}")
            finally:
                self.driver = None
                self.wait = None

    def validate(self) -> bool:
        """验证步骤参数是否合法"""
        try:
            if self.action == ActionType.SEARCH:
                assert isinstance(self.params, SearchParams)
                assert len(self.params.keywords.strip()) > 0
            elif self.action == ActionType.CLICK_RESULT:
                assert isinstance(self.params, ClickParams)
                assert self.params.index >= 0
                assert len(self.params.link_text.strip()) > 0
            elif self.action == ActionType.EXTRACT_TEXT:
                assert isinstance(self.params, ExtractParams)
                assert len(self.params.selector.strip()) > 0
            return True
        except AssertionError:
            return False

    def to_dict(self) -> Dict[str, Any]:
        """换为字典格式"""
        return {
            "action": self.action.value,
            "params": asdict(self.params)
        }

    @retry_on_error(max_retries=3)
    def format_collected_info(self, info_list: List[Dict[str, Any]], user_task: str) -> str:
        """格式化收集的信息"""
        try:
            if not info_list:
                return "未收集到任何信息"

            # 预处理收集到的信息
            formatted_info = []
            urls = set()  # 用于去重
            
            for info in info_list:
                if isinstance(info.get('data'), str):
                    text = info['data'][:1000]  # 限制单条信息长度
                    url = info.get('url', '')
                    timestamp = info.get('timestamp', '')
                    
                    if url not in urls:  # 避免重复URL
                        urls.add(url)
                        formatted_info.append({
                            "text": text,
                            "url": url,
                            "timestamp": timestamp
                        })

            if not formatted_info:
                return "收集到的信息无法处理"

            # 构建输出
            output = "【主要内容】\n"
            for idx, info in enumerate(formatted_info, 1):
                # 提取日期（如果有）
                date_str = ""
                if info['timestamp']:
                    try:
                        date = datetime.fromisoformat(info['timestamp'])
                        date_str = f"[{date.strftime('%Y-%m-%d')}] "
                    except:
                        pass
                        
                output += f"{idx}. {date_str}{info['text'][:200]}...\n\n"

            output += "\n【相关链接】\n"
            for idx, info in enumerate(formatted_info, 1):
                if info['url']:
                    output += f"{idx}. {info['url']}\n"

            return output

        except Exception as e:
            self.logger.error(f"格式化信息失败: {e}")
            return f"格式化失败。原因：{str(e)}\n收集到 {len(info_list)} 条信息。"

    def evaluate_content_quality(self, content: str, user_task: str) -> float:
        """评估内容质量和相关性"""
        try:
            prompt = [
                {
                    "role": "system",
                    "content": """评估内容质量和相关性。必须输出0到1之间的分数：
{"score":0.85,"reason":"原因"}

评分标准：
1. 相关性(40%): 与用户需求的相关程度
2. 可信度(30%): 内容的可信度和权威性
3. 完整性(20%): 信息的完整性
4. 时效性(10%): 信息的新旧程度

示例输出：
{"score":0.85,"reason":"内容高度相关且可信"}"""
                },
                {
                    "role": "user",
                    "content": f"用户需求：{user_task}\n内容：{content[:500]}"  # 限制内容长度
                }
            ]
            
            response = self.create(messages=prompt)
            content = response['choices'][0]['message']['content'].strip()
            
            # 清理和验证 JSON
            try:
                # 移除可能的非 JSON 内容
                content = re.search(r'\{.*\}', content).group(0)
                result = json.loads(content)
                return float(result.get('score', 0.0))
            except (AttributeError, json.JSONDecodeError):
                return 0.0
            
        except Exception as e:
            self.logger.error(f"内容质量评估失败: {e}")
            return 0.0

    def deep_search(self, initial_url: str, user_task: str, depth: int = 0) -> List[Dict[str, Any]]:
        """深度搜索页面内容"""
        if depth >= self.search_config.max_depth:
            return []

        collected_data = []
        try:
            # 存储原始窗口句柄
            original_window = self.driver.current_window_handle
            
            # 在新标签页中打开链接
            self.driver.execute_script(f'window.open("{initial_url}", "_blank");')
            time.sleep(2)
            
            # 切换到新标签页
            self.driver.switch_to.window(self.driver.window_handles[-1])
            
            try:
                # 等待页面加载完成
                WebDriverWait(self.driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                
                # 提取当前页面内容
                content = self.driver.find_element(By.TAG_NAME, "body").text
                quality_score = self.evaluate_content_quality(content, user_task)

                if quality_score >= self.search_config.quality_threshold:
                    collected_data.append({
                        "url": initial_url,
                        "data": content,
                        "quality_score": quality_score
                    })

                # 如果深度允许，获取子链接
                if depth < self.search_config.max_depth:
                    # 获取所有链接
                    links = []
                    try:
                        # 使用JavaScript获取所有链接
                        links_data = self.driver.execute_script("""
                            var links = [];
                            var elements = document.getElementsByTagName('a');
                            for(var i = 0; i < elements.length; i++) {
                                var href = elements[i].href;
                                var text = elements[i].innerText;
                                if(href && href.startsWith('http')) {
                                    links.push({href: href, text: text});
                                }
                            }
                            return links;
                        """)
                        
                        # 过滤和处理链接
                        for link_data in links_data:
                            url = link_data['href']
                            text = link_data['text']
                            
                            # 跳过社交媒体、广告等链接
                            if any(skip in url.lower() for skip in ['twitter', 'facebook', 'ads', 'login', 'signup']):
                                continue
                            
                            links.append(url)
                            
                    except Exception as e:
                        self.logger.warning(f"获取子链接失败: {e}")

                    # 处理子链接
                    for sub_url in links[:self.search_config.max_results]:
                        try:
                            sub_results = self.deep_search(sub_url, user_task, depth + 1)
                            collected_data.extend(sub_results)
                        except Exception as e:
                            self.logger.warning(f"处理子链接失败: {e}")
                            continue

            finally:
                # 关闭当前标签页
                self.driver.close()
                # 切回原始窗口
                self.driver.switch_to.window(original_window)

            return collected_data

        except Exception as e:
            self.logger.error(f"深度搜索失败: {e}")
            # 确保切回原始窗口
            try:
                self.driver.switch_to.window(original_window)
            except:
                pass
            return []

    def get_summary_prompt(self, info_list: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """获取总结提示词"""
        # 准备输入文本
        texts = []
        for info in info_list:
            if isinstance(info.get('data'), str):
                text = info['data'][:1000]  # 限制单条信息长度
                url = info.get('url', '')
                texts.append(f"来源: {url}\n内容: {text}\n")
        
        combined_text = "\n".join(texts)
        
        return [
            {
                "role": "system",
                "content": """你是一个专业的信息总结专家。请严格按照以下格式和规则总结提供的信息：

输出格式：
{
    "summary": {
        "main_points": [
            "要点1",
            "要点2",
            "要点3"
        ],
        "details": {
            "time_info": "时间相关信息",
            "key_facts": [
                "关键事实1",
                "关键事实2"
            ],
            "statistics": [
                "统计数据1",
                "统计数据2"
            ]
        },
        "conclusion": "总结性结论"
    }
}

严格规则：
1. 格式要求：
- 必须输出合法的JSON格式
- 必须包含所有指定字段
- 不允许添加额外字段
- 不能使用markdown格式
- 不能包含HTML标签

2. 内容要求：
- main_points: 3-5个核心要点
- key_facts: 2-4个关键事实
- statistics: 包含数字的统计信息（如果有）
- conclusion: 50-100字的总结

3. 写作规范：
- 使用中文输出
- 使用客观陈述语气
- 避免主观评价
- 保持时间信息的准确性
- 数据必须有来源说明

4. 禁止事项：
- 不能使用模糊表述
- 不能添加个人观点
- 不能使用营销语言
- 不能包含预测性内容
- 不能使用未经证实的信息

5. 信息处理：
- 合并重复信息
- 优先使用最新信息
- 保留具体数据
- 注明信息来源
- 标注时间戳

错误示例：
{
    "summary": {
        "main_points": ["可能会发展", "据说有影响", "预计将会"],
        "details": {
            "time_info": "最近",
            "key_facts": ["某些专家认为"],
            "statistics": ["大约有很多"]
        },
        "conclusion": "前景光明"
    }
}

注意：如果信息不足，相应字段填写"信息不足"，但必须保持JSON结构完整。"""
            },
            {
                "role": "user",
                "content": f"请总结以下信息：\n\n{combined_text}"
            }
        ]

# 用示例
def main():
    assistant = WorkAssistant(log_level=logging.DEBUG)  # 设置更详细的日志级别
    
    try:
        task = "搜索哔哩哔"
        result = assistant.execute_task(task)
        print("执行结果:", result)
    except Exception as e:
        print(f"执行失败: {e}")
    finally:
        assistant.close()

if __name__ == "__main__":
    main()