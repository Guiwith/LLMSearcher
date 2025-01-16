from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QProgressBar, QSizePolicy, QSplitter, QDialog, QLabel, QTableWidget, QTableWidgetItem, QTimeEdit, QHeaderView, QMessageBox
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTime, QTimer, QDateTime
import sys
from selenium import webdriver
from bs4 import BeautifulSoup
import json
import requests
from typing import List, Dict
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

class LLMBrowser:
    def __init__(self, model: str = "glm4:latest"):
        self.llm_url = "http://172.31.118.255:11434/v1/chat/completions"
        self.headers = {"Content-Type": "application/json"}
        self.model = model
        
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
        """分析用户需求,只回答1个最核心的用户可能想搜索的搜索关键词"""
        prompt = f"""请分析以下需求,只回答1个最核心的用户可能想搜索的搜索关键词。

正确示例：
用户需求：搜索哔哩哔哩，收集视频标题
核心搜索关键词：哔哩哔哩

用户需求：查找关于Python编程的入门教程
核心搜索关键词：Python教程

用户需求：寻找北京最好吃的火锅店推荐
核心搜索关键词：北京火锅

错误示例：
用户需求：搜索bilibili，收集视频标题
错误关键词：bilibili视频标题（❌ 不要把目标动作加入关键词）
正确关键词：bilibili（✓ 只需要目标网站名称）

用户需求：寻找Python入门教程视频
错误关键词：Python教程视频（❌ 不要把内容类型加入关键词）
正确关键词：Python教程（✓ 只需要核心主题）

用户需求：搜索美食up主视频
错误关键词：美食视频up主（❌ 不要把多个概念混合）
正确关键词：美食up主（✓ 只需要目标对象）

当前需求内容：{user_query}

请严格按照以下格式返回关键词，不要包含序号、逗号或其他文字：
关键词"""
        
        response = self._call_llm(prompt)
        return self._parse_keywords(response)
    
    def _parse_keywords(self, llm_response: str) -> List[str]:
        """解析LLM返回的关键词"""
        try:
            # 移除可能的多余空格和换行
            response_text = llm_response.strip()
            
            # 移除所有标点符号
            response_text = response_text.replace(',', ' ').replace('，', ' ')
            
            # 分割并取第一个非空词
            keywords = [k.strip() for k in response_text.split() if k.strip()]
            
            # 只取第一个关键词
            if keywords:
                keywords = [keywords[0]]
            else:
                raise ValueError("未能从LLM响应中提取到关键词")
                
            return keywords
            
        except Exception as e:
            raise Exception(f"解析关键词时发生错误: {str(e)}")
    
    def search_web(self, keywords: List[str]) -> List[Dict]:
        """执行搜索并返回结果"""
        try:
            from playwright.sync_api import sync_playwright
            
            results = []
            with sync_playwright() as p:
                # 启动浏览器
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-gpu',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process'
                    ]
                )
                
                # 创建新页面
                page = browser.new_page(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                
                try:
                    # 构建搜索URL
                    search_query = ' '.join(keywords)
                    search_url = f"https://www.bing.com/search?q={search_query}"
                    
                    # 访问页面
                    page.goto(search_url, wait_until='networkidle')
                    
                    # 等待搜索结果加载
                    page.wait_for_selector('#b_results')
                    
                    # 获取所有搜索结果，包括特殊内容
                    results_data = page.evaluate('''
                        () => {
                            const results = [];
                            
                            // 处理所有可能的结果容器
                            const containers = [
                                '#b_results > li',  // 标准结果
                                '.b_ans',           // 答案框
                                '.b_rich',          // 富媒体结果
                                '.b_algo',          // 算法结果
                                '.b_top',           // 顶部结果
                                '.b_context'        // 上下文结果
                            ];
                            
                            // 获取所有匹配的元素
                            containers.forEach(selector => {
                                document.querySelectorAll(selector).forEach(item => {
                                    // 跳过广告
                                    if (item.classList.contains('b_ad')) return;
                                    
                                    let title = '';
                                    let url = '';
                                    let description = '';
                                    let content = '';
                                    
                                    // 获取所有文本内容（用于特殊结果）
                                    content = item.textContent.trim();
                                    
                                    // 获取链接和标题
                                    const links = item.querySelectorAll('a[href]:not([href^="javascript:"]):not([href^="#"])');
                                    for (const link of links) {
                                        const text = link.textContent.trim();
                                        if (text && link.href) {
                                            title = text;
                                            url = link.href;
                                            break;
                                        }
                                    }
                                    
                                    // 获取描述
                                    const descElements = item.querySelectorAll('p, .b_caption p, .b_snippet, .snippet, .news-body');
                                    for (const desc of descElements) {
                                        const text = desc.textContent.trim();
                                        if (text) {
                                            description = text;
                                            break;
                                        }
                                    }
                                    
                                    // 添加结果
                                    if ((title && url) || content) {
                                        results.push({
                                            title,
                                            url,
                                            description,
                                            content,
                                            isSpecialContent: !title && !url && content
                                        });
                                    }
                                });
                            });
                            
                            return results;
                        }
                    ''')
                    
                    # 处理结果
                    for result in results_data:
                        if result.get('isSpecialContent'):
                            # 特殊内容（如热搜列表）直接使用content
                            results.append({
                                'title': '特殊内容',
                                'url': search_url,
                                'description': result['content']
                            })
                        else:
                            # 标准搜索结果
                            results.append({
                                'title': result['title'],
                                'url': result['url'],
                                'description': result['description']
                            })
                        print(f"Found result: {result}")  # 调试输出
                    
                    print(f"Total results found: {len(results)}")  # 调试输出
                    return results
                    
                finally:
                    browser.close()
                    
        except Exception as e:
            print(f"Search error: {str(e)}")  # 调试输出
            raise Exception(f"搜索网页时发生错误: {str(e)}")
    
    def select_pages(self, search_results: List[Dict], user_query: str) -> List[str]:
        """让LLM选择最相关的页面"""
        try:
            prompt = f"""基于用户需求，从搜索结果中选择1个最相关的页面标题。

示例1：
用户需求：搜索哔哩哔哩，收集视频标题
搜索结果：
[{{"title": "哔哩哔哩 (゜-゜)つロ 干杯~-bilibili", "url": "https://www.bilibili.com"}}, {{"title": "B站_百度百科", "url": "https://baike.baidu.com/item/B站"}}]
选择标题：哔哩哔哩 (゜-゜)つロ 干杯~-bilibili

示例2：
用户需求：查找Python教程
搜索结果：
[{{"title": "Python教程 - 廖雪峰的官方网站", "url": "https://www.liaoxuefeng.com/wiki/1016959663602400"}}, {{"title": "Python入门教程", "url": "https://www.runoob.com/python/python-tutorial.html"}}]
选择标题：Python教程 - 廖雪峰的官方网站

示例3：
用户需求：寻找北京火锅推荐
搜索结果：
[{{"title": "北京最受欢迎的10家火锅店", "url": "https://example.com/1"}}, {{"title": "美团外卖北京火锅", "url": "https://example.com/2"}}]
选择标题：北京最受欢迎的10家火锅店

注意事项：
1. 如果用户需求是搜索视频网站，优先选择该网站的主页而不是教程或介绍页面
2. 如果用户需求是寻找教程，优先选择专业的教程网站而不是问答页面
3. 如果用户需求是寻找推荐，优先选择包含排名或列表的页面

当前用户需求: {user_query}
当前搜索结果:
{json.dumps(search_results, ensure_ascii=False, indent=2)}

请严格按照以下格式返回标题，不要添加任何其他文字：
标题"""
            
            print(f"Prompt to LLM:\n{prompt}")  # 调试输出
            
            # 调用LLM
            response = self._call_llm(prompt)
            print(f"LLM Response:\n{response}")  # 调试输出
            
            # 解析返回的标题
            titles = [title.strip() for title in response.strip().split(',')]
            print(f"Found titles: {titles}")  # 调试输出
            
            # 根据标题查找对应的URL
            urls = []
            for title in titles:
                for result in search_results:
                    if title in result['title'] or result['title'] in title:
                        urls.append(result['url'])
                        print(f"Matched title '{title}' to URL: {result['url']}")  # 调试输出
                        break
            
            if not urls and search_results:
                # 如果没有匹配的URL，使用第一个搜索结果
                urls = [search_results[0]['url']]
                print(f"Falling back to first result: {urls[0]}")  # 调试输出
            
            return urls
            
        except Exception as e:
            print(f"Error in select_pages: {str(e)}")  # 调试输出
            raise Exception(f"选择页面时发生错误: {str(e)}")
    
    def crawl_page_content(self, url: str) -> Dict:
        """使用DOM树分析页面内容"""
        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-gpu',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-web-security'
                    ]
                )
                
                page = browser.new_page(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                
                try:
                    page.goto(url, wait_until='networkidle')
                    
                    # 获取DOM树结构
                    dom_tree = self._build_dom_tree(page)
                    
                    # 提取有意义的内容
                    content = self._extract_content_from_dom(dom_tree)
                    
                    return {'content': content, 'url': url}
                    
                finally:
                    browser.close()
                    
        except Exception as e:
            print(f"页面分析失败: {url}, 错误: {str(e)}")
            return {'content': '', 'url': url}

    def _build_dom_tree(self, page) -> Dict:
        """构建DOM树结构"""
        return page.evaluate('''
            () => {
                function buildNode(element) {
                    const node = {
                        tagName: element.tagName?.toLowerCase(),
                        type: element.nodeType === 3 ? 'TEXT_NODE' : 'ELEMENT_NODE',
                        isVisible: (function() {
                            if (element.nodeType === 3) {
                                return element.textContent.trim().length > 0;
                            }
                            const style = window.getComputedStyle(element);
                            return style.display !== 'none' && 
                                   style.visibility !== 'hidden' && 
                                   style.opacity !== '0';
                        })(),
                        isInteractive: (function() {
                            if (element.nodeType === 3) return false;
                            const interactiveTags = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'];
                            return interactiveTags.includes(element.tagName) || 
                                   element.onclick != null || 
                                   element.getAttribute('role') === 'button';
                        })(),
                        children: []
                    };
                    
                    if (element.nodeType === 3) {
                        node.text = element.textContent.trim();
                    } else {
                        // 获取元素属性
                        node.attributes = {};
                        for (const attr of element.attributes || []) {
                            node.attributes[attr.name] = attr.value;
                        }
                        
                        // 递归处理子节点
                        for (const child of element.childNodes) {
                            if (child.nodeType === 1 || (child.nodeType === 3 && child.textContent.trim())) {
                                node.children.push(buildNode(child));
                            }
                        }
                    }
                    
                    return node;
                }
                
                return buildNode(document.documentElement);
            }
        ''')

    def _extract_content_from_dom(self, dom_tree: Dict) -> str:
        """从DOM树中提取有意义的内容"""
        content_parts = []
        
        def extract_node(node: Dict):
            if node['type'] == 'TEXT_NODE' and node['isVisible']:
                text = node.get('text', '').strip()
                if text and len(text) > 3:  # 忽略太短的文本
                    content_parts.append(text)
            
            if node['type'] == 'ELEMENT_NODE':
                # 处理特定标签
                tag = node.get('tagName', '')
                if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    # 为标题添加标记
                    heading_texts = [child.get('text', '') for child in node['children'] 
                                   if child['type'] == 'TEXT_NODE' and child['isVisible']]
                    if heading_texts:
                        content_parts.append(f"\n[{tag.upper()}] {''.join(heading_texts)}\n")
                
                # 递归处理子节点
                for child in node.get('children', []):
                    extract_node(child)
        
        extract_node(dom_tree)
        return '\n'.join(content_parts)
    
    def summarize_content(self, content: str, user_query: str) -> str:
        """基于爬取的内容回答用户需求"""
        try:
            # 检查内容是否为空或无效
            if not content or len(content.strip()) < 10:
                return "抱歉，未能成功获取到有效内容。可能的原因：\n1. 页面需要登录\n2. 内容被动态加载\n3. 网站有反爬虫机制\n\n建议：\n- 尝试直接访问网页\n- 选择其他相关网页"

            prompt = f"""你现在拥有以下知识：

{content}

请基于上述知识，回答用户的需求：{user_query}

要求：
1. 只使用给定知识中的信息来回答
2. 如果知识中没有相关信息，请明确说明
3. 保持回答的准确性和客观性
4. 使用清晰的结构组织回答
5. 如果信息不完整，可以指出缺失的部分

请直接给出回答，不要解释你的思考过程。"""

            return self._call_llm(prompt)
            
        except Exception as e:
            return f"处理内容时发生错误: {str(e)}"
    
    def start_search(self):
        query = self.query_input.toPlainText()
        if not query:
            return
            
        try:
            # 清空之前的结果
            self.results_display.clear()
            
            self.status_display.append("分析需求中...")
            keywords = self.browser.analyze_query(query)
            self.results_display.append("搜索关键词：" + ", ".join(keywords) + "\n")
            
            self.status_display.append("搜索相关内容...")
            search_results = self.browser.search_web(keywords)
            
            self.status_display.append("选择相关页面...")
            selected_urls = self.browser.select_pages(search_results, query)
            
            # 爬取选中页面的内容
            self.status_display.append("爬取页面内容...")
            all_content = []
            for url in selected_urls:
                content = self.browser.crawl_page_content(url)
                # 清理内容（移除多余空白字符）
                cleaned_content = ' '.join(content['content'].split())
                all_content.append(cleaned_content)
            
            # 合并所有内容
            combined_content = '\n\n'.join(all_content)
            
            # 让LLM总结内容
            self.status_display.append("正在总结内容...")
            summary = self.browser.summarize_content(combined_content, query)
            
            # 显示总结结果
            self.results_display.append("\n总结内容：\n")
            self.results_display.append(summary)
            
            self.status_display.append("处理完成!")
            if selected_urls:
                self.web_view.setUrl(QUrl(selected_urls[0]))
        except Exception as e:
            self.status_display.append(f"错误: {str(e)}")

class SearchThread(QThread):
    """搜索线程"""
    # 定义信号
    status_signal = pyqtSignal(str)  # 用于更新状态
    result_signal = pyqtSignal(str)  # 用于更新结果
    error_signal = pyqtSignal(str)   # 用于报告错误
    url_signal = pyqtSignal(str)     # 用于更新网页
    search_url_signal = pyqtSignal(str)  # 用于更新搜索页面
    progress_signal = pyqtSignal(int)  # 用于更新进度条

    def __init__(self, browser, query):
        super().__init__()
        self.browser = browser
        self.query = query

    def run(self):
        try:
            # 分析需求 (20%)
            self.progress_signal.emit(0)
            self.status_signal.emit("分析需求中...")
            keywords = self.browser.analyze_query(self.query)
            self.result_signal.emit("搜索关键词：" + ", ".join(keywords) + "\n")
            self.progress_signal.emit(20)
            
            # 搜索内容 (40%)
            self.status_signal.emit("搜索相关内容...")
            search_query = ' '.join(keywords)
            search_url = f"https://www.bing.com/search?q={search_query}"
            self.search_url_signal.emit(search_url)
            search_results = self.browser.search_web(keywords)
            self.progress_signal.emit(40)
            
            # 选择页面 (60%)
            self.status_signal.emit("选择相关页面...")
            selected_urls = self.browser.select_pages(search_results, self.query)
            if selected_urls:
                self.url_signal.emit(selected_urls[0])
            self.progress_signal.emit(60)
            
            # 爬取内容 (80%)
            self.status_signal.emit("爬取页面内容...")
            all_content = []
            for url in selected_urls:
                content = self.browser.crawl_page_content(url)
                cleaned_content = ' '.join(content['content'].split())
                all_content.append(cleaned_content)
            self.progress_signal.emit(80)
            
            # 总结内容 (100%)
            self.status_signal.emit("正在总结内容...")
            combined_content = '\n\n'.join(all_content)
            summary = self.browser.summarize_content(combined_content, self.query)
            self.result_signal.emit("\n总结内容：\n" + summary)
            self.progress_signal.emit(100)
            
            self.status_signal.emit("处理完成!")
                
        except Exception as e:
            self.error_signal.emit(f"错误: {str(e)}")
            self.progress_signal.emit(0)

class BatchTaskDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量任务设置")
        self.setMinimumSize(600, 400)
        self.tasks = []  # 存储任务列表
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 创建表格
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["需求内容", "计划执行时间", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 100)
        layout.addWidget(self.table)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 添加任务按钮
        add_button = QPushButton("添加任务")
        add_button.clicked.connect(self.add_task)
        button_layout.addWidget(add_button)
        
        # 删除任务按钮
        delete_button = QPushButton("删除任务")
        delete_button.clicked.connect(self.delete_task)
        button_layout.addWidget(delete_button)
        
        # 确认按钮
        confirm_button = QPushButton("确认")
        confirm_button.clicked.connect(self.accept)
        button_layout.addWidget(confirm_button)
        
        # 取消按钮
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
    def add_task(self):
        """添加新任务行"""
        current_row = self.table.rowCount()
        self.table.insertRow(current_row)
        
        # 需求内容
        content_item = QTableWidgetItem("")
        self.table.setItem(current_row, 0, content_item)
        
        # 时间选择
        time_widget = QTimeEdit()
        time_widget.setDisplayFormat("HH:mm:ss")
        if current_row == 0:
            # 第一个任务默认即时开始
            time_widget.setTime(QTime.currentTime())
        else:
            # 后续任务默认在上一个任务的1小时后
            last_time = self.table.cellWidget(current_row-1, 1).time()
            next_time = last_time.addSecs(3600)  # 添加1小时
            time_widget.setTime(next_time)
        self.table.setCellWidget(current_row, 1, time_widget)
        
        # 状态
        status_item = QTableWidgetItem("等待中")
        self.table.setItem(current_row, 2, status_item)
        
    def delete_task(self):
        """删除选中的任务行"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)
            
    def get_tasks(self):
        """获取所有任务信息"""
        tasks = []
        for row in range(self.table.rowCount()):
            content = self.table.item(row, 0).text()
            time = self.table.cellWidget(row, 1).time()
            tasks.append({
                'content': content,
                'time': time,
                'status': self.table.item(row, 2).text()
            })
        return tasks

class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("搜索历史")
        self.setMinimumSize(800, 600)
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 历史记录显示区域
        self.history_display = QTextEdit()
        self.history_display.setReadOnly(True)
        self.history_display.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 10px;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.history_display)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 清空历史按钮
        clear_button = QPushButton("清空历史")
        clear_button.clicked.connect(self.clear_history)
        clear_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        button_layout.addWidget(clear_button)
        
        # 关闭按钮
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
    def clear_history(self):
        reply = QMessageBox.question(
            self, 
            '确认清空', 
            '确定要清空所有历史记录吗？此操作不可撤销。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.history_display.clear()
            # 发送信号通知主窗口历史已清空
            self.parent().history_records.clear()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("灵析AI浏览器")
        self.setMinimumSize(1200, 800)
        
        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(main_splitter)
        
        # 左侧面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # 输入框
        self.query_input = QTextEdit()
        self.query_input.setPlaceholderText("输入你的需求...")
        self.query_input.setMaximumHeight(100)
        left_layout.addWidget(self.query_input)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 搜索按钮
        search_button = QPushButton("开始搜索")
        search_button.clicked.connect(self.start_search)
        button_layout.addWidget(search_button)
        
        # 批量任务按钮
        batch_button = self.add_batch_tasks_button()
        button_layout.addWidget(batch_button)
        
        # 历史记录按钮
        history_button = QPushButton("历史记录")
        history_button.clicked.connect(self.show_history)
        button_layout.addWidget(history_button)
        
        left_layout.addLayout(button_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(2)  # 设置进度条高度
        self.progress_bar.setTextVisible(False)  # 隐藏进度文本
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background: #f0f0f0;
            }
            QProgressBar::chunk {
                background: #4CAF50;
            }
        """)
        left_layout.addWidget(self.progress_bar)
        
        # 状态显示
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setPlaceholderText("状态信息...")
        self.status_display.setMaximumHeight(50)  # 减小高度只显示最新状态
        self.status_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;  /* 深色背景 */
                border: 1px solid #333333;  /* 深色边框 */
                border-radius: 4px;
                padding: 5px;
                color: #ffffff;  /* 白色文字 */
                font-size: 12px;
            }
            QTextEdit:disabled {
                background-color: #1e1e1e;
                color: #ffffff;
            }
        """)
        left_layout.addWidget(self.status_display)
        
        # 搜索结果显示
        self.results_display = QTextEdit()
        self.results_display.setReadOnly(True)
        self.results_display.setPlaceholderText("搜索结果将在这里显示...")
        left_layout.addWidget(self.results_display)
        
        # 配置WebEngine设置
        profile = QWebEngineProfile.defaultProfile()
        settings = profile.settings()
        
        # 禁用JavaScript错误报告
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        
        # 其他设置保持不变
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebRTCPublicInterfacesOnly, True)
        
        # 禁用其他可能的问题源
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        profile.setPersistentStoragePath("")
        
        # 右侧浏览器
        self.web_view = QWebEngineView()
        self.default_url = QUrl("https://www.bing.com")
        self.web_view.setUrl(self.default_url)
        self.web_view.setZoomFactor(0.9)
        self.web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # 将左侧面板和浏览器添加到分割器
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(self.web_view)
        
        # 设置初始分割比例（左:右 = 1:2）
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 2)
        
        # 设置分割器样式
        main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #cccccc;
                width: 2px;
            }
            QSplitter::handle:hover {
                background-color: #999999;
            }
            QSplitter::handle:pressed {
                background-color: #666666;
            }
        """)
        
        # 初始化浏览器为None
        self.browser = None
        self.search_thread = None
        
        # 添加任务存储
        self.scheduled_tasks = []  # 存储已计划的任务
        
        # 存储历史记录
        self.history_records = []
        
        # 初始化浏览器
        try:
            self.status_display.append("正在初始化浏览器...")
            self.browser = LLMBrowser(model="glm4:latest")
            self.status_display.append("浏览器初始化完成!")
        except Exception as e:
            self.status_display.append(f"初始化错误: {str(e)}")

    def resizeEvent(self, event):
        """处理窗口大小改变事件"""
        super().resizeEvent(event)
        # 更新web_view的大小
        if hasattr(self, 'web_view'):
            self.web_view.setFixedHeight(self.height())

    def start_search(self):
        query = self.query_input.toPlainText()
        if not query:
            return
            
        # 重置进度条和结果显示
        self.progress_bar.setValue(0)
        self.results_display.clear()
        
        # 创建并启动搜索线程
        self.search_thread = SearchThread(self.browser, query)
        
        # 连接信号
        self.search_thread.status_signal.connect(self.append_status)
        self.search_thread.result_signal.connect(self.results_display.append)
        self.search_thread.error_signal.connect(self.status_display.append)
        self.search_thread.url_signal.connect(lambda url: self.web_view.setUrl(QUrl(url)))
        self.search_thread.search_url_signal.connect(lambda url: self.web_view.setUrl(QUrl(url)))
        self.search_thread.progress_signal.connect(self.progress_bar.setValue)
        self.search_thread.finished.connect(self.on_search_finished)
        
        # 启动线程
        self.search_thread.start()
    
    def on_search_finished(self):
        """搜索完成后的处理"""
        # 获取当前搜索结果
        current_result = self.results_display.toPlainText()
        if current_result:
            # 将结果添加到历史记录
            self.append_to_history(self.query_input.toPlainText(), current_result)
            print("Search result added to history")  # 调试输出
        
        # 重置浏览器到默认页面
        self.web_view.setUrl(self.default_url)
        self.status_display.append("搜索完成，浏览器已重置到首页")

    def add_batch_tasks_button(self):
        """添加批量任务按钮"""
        batch_button = QPushButton("批量任务")
        batch_button.clicked.connect(self.show_batch_dialog)
        return batch_button

    def show_batch_dialog(self):
        """显示批量任务设置对话框"""
        dialog = BatchTaskDialog(self)
        
        # 恢复之前的任务
        for task in self.scheduled_tasks:
            current_row = dialog.table.rowCount()
            dialog.table.insertRow(current_row)
            
            # 设置需求内容
            content_item = QTableWidgetItem(task['content'])
            dialog.table.setItem(current_row, 0, content_item)
            
            # 设置执行时间
            time_widget = QTimeEdit()
            time_widget.setDisplayFormat("HH:mm:ss")
            time_widget.setTime(task['time'])
            dialog.table.setCellWidget(current_row, 1, time_widget)
            
            # 设置状态
            status_item = QTableWidgetItem(task['status'])
            dialog.table.setItem(current_row, 2, status_item)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            tasks = dialog.get_tasks()
            if tasks:
                self.scheduled_tasks = tasks  # 保存新的任务列表
                self.schedule_tasks(tasks)
    
    def schedule_tasks(self, tasks):
        """调度任务执行"""
        current_time = QTime.currentTime()
        
        for task in tasks:
            content = task['content']
            planned_time = task['time']
            
            # 计算延迟时间（毫秒）
            delay = current_time.msecsTo(planned_time)
            if delay < 0:  # 如果计划时间早于当前时间，安排在明天同一时间
                delay += 24 * 3600 * 1000
            
            # 创建定时器
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda q=content: self.execute_scheduled_task(q))
            timer.start(delay)
            
            # 更新任务状态
            for stored_task in self.scheduled_tasks:
                if stored_task['content'] == content:
                    stored_task['status'] = "已计划"
    
    def execute_scheduled_task(self, query):
        """执行计划任务"""
        self.query_input.setPlainText(query)
        self.start_search()
        
        # 更新任务状态
        for task in self.scheduled_tasks:
            if task['content'] == query:
                task['status'] = "已完成"

    def append_status(self, text):
        """更新状态显示"""
        self.status_display.clear()  # 清除之前的内容
        self.status_display.append(text)  # 只显示最新状态

    def show_history(self):
        """显示历史记录对话框"""
        dialog = HistoryDialog(self)
        
        # 显示所有历史记录
        for record in self.history_records:
            dialog.history_display.append(record)
            dialog.history_display.append("\n" + "="*50 + "\n")  # 分隔线
        
        print(f"Showing {len(self.history_records)} history records")  # 调试输出
        dialog.exec()
    
    def append_to_history(self, query: str, result: str):
        """添加搜索结果到历史记录"""
        current_time = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        history_entry = f"时间：{current_time}\n需求：{query}\n结果：\n{result}"
        self.history_records.append(history_entry)
        print(f"Added to history: {history_entry}")  # 调试输出

def main():
    app = QApplication(sys.argv + [
        '--disable-web-security',  # 禁用网页安全限制
        '--no-sandbox',  # 禁用沙箱
        '--disable-gpu',  # 禁用GPU加速
        '--disable-software-rasterizer',  # 禁用软件光栅化
        '--disable-dev-shm-usage',  # 禁用/dev/shm使用
        '--disable-webgl',  # 禁用WebGL
        '--disable-accelerated-2d-canvas',  # 禁用加速2D画布
    ])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
