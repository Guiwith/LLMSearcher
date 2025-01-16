from PyQt6.QtCore import QThread, pyqtSignal
from ...core.llm_browser import LLMBrowser

class SearchThread(QThread):
    status_signal = pyqtSignal(str)
    result_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    url_signal = pyqtSignal(str)
    search_url_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)

    def __init__(self, browser: LLMBrowser, query: str):
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
                all_content.append(content['content'])
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