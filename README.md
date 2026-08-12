# 每日 arXiv 论文追踪与中文总结网站

这是一个可以部署在 GitHub 上的自动化论文网站。它每天根据你维护的关键词查询 arXiv，使用 DeepSeek 等兼容 OpenAI API 的模型生成中文总结，为论文添加规范主题标签，并通过 GitHub Pages 展示结果。

整个系统不需要购买服务器，主要使用：

- GitHub Actions：每天自动抓取、总结和更新论文。
- GitHub Pages：托管论文浏览网站。
- DeepSeek API：生成中文论文总结。
- `data` 分支：保存每天生成的论文数据。

> [!CAUTION]
> 论文内容和中文总结可能存在错误。AI 结果只能作为阅读辅助，重要结论请以原论文为准。部署者需要自行承担 API 费用，并负责公开页面的内容合规。

## 功能

- 根据 [`keywords.txt`](./keywords.txt) 自动查询近期 arXiv 论文。
- 默认查询全部 arXiv 学科，也可以限制为指定分类。
- 自动生成 TL;DR、研究动机、方法、结果和结论的中文总结。
- 内置 30 个不重复的规范主题标签。
- 支持按 arXiv 分类、主题标签、作者和文本检索论文。
- 支持单日和日期范围浏览。
- 标签升级时只迁移已有 JSONL 数据，不重新读取 PDF，也不重新调用模型。
- 每天北京时间 09:30 自动运行，也支持手动执行。

## 部署前准备

你需要：

1. 一个 GitHub 账号。
2. 一个 DeepSeek API Key，通常以 `sk-` 开头。
3. 已经 Fork 本仓库，或者把本地代码推送到自己的 GitHub 仓库。

DeepSeek API Key 可以在 DeepSeek 开放平台创建。请勿把 API Key 写入代码、README、Issue 或普通 GitHub Variable。

## 第一步：把项目放到自己的 GitHub

### 方法一：使用 Fork

在原仓库页面点击右上角 `Fork`，选择自己的 GitHub 账号，然后等待仓库创建完成。

如果 GitHub 提示 Fork 中的工作流已停用，进入仓库的 `Actions` 页面，点击：

```text
I understand my workflows, go ahead and enable them
```

### 方法二：推送当前本地代码

确认远程仓库地址后执行：

```bash
git add .
git commit -m "feat: deploy daily arxiv website"
git push origin main
```

当前项目对应的 GitHub Pages 地址通常是：

```text
https://<GitHub用户名>.github.io/<仓库名>/
```

例如仓库是 `KevinClaint/Arxiv-Daliy`，地址就是：

```text
https://kevinclaint.github.io/Arxiv-Daliy/
```

## 第二步：添加 DeepSeek API 配置

打开自己的 GitHub 仓库，依次进入：

```text
Settings
-> Secrets and variables
-> Actions
```

这里有两个不同的页面：

- `Secrets`：保存 API Key 等敏感信息，保存后无法再次查看原文。
- `Variables`：保存模型名、语言等普通配置，会以明文显示。

### 添加 Secrets

进入 `Secrets`，点击 `New repository secret`，分别添加以下两个 Secret。

第一个：

```text
Name: OPENAI_API_KEY
Secret: 你的 DeepSeek API Key
```

示意：

```text
OPENAI_API_KEY = sk-xxxxxxxxxxxxxxxx
```

第二个：

```text
Name: OPENAI_BASE_URL
Secret: https://api.deepseek.com
```

注意：

- Secret 名称必须完全一致，并且区分大小写。
- 值的两侧不要添加引号。
- 不要在末尾添加多余空格。
- `OPENAI_API_KEY` 只能放在 Secrets，不能放在 Variables。

## 第三步：设置模型和总结语言

仍然在：

```text
Settings
-> Secrets and variables
-> Actions
```

进入 `Variables`，点击 `New repository variable`。

推荐配置如下：

| Variable 名称 | 推荐值 | 说明 |
| --- | --- | --- |
| `MODEL_NAME` | `deepseek-chat` | 用于生成论文结构化总结的模型 |
| `LANGUAGE` | `Chinese` | 让模型输出中文总结 |
| `LOOKBACK_DAYS` | `7` | 每次回看最近 7 天，覆盖周末或延迟发布 |
| `DAILY_PAPER_LIMIT` | `500` | 每次最多处理的新论文数量 |

