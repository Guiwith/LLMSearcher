from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QTextEdit, QPushButton, QProgressBar, QSplitter, QDialog)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QUrl, QTime, QTimer, QDateTime
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings

from .dialogs.batch_task_dialog import BatchTaskDialog
from .dialogs.history_dialog import HistoryDialog
from .widgets.search_thread import SearchThread
from ..core.llm_browser import LLMBrowser

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("灵析AI浏览器")
        self.setMinimumSize(1200, 800)
        
        # 先创建UI，再初始化其他组件
        self.setup_ui()
        self.setup_web_engine()
        self.initialize_browser()
        
        self.scheduled_tasks = []
        self.history_records = []
        
    def setup_ui(self):
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
        batch_button = QPushButton("批量任务")
        batch_button.clicked.connect(self.show_batch_dialog)
        button_layout.addWidget(batch_button)
        
        # 历史记录按钮
        history_button = QPushButton("历史记录")
        history_button.clicked.connect(self.show_history)
        button_layout.addWidget(history_button)
        
        left_layout.addLayout(button_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(2)
        self.progress_bar.setTextVisible(False)
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
        self.status_display.setMaximumHeight(50)
        self.status_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #333333;
                border-radius: 4px;
                padding: 5px;
                color: #ffffff;
                font-size: 12px;
            }
        """)
        left_layout.addWidget(self.status_display)
        
        # 搜索结果显示
        self.results_display = QTextEdit()
        self.results_display.setReadOnly(True)
        self.results_display.setPlaceholderText("搜索结果将在这里显示...")
        left_layout.addWidget(self.results_display)
        
        # 右侧浏览器
        self.web_view = QWebEngineView()
        self.default_url = QUrl("https://www.bing.com")
        self.web_view.setUrl(self.default_url)
        
        # 将左侧面板和浏览器添加到分割器
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(self.web_view)
        
        # 设置分割比例
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 2)
        
    def setup_web_engine(self):
        profile = QWebEngineProfile.defaultProfile()
        settings = profile.settings()
        
        # 启用必要的功能
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)  # 启用 JavaScript
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
        
        # 禁用不必要的功能
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, False)
        
        # 配置缓存和Cookie策略
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        profile.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
    def initialize_browser(self):
        try:
            self.status_display.append("正在初始化浏览器...")
            self.browser = LLMBrowser(model="glm4:latest")
            self.status_display.append("浏览器初始化完成!")
        except Exception as e:
            self.status_display.append(f"初始化错误: {str(e)}")
            
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
        self.search_thread.status_signal.connect(self.status_display.append)
        self.search_thread.result_signal.connect(self.results_display.append)
        self.search_thread.error_signal.connect(self.status_display.append)
        self.search_thread.url_signal.connect(lambda url: self.web_view.setUrl(QUrl(url)))
        self.search_thread.search_url_signal.connect(lambda url: self.web_view.setUrl(QUrl(url)))
        self.search_thread.progress_signal.connect(self.progress_bar.setValue)
        
        # 启动线程
        self.search_thread.start()
        
    def show_batch_dialog(self):
        dialog = BatchTaskDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.scheduled_tasks = dialog.get_tasks()
            self.schedule_tasks(self.scheduled_tasks)
            
    def show_history(self):
        dialog = HistoryDialog(self)
        dialog.exec()
        
    def schedule_tasks(self, tasks):
        current_time = QTime.currentTime()
        
        for task in tasks:
            content = task['content']
            planned_time = task['time']
            
            delay = current_time.msecsTo(planned_time)
            if delay < 0:
                delay += 24 * 3600 * 1000
            
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda q=content: self.execute_scheduled_task(q))
            timer.start(delay)
            
    def execute_scheduled_task(self, query):
        self.query_input.setPlainText(query)
        self.start_search() 