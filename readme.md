本项目为NUTT开源项目，遵循GPL-3.0协议，欢迎大家使用和贡献。

![](example.png)

LLM-Searcher 是一个基于LLM的搜索引擎，可以自动执行搜索任务，并返回搜索结果。

项目基于Openai的API格式，使用Ollama的glm4模型(目前仅测试9b)，并使用Selenium库进行网页操作。使用Ollama仅因为agent消耗token量巨大，所以希望能够有本地ollama来替代。目前效果较差，还在不断开发调试中。

安装请使用poetry，并使用python3.10以上版本。

1.建立虚拟环境

```
python -m venv venv
venv/Scripts/activate
```

2.安装poetry

```
pip install poetry
```

3.安装依赖

```
poetry install
```

4.启动脚本

```
streamlit run app.py 
```