其中最重要的是：

```text
MODEL_NAME = deepseek-chat
LANGUAGE = Chinese
```

如果没有设置，工作流也会默认使用这两个值。

### 是否需要设置 CATEGORIES

`CATEGORIES` 是可选变量。

- 不创建或留空：在全部 arXiv 学科中查询关键词，覆盖范围最大。
- 设置分类：只查询指定学科，速度更快、无关结果更少。

示例：

```text
CATEGORIES = cs.AI, cs.CV, cs.LG, cs.RO
```

常见分类：

| 分类 | 含义 |
| --- | --- |
| `cs.AI` | 人工智能 |
| `cs.CV` | 计算机视觉 |
| `cs.LG` | 机器学习 |
| `cs.CL` | 计算语言学 |
| `cs.RO` | 机器人 |
| `cs.GR` | 计算机图形学 |
| `stat.ML` | 统计机器学习 |
| `eess.IV` | 图像与视频处理 |

如果目标是“尽可能广地抓取关键词论文”，不要设置 `CATEGORIES`。

## 第四步：允许 GitHub Actions 自动提交

进入：

```text
Settings
-> Actions
-> General
-> Workflow permissions
```

选择：

```text
Read and write permissions
```

然后点击 `Save`。

这是必需设置。工作流需要把网页配置推送到 `main` 分支，并把每日论文数据推送到 `data` 分支。

如果仓库启用了分支保护，还需要允许 GitHub Actions 向 `main` 分支提交，或者为机器人提交配置例外规则。

## 第五步：设置抓取关键词

编辑仓库根目录的 [`keywords.txt`](./keywords.txt)。每行填写一个关键词或短语：

```text
video world model
physics-aware video generation
3D scene understanding
spatial reasoning
physical reasoning
```

规则：

- 每行一个关键词或短语。
- `#` 开头的行是注释，不参与查询。
- 空行会被忽略。
- 匹配不区分英文大小写。
- 多个关键词之间是“或”的关系，命中任意一个就会收录。
- 多词短语中的各个词需要同时出现在标题或摘要查询结果中。

关键词数量较多时，程序会自动分批请求 arXiv，然后合并和去重结果，避免查询地址过长。

修改完成后提交：

```bash
git add keywords.txt
git commit -m "chore: update arxiv keywords"
git push origin main
```

## 第六步：手动运行一次工作流

打开仓库的 `Actions` 页面，然后：

1. 点击左侧的 `arXiv-daily-ai-enhanced`。
2. 点击右侧的 `Run workflow`。
3. Branch 选择 `main`。
4. 再点击绿色的 `Run workflow`。

第一次运行可能需要较长时间，具体取决于命中的论文数量和模型接口速度。

工作流主要执行以下步骤：

1. 安装 Python 依赖。
2. 从 `data` 分支恢复历史论文数据。
3. 根据 `keywords.txt` 查询近期 arXiv 论文。
4. 与全部历史论文 ID 去重。
5. 调用 DeepSeek 生成中文总结。
6. 为论文添加或迁移主题标签。
7. 将网页配置提交到 `main` 分支。
8. 将论文 JSONL 数据提交到 `data` 分支。

运行成功后，日志中通常可以看到：

```text
Connect to: deepseek-chat
```

以及论文处理、标签更新和分支推送完成的信息。

## 第七步：开启 GitHub Pages

进入：

```text
Settings
-> Pages
```

在 `Build and deployment` 中设置：

```text
Source: Deploy from a branch
Branch: main
Folder: /(root)
```

点击 `Save`。等待几分钟后，GitHub 会显示网站地址：

```text
https://<GitHub用户名>.github.io/<仓库名>/
```

首次工作流执行时会自动把网站的数据源地址修改为你自己的仓库，因此建议先成功运行一次 Actions，再检查 Pages。

## 每日自动更新时间

工作流配置位于 [`.github/workflows/run.yml`](./.github/workflows/run.yml)。当前定时表达式是：

