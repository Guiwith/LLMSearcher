import streamlit as st
from main import WorkAssistant
import json
from datetime import datetime

# 隐藏默认菜单和页脚
st.set_page_config(
    page_title="LLM Searcher",
    page_icon="🤖",
    layout="wide",
    menu_items=None  # 这将隐藏默认菜单
)

# 隐藏Streamlit默认样式
hide_st_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

def init_session_state():
    if 'assistant' not in st.session_state:
        st.session_state.assistant = None
    if 'task_results' not in st.session_state:
        st.session_state.task_results = []

def main():
    st.title("🤖 LLM Searcher")
    init_session_state()

    # 侧边栏配置
    with st.sidebar:
        st.header("配置")
        api_base = st.text_input("API地址", value="http://172.31.118.255:11434")
        model = st.text_input("模型名称", value="glm4:latest")
        auto_close = st.checkbox("任务完成后自动关闭浏览器", value=True)
        headless = st.checkbox("使用无头模式（隐藏浏览器）", value=False)
        
        if st.button("初始化助手"):
            try:
                if st.session_state.assistant:
                    st.session_state.assistant.close()
                st.session_state.assistant = WorkAssistant(
                    api_base=api_base, 
                    model=model,
                    auto_close_browser=auto_close,
                    headless=headless
                )
                st.success("助手初始化成功！")
            except Exception as e:
                st.error(f"初始化失败: {str(e)}")

    # 主界面
    if st.session_state.assistant is None:
        st.warning("请先在侧边栏初始化助手")
        return

    # 任务输入区
    with st.form("task_form"):
        task = st.text_area("请输入您的任务需求:", 
                           placeholder="例如：在百度上搜索'Python教程'并收集前三个非广告结果的信息")
        keep_browser = st.checkbox("保持浏览器打开", value=not auto_close)
        submitted = st.form_submit_button("开始执行")
        
        if submitted and task:
            with st.spinner("正在执行任务..."):
                try:
                    # 临时设置浏览器关闭选项
                    original_setting = st.session_state.assistant.auto_close_browser
                    st.session_state.assistant.auto_close_browser = not keep_browser
                    
                    results = st.session_state.assistant.execute_task(task)
                    st.session_state.task_results.append({
                        "task": task,
                        "results": results,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    # 恢复原始设置
                    st.session_state.assistant.auto_close_browser = original_setting
                    st.success("任务执行完成！")
                except Exception as e:
                    st.error(f"任务执行失败: {str(e)}")

    # 显示历史结果
    if st.session_state.task_results:
        st.header("执行历史")
        
        # 添加清空历史按钮
        if st.button("清空所有历史"):
            st.session_state.task_results = []
            st.success("历史记录已清空！")
            st.rerun()
            
        # 反转列表，最新的结果显示在最上面
        for idx, item in enumerate(reversed(st.session_state.task_results)):
            real_idx = len(st.session_state.task_results) - idx - 1  # 计算真实索引
            
            # 使用列布局来放置任务内容和删除按钮
            col1, col2 = st.columns([6, 1])
            
            with col1:
                with st.expander(f"任务 {real_idx + 1}: {item['task'][:50]}..."):
                    st.write("任务详情:", item["task"])
                    st.write("执行结果:", item["results"])
                    st.text(f"执行时间: {item.get('timestamp', '未记录')}")
            
            with col2:
                # 为每个任务添加删除按钮
                if st.button("删除", key=f"delete_{real_idx}"):
                    st.session_state.task_results.pop(real_idx)
                    st.success(f"已删除任务 {real_idx + 1}")
                    st.rerun()

    # 添加手动关闭浏览器按钮
    if st.session_state.assistant and st.button("关闭浏览器"):
        try:
            st.session_state.assistant.close()
            st.success("浏览器已关闭！")
        except Exception as e:
            st.error(f"关闭浏览器失败: {str(e)}")

    # 添加退出助手按钮
    if st.button("退出助手"):
        if st.session_state.assistant:
            st.session_state.assistant.close()
            st.session_state.assistant = None
            st.success("助手已安全退出！")
            st.rerun()

if __name__ == "__main__":
    main()
