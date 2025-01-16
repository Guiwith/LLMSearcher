from playwright.sync_api import sync_playwright
from typing import Dict, List, Optional
import json

class WebCrawler:
    @staticmethod
    def _analyze_dom_element(element) -> Dict:
        """分析DOM元素的属性和可交互性"""
        element_info = {
            'tag': element.get('tagName', '').lower(),
            'type': 'element',
            'text': element.get('textContent', '').strip(),
            'is_visible': element.get('isVisible', False),
            'is_interactive': element.get('isInteractive', False),
            'attributes': element.get('attributes', {}),
            'children': [],
            'actions': []
        }

        # 分析可执行的操作
        if element_info['is_interactive']:
            if element_info['tag'] == 'a':
                element_info['actions'].append({
                    'type': 'click',
                    'description': f"点击链接: {element_info['text']}"
                })
            elif element_info['tag'] == 'button':
                element_info['actions'].append({
                    'type': 'click',
                    'description': f"点击按钮: {element_info['text']}"
                })
            elif element_info['tag'] == 'input':
                input_type = element_info['attributes'].get('type', 'text')
                if input_type == 'text':
                    element_info['actions'].append({
                        'type': 'input',
                        'description': f"输入文本到: {element_info['attributes'].get('placeholder', '文本框')}"
                    })
                elif input_type in ['submit', 'button']:
                    element_info['actions'].append({
                        'type': 'click',
                        'description': f"点击: {element_info['text'] or element_info['attributes'].get('value', '按钮')}"
                    })

        # 递归处理子元素
        for child in element.get('children', []):
            child_info = WebCrawler._analyze_dom_element(child)
            if child_info:
                element_info['children'].append(child_info)

        return element_info

    @staticmethod
    def search_web(keywords: List[str]) -> List[Dict]:
        """执行网页搜索并返回DOM分析结果"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
                )
                
                search_query = ' '.join(keywords)
                search_url = f"https://www.bing.com/search?q={search_query}"
                page.goto(search_url, wait_until='networkidle')
                
                # 获取搜索结果的DOM结构
                dom_tree = page.evaluate('''
                    () => {
                        function buildNode(element) {
                            if (!element) return null;
                            
                            const node = {
                                tagName: element.tagName,
                                textContent: element.textContent,
                                isVisible: (function() {
                                    const style = window.getComputedStyle(element);
                                    return style.display !== 'none' && 
                                           style.visibility !== 'hidden' && 
                                           style.opacity !== '0';
                                })(),
                                isInteractive: (function() {
                                    return element.tagName === 'A' ||
                                           element.tagName === 'BUTTON' ||
                                           element.tagName === 'INPUT' ||
                                           element.onclick != null ||
                                           element.getAttribute('role') === 'button';
                                })(),
                                attributes: {},
                                children: []
                            };
                            
                            // 获取元素属性
                            for (const attr of element.attributes || []) {
                                node.attributes[attr.name] = attr.value;
                            }
                            
                            // 处理搜索结果
                            if (element.matches('#b_results > li')) {
                                const title = element.querySelector('h2')?.textContent || '';
                                const url = element.querySelector('a')?.href || '';
                                const description = element.querySelector('.b_caption p')?.textContent || '';
                                
                                if (title && url) {
                                    node.searchResult = { title, url, description };
                                }
                            }
                            
                            // 递归处理子元素
                            for (const child of element.children) {
                                const childNode = buildNode(child);
                                if (childNode) {
                                    node.children.push(childNode);
                                }
                            }
                            
                            return node;
                        }
                        
                        return buildNode(document.querySelector('#b_results'));
                    }
                ''')
                
                # 提取搜索结果
                results = []
                def extract_search_results(node):
                    if 'searchResult' in node:
                        results.append(node['searchResult'])
                    for child in node.get('children', []):
                        extract_search_results(child)
                
                extract_search_results(dom_tree)
                return results

        except Exception as e:
            raise Exception(f"搜索网页时发生错误: {str(e)}")

    @staticmethod
    def crawl_page_content(url: str) -> Dict:
        """爬取页面内容并分析DOM结构"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
                )
                
                page.goto(url, wait_until='networkidle')
                
                # 获取页面DOM结构
                dom_tree = page.evaluate('''
                    () => {
                        function buildNode(element) {
                            if (!element) return null;
                            
                            const node = {
                                tagName: element.tagName,
                                textContent: element.textContent,
                                isVisible: (function() {
                                    const style = window.getComputedStyle(element);
                                    return style.display !== 'none' && 
                                           style.visibility !== 'hidden' && 
                                           style.opacity !== '0';
                                })(),
                                isInteractive: (function() {
                                    return element.tagName === 'A' ||
                                           element.tagName === 'BUTTON' ||
                                           element.tagName === 'INPUT' ||
                                           element.onclick != null ||
                                           element.getAttribute('role') === 'button';
                                })(),
                                attributes: {},
                                children: []
                            };
                            
                            // 获取元素属性
                            for (const attr of element.attributes || []) {
                                node.attributes[attr.name] = attr.value;
                            }
                            
                            // 递归处理子元素
                            for (const child of element.children) {
                                const childNode = buildNode(child);
                                if (childNode) {
                                    node.children.push(childNode);
                                }
                            }
                            
                            return node;
                        }
                        
                        return buildNode(document.body);
                    }
                ''')
                
                # 分析DOM树
                analyzed_dom = WebCrawler._analyze_dom_element(dom_tree)
                
                # 提取主要文本内容
                main_content = page.evaluate('''
                    () => {
                        // 移除不需要的元素
                        const elementsToRemove = document.querySelectorAll('script, style, noscript, iframe, img');
                        elementsToRemove.forEach(el => el.remove());
                        
                        // 获取主要内容
                        return document.body.innerText;
                    }
                ''')
                
                return {
                    'url': url,
                    'content': main_content,
                    'dom_tree': analyzed_dom
                }
                
        except Exception as e:
            return {
                'url': url,
                'content': '',
                'dom_tree': None,
                'error': str(e)
            } 