```yaml
schedule:
  - cron: "30 1 * * *"
```

GitHub Actions 使用 UTC 时间，`01:30 UTC` 对应北京时间每天 `09:30`。

如果想改为北京时间每天 08:00：

```yaml
schedule:
  - cron: "0 0 * * *"
```

GitHub 的定时任务可能因平台负载延迟几分钟，这是正常现象。

## 网站如何检索论文

网站支持：

- `Category`：按 arXiv 学科分类查看。
- `主题标签`：点击一个或多个规范标签筛选论文。
- `Filter`：按个人关键词或作者偏好高亮论文。
- 搜索按钮：在标题、作者、摘要、中文总结和标签中搜索文本。
- 日历按钮：查看某一天或一个日期范围内的论文。

也可以通过 URL 查询规范标签：

```text
https://<你的网站地址>/?tags=world-models,physical-ai
```

多个标签之间是“或”的关系。URL 标签模式会输出匹配论文的 JSON，方便其他脚本调用。

## 30 个主题标签如何维护

规范标签保存在 [`tag_catalog.json`](./tag_catalog.json)。每个标签包含：

```json
{
  "id": "world-models",
  "label": "世界模型",
  "terms": ["world model", "world simulator", "world simulation"]
}
```

- `id`：稳定的内部标识，不应随意修改。
- `label`：网站展示的中文名称。
- `terms`：从标题、摘要和已有中文总结中判断标签的代表性词组。

系统会校验：

- 标签数量必须保持在 25 到 35 个之间。
- 当前默认维护 30 个标签。
- 标签 `id` 不能重复。
- 中文 `label` 不能重复。
- 每个标签必须至少包含一个匹配词组。

### 替换标签时的正确做法

不能直接删除旧标签 ID。你需要提高 `schema_version`，并添加迁移记录。

例如把旧标签 `video-ai` 拆成 `video-generation` 和 `world-models`：

```json
{
  "schema_version": 2,
  "tags": [
    {
      "id": "video-generation",
      "label": "视频生成",
      "terms": ["video generation"]
    },
    {
      "id": "world-models",
      "label": "世界模型",
      "terms": ["world model"]
    }
  ],
  "migrations": [
    {
      "from_version": 1,
      "to_version": 2,
      "replace": {
        "video-ai": ["video-generation", "world-models"]
      }
    }
  ]
}
```

一对一替换写法：

```json
"replace": {
  "old-tag": ["new-tag"]
}
```

一对多拆分写法：

```json
"replace": {
  "old-tag": ["new-tag-a", "new-tag-b"]
}
```

迁移时 [`tag_papers.py`](./tag_papers.py) 只读取历史 JSONL 中已有的标题、摘要、中文总结和标签字段：

- 不下载或读取 PDF。
- 不重新调用 DeepSeek。
- 不重新生成论文总结。
- 可以重复运行，已经迁移完成的数据不会再次变化。

本地验证命令：

```bash
uv run python tag_papers.py --data-dir data
uv run python -m unittest discover -s tests -v
```

## 本地运行

项目要求 Python 3.12 或更高版本，推荐使用 `uv`。

安装依赖：

```bash
uv sync --frozen
```

设置环境变量：

```bash
export OPENAI_API_KEY="你的 DeepSeek API Key"
export OPENAI_BASE_URL="https://api.deepseek.com"
export MODEL_NAME="deepseek-chat"
export LANGUAGE="Chinese"
```

执行与 GitHub Actions 接近的本地流程：

```bash
bash run.sh
```

仅启动静态网站：

```bash
python -m http.server 8000
```

然后访问：

```text
http://127.0.0.1:8000/
```

注意：网站默认从 GitHub 的 `data` 分支读取论文数据，因此本地页面展示的仍然可能是远程数据。

## 历史论文检索和 EndNote 导出

[`search_arxiv.py`](./search_arxiv.py) 用于检索较长时间范围内的历史论文。默认关键词同样来自 `keywords.txt`。

直接使用文件中的配置：

```bash
uv run python search_arxiv.py
```

临时指定关键词、日期和 RIS 输出文件：

