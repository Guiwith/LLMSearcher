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
    index: int
    link_text: str

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

class TaskParser:
    """任务解析器"""
    @classmethod
    def get_prompt_template(cls, task: str) -> List[Dict[str, str]]:
        """获取提示词模板"""
        return [
            {
                "role": "system",
                "content": """你是一个任务规划器。你的输出必须是单个、完整、合法的JSON对象。

输出格式：
{"steps":[{"action":"动作名","params":{"参数名":"参数值"}},...]}

严格规则：
1. 动作类型仅限以下四种：
- search: 搜索操作
- click_result: 点击搜索结果
- extract_text: 提取文本
- back: 返回上一页

2. 每种动作的参数格式：
search: {"keywords":"搜索词"}
click_result: {"index":0,"link_text":"要点击的标题"}
extract_text: {"selector":".css选择器","attribute":"text"}
back: {}

3. 完整示例：
{"steps":[{"action":"search","params":{"keywords":"Python教程"}},{"action":"click_result","params":{"index":0,"link_text":"Python"}},{"action":"extract_text","params":{"selector":".content","attribute":"text"}},{"action":"back","params":{}}]}

4. 格式要求：
- 必须是合法的JSON
- 必须包含steps数组
- 每个步骤必须有action和params
- 不能省略大括号或引号
- 不能包含注释或换行
- 不能使用markdown标记
- 不能有多余空格

5. 禁止事项：
- 不能有多个steps数组
- 不能嵌套steps数组
- 不能改变JSON结构
- 不能添加其他字段
- 不能使用未定义的动作类型
- 不能省略必需的参数"""
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
            try:
                cleaned_response = clean_response(response)
                print(f"清理后的JSON: {cleaned_response}")  # 调试输出
                data = json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {str(e)}")
                print(f"清理后的JSON: {cleaned_response}")
                raise

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

class WorkAssistant(LLMClient):
    def __init__(self, api_base: str = "http://localhost:11434", 
                 model: str = "glm4:latest",
                 log_level: int = logging.INFO,
                 auto_close_browser: bool = True,
                 headless: bool = False):
        super().__init__(base_url=api_base, model=model)
        self.setup_logging(log_level)
        self.collected_info = []
        self.current_task: Optional[TaskPlan] = None
        self.task_parser = TaskParser()
        self.driver = None
        self.wait = None
        self.auto_close_browser = auto_close_browser
        self.headless = headless

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
            if self.headless:
                # 无头模式配置
                chrome_options.add_argument('--headless=new')  # 新版Chrome的无头模式
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--window-size=1920,1080')  # 设置窗口大小
            
            # 用配置
            chrome_options.add_argument('--disable-popup-blocking')
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            self.driver.set_page_load_timeout(30)
            self.wait = WebDriverWait(self.driver, 10)
            
        except Exception as e:
            self.logger.error(f"浏览器驱动初始化失败: {e}")
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

    def _execute_search(self, params: SearchParams) -> bool:
        """执行搜索操作"""
        try:
            search_box = self.wait.until(
                EC.presence_of_element_located((By.ID, "kw"))
            )
            search_box.clear()
            search_box.send_keys(params.keywords)
            
            search_button = self.wait.until(
                EC.element_to_be_clickable((By.ID, "su"))
            )
            search_button.click()
            
            # 等待搜索结果加载
            self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "result"))
            )
            return True
            
        except TimeoutException:
            self.logger.error("搜索操作超时")
            return False
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
2. 来源可靠性：是否是可靠的��站
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
            results = self.wait.until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "result"))
            )
            
            self.logger.info(f"找到 {len(results)} 个搜索结果")
            
            for idx, result in enumerate(results):
                try:
                    if "广告" in result.text:
                        continue
                    
                    title_element = result.find_element(By.TAG_NAME, "h3")
                    title = title_element.text
                    
                    self.logger.debug(f"检查搜索结果 {idx + 1}: {title}")
                    
                    # 使用LLM判断是否点击
                    if self.should_click_result(params.link_text, title):
                        self.logger.info(f"尝试点击匹配的结果: {title}")
                        
                        # 点击逻辑...
                        try:
                            link = title_element.find_element(By.XPATH, ".//a")
                            link.click()
                            time.sleep(2)
                            
                            if len(self.driver.window_handles) > 1:
                                self.driver.switch_to.window(self.driver.window_handles[-1])
                            return True
                            
                        except Exception as e:
                            self.logger.warning(f"点击失败: {e}")
                            continue
                        
                except Exception as e:
                    self.logger.warning(f"处理搜索结果出错: {e}")
                    continue
                
            return False
            
        except Exception as e:
            self.logger.error(f"执行点击操作失败: {e}")
            return False

    def _execute_extract_text(self, params: ExtractParams) -> bool:
        """执行提取文本操作"""
        try:
            # 等待页面加载完成
            time.sleep(2)
            
            # 尝试不同的选择器
            selectors = [
                params.selector,  # 原始选择器
                "body",          # 整个body
                "html",          # 整个html
                "*"             # 所有元素
            ]
            
            for selector in selectors:
                try:
                    # 尝试找到元
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        # 收集所有文本
                        texts = []
                        for element in elements:
                            try:
                                if params.attribute == "text":
                                    text = element.text
                                else:
                                    text = element.get_attribute(params.attribute)
                                
                                if text and text.strip():
                                    texts.append(text.strip())
                            except:
                                continue
                        
                        if texts:
                            # 如果有关键词，过滤包含关键字的文本
                            if params.keywords:
                                filtered_texts = [t for t in texts if params.keywords.lower() in t.lower()]
                                if filtered_texts:
                                    texts = filtered_texts
                            
                            # 合并文本并保存
                            combined_text = "\n".join(texts)
                            self.collected_info.append({
                                "type": "text",
                                "data": combined_text,
                                "url": self.driver.current_url
                            })
                            return True
                except Exception as e:
                    self.logger.warning(f"使用选择器 {selector} 提取失败: {e}")
                    continue
            
            self.logger.error("未能找到任何效文本")
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
- 必须按顺序执行
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
        """使用LLM整理收集的信息"""
        try:
            prompt = [
                {
                    "role": "system",
                    "content": """你是一个内容整理助手。必须严格按照以下规则整理内容：

1. 输出格式：
【内容分类】
1. 具体内容1
2. 具体内容2
...

2. 严格要求：
- 必须有分类标题
- 必须有序号
- 内容必须简洁
- 去除无关内容
- 保持原始顺序

3. 禁止事项：
- 不能添加评论
- 不能有多余解释
- 不能改变格式
- 不能省略重要信息
- 不能添加装饰性文字

示例1：
用���需求：收集视频标题
输出：
【视频标题】
1. xxx视频
2. xxx视频

示例2：
用户需求：查找Python相关题
输出：
【热门问题】
1. Python何门？
2. Python适合做什么项目？

示例3：
用户需求：收集商品价格
输出：
【商品价格信息】
1. 商品A：¥999
2. 商品B：¥888"""
                },
                {
                    "role": "user",
                    "content": f"""用户需求：{user_task}
收集内容：{json.dumps(info_list, ensure_ascii=False)}

请严格按照格式整理。"""
                }
            ]

            # 调用LLM进行整理
            response = self.create(messages=prompt)
            formatted_content = response['choices'][0]['message']['content']
            return formatted_content

        except Exception as e:
            self.logger.error(f"内容整理失败: {e}")
            return "内容整理失败，返回原内容：\n" + "\n".join(
                [f"URL: {info['url']}\n{info['data']}" for info in info_list]
            )

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