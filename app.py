import streamlit as st
from main import WorkAssistant
import json

def init_session_state():
    if 'assistant' not in st.session_state:
        st.session_state.assistant = None
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'task_results' not in st.session_state:
        st.session_state.task_results = []

def main():
    st.title("🤖 AI工作助手")
    init_session_state()

    # 侧边栏配置
    with st.sidebar:
        st.header("配置")
        api_base = st.text_input("API地址", value="http://172.31.118.255:11434")
        model = st.text_input("模型名称", value="qwen:7b")
        
        if st.button("初始化助手"):
            try:
                if st.session_state.assistant:
                    st.session_state.assistant.close()
                st.session_state.assistant = WorkAssistant(api_base=api_base, model=model)
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
        submitted = st.form_submit_button("开始执行")
        
        if submitted and task:
            with st.spinner("正在执行任务..."):
                try:
                    results = st.session_state.assistant.execute_task(task)
                    st.session_state.task_results.append({
                        "task": task,
                        "results": results
                    })
                    st.success("任务执行完成！")
                except Exception as e:
                    st.error(f"任务执行失败: {str(e)}")

    # 显示历史结果
    if st.session_state.task_results:
        st.header("执行历史")
        for idx, item in enumerate(st.session_state.task_results):
            with st.expander(f"任务 {idx + 1}: {item['task'][:50]}..."):
                st.write("任务详情:", item["task"])
                st.write("执行结果:")
                for result in item["results"]:
                    st.write(result)

    # 添加退出按钮
    if st.button("退出助手"):
        if st.session_state.assistant:
            st.session_state.assistant.close()
            st.session_state.assistant = None
            st.success("助手已安全退出！")
            st.experimental_rerun()

if __name__ == "__main__":
    main()