```bash
uv run python search_arxiv.py \
  "video world model" \
  "spatial reasoning" \
  --start-date 2020-01-01 \
  --end-date 2026-12-31 \
  --output papers.ris
```

其他格式：

```bash
uv run python search_arxiv.py "world model" --output papers.csv
uv run python search_arxiv.py "world model" --output papers.jsonl
```

历史检索支持断点续传。输出旁边会生成 `<输出文件>.checkpoint.json`；请求限流或程序中断后，使用相同参数重新运行即可继续。使用 `--no-resume` 可以覆盖旧结果并从头开始。

## 常见问题

### Actions 提示没有写权限

检查：

```text
Settings -> Actions -> General -> Workflow permissions
```

必须选择 `Read and write permissions`。同时检查 `main` 分支保护规则是否阻止机器人提交。

### 提示 OPENAI_API_KEY 不存在或认证失败

检查 Secret 名称是否严格为：

```text
OPENAI_API_KEY
```

确认它创建在 `Repository secrets` 中，而不是 Variables 中。还要确认 DeepSeek 账号有可用余额。

### 提示模型不存在

检查 Variables：

```text
MODEL_NAME = deepseek-chat
```

检查 Secret：

```text
OPENAI_BASE_URL = https://api.deepseek.com
```

模型名不要添加引号。

### 工作流成功，但当天没有论文

这通常表示最近的论文没有命中关键词，或者已经存在于历史数据中。可以：

- 扩展 `keywords.txt`。
- 增大 `LOOKBACK_DAYS`。
- 确认没有设置过窄的 `CATEGORIES`。
- 查看 `Fetch recent arXiv papers by keyword` 步骤中的查询日志。

### Pages 打开后没有数据

依次检查：

1. Actions 是否至少成功运行过一次。
2. 仓库中是否已经存在 `data` 分支。
3. Pages 是否选择 `main` 和 `/(root)`。
4. `js/data-config.js` 中是否已经变成你自己的仓库用户名和仓库名。
5. 如果仓库是私有仓库，浏览器可能无法匿名读取 Raw 数据；推荐将用于公开 Pages 的仓库设为 Public。

### DeepSeek 调用费用太高

可以：

- 缩小 `keywords.txt`。
- 设置 `CATEGORIES` 限制学科。
- 降低 `DAILY_PAPER_LIMIT`。
- 先手动运行并观察每日命中数量，再决定自动任务配置。

## 关键文件说明

| 文件 | 用途 |
| --- | --- |
| [`keywords.txt`](./keywords.txt) | 每日抓取和历史检索共用的关键词 |
| [`fetch_daily.py`](./fetch_daily.py) | 查询近期 arXiv 论文并做历史去重 |
| [`ai/enhance.py`](./ai/enhance.py) | 调用模型生成论文总结 |
| [`tag_catalog.json`](./tag_catalog.json) | 30 个规范主题标签和迁移记录 |
| [`tag_papers.py`](./tag_papers.py) | 为论文打标签并迁移旧标签 |
| [`index.html`](./index.html) | 网站首页 |
| [`js/app.js`](./js/app.js) | 网站加载、搜索、标签筛选逻辑 |
| [`.github/workflows/run.yml`](./.github/workflows/run.yml) | 每日自动任务和数据提交流程 |
| [`search_arxiv.py`](./search_arxiv.py) | 历史论文检索及 RIS/CSV/JSONL 导出 |

## 安全建议

- 永远不要把 API Key 提交到 Git。
- 不要在 Actions 日志中打印 API Key。
- 定期检查 DeepSeek API 用量和余额。
- API Key 泄露后应立即在 DeepSeek 平台撤销并重新创建。
- 公开网站上的 AI 总结必须人工甄别，不能代替原论文。

## 验证项目

运行全部自动测试：

```bash
uv run python -m unittest discover -s tests -v
```

检查 JavaScript 语法：

```bash
node --check js/app.js
```

检查本地流程脚本：

```bash
bash -n run.sh
```

## 开源许可与致谢

项目使用 Apache-2.0 License，详见 [`LICENSE`](./LICENSE)。本项目基于 `daily-arXiv-ai-enhanced` 继续开发，感谢原项目作者和所有贡献者。
