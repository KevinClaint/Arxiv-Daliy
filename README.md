# 🚀 daily-arXiv-ai-enhanced

> [!CAUTION]
> 若您所在法域对学术数据有审查要求，谨慎运行本代码；任何二次分发版本必须履行合规审查（包括但不限于原始论文合规性、AI合规性）义务，否则一切法律后果由下游自行承担。

> [!CAUTION]
> If your jurisdiction has censorship requirements for academic data, run this code with caution; any secondary distribution version must remove the entrance accessible to China and fulfill the content review obligations, otherwise all legal consequences will be borne by the downstream.


This innovative tool transforms how you stay updated with arXiv papers by combining automated crawling with AI-powered summarization.


## ✨ Key Features

🎯 **Zero Infrastructure Required**
- Leverages GitHub Actions and Pages - no server needed
- Completely free to deploy and use

🤖 **Smart AI Summarization**
- Daily paper crawling with DeepSeek-powered summaries
- Cost-effective: Only ~0.2 CNY per day

💫 **Smart Reading Experience**
- Personalized paper highlighting based on your interests
- Cross-device compatibility (desktop & mobile)
- Local preference storage for privacy
- Flexible date range filtering

🧩 **SKILL System**
- Plug-and-play skill modules for customizing paper filtering

⚙️ **Easy Preference Export & Integration**
- One-click copy in Settings to export your keywords and authors configuration
- Seamlessly combine exported preferences with SKILL for reproducible and shareable setups

👉 **[Try it now!](https://dw-dengwei.github.io/daily-arXiv-ai-enhanced/)** - No installation required



https://github.com/user-attachments/assets/b25712a4-fb8d-484f-863d-e8da6922f9d7




# How to use
This repo searches recent papers across **all arXiv fields** using your shared keyword list, and uses an OpenAI-compatible model such as **DeepSeek** to summarize them in **Chinese**.
You can optionally restrict arXiv categories, change the model, or change the output language in GitHub Actions variables.
Otherwise, you can watch the video above first and directly use this repo in https://dw-dengwei.github.io/daily-arXiv-ai-enhanced/. Please star it if you like :)

## 部署到你自己的 GitHub，每日按关键词更新

1. 修改仓库根目录的 [`keywords.txt`](./keywords.txt)：每行一个关键词或短语，`#` 开头的行是注释。每日任务直接通过 arXiv API 在标题和摘要中查询，命中任意一条就保留；默认覆盖所有 arXiv 学科。
2. 把仓库推送到你自己的 GitHub，或在 GitHub 上 Fork 后提交对 `keywords.txt` 的修改。
3. 打开仓库的 `Settings -> Actions -> General`，在 `Workflow permissions` 中选择 `Read and write permissions`。
4. 在 `Settings -> Secrets and variables -> Actions` 中添加下方列出的 Secrets 和 Variables。
5. 打开 `Actions`，如果 GitHub 提示 Fork 的工作流已停用，先点击 `I understand my workflows, go ahead and enable them`；然后进入 `arXiv-daily-ai-enhanced -> Run workflow` 手动测试一次。正常运行后，任务会在每天北京时间 09:30 自动执行。
6. 打开 `Settings -> Pages`，选择 `Deploy from a branch`，分支设为 `main`，目录设为 `/(root)`。页面地址是 `https://<你的用户名>.github.io/<仓库名>/`。

必需的 Secrets：

- `OPENAI_API_KEY`：用于生成论文摘要的模型 API Key。
- `OPENAI_BASE_URL`：OpenAI 兼容接口地址，例如 DeepSeek 的 `https://api.deepseek.com`。

建议添加的 Variables：

- `CATEGORIES`：可选。留空代表查询全部 arXiv 学科；只有确实要缩小范围时才填写，例如 `cs.AI, cs.CV, cs.LG`。
- `LANGUAGE`：摘要语言，例如 `Chinese`。
- `MODEL_NAME`：模型名，例如 `deepseek-chat`。
- `LOOKBACK_DAYS`：每日回看天数，默认 `7`，用于覆盖周末、延迟发布和临时失败。
- `DAILY_PAPER_LIMIT`：每日最多处理的新论文数，默认 `500`。
- `EMAIL`、`NAME`：可选的自动提交身份；未设置时使用 `github-actions[bot]`。

`ACCESS_PASSWORD` 和 `TOKEN_GITHUB` 是可选 Secret。前者控制网页访问密码，后者仅用于查询论文中 GitHub 项目的额外信息。GitHub 定时表达式使用 UTC；当前 `30 1 * * *` 对应北京时间每天 09:30。

## 主题标签库与向下兼容更新

[`tag_catalog.json`](./tag_catalog.json) 是网站的规范主题标签库，目前包含 30 个不重复标签。每个标签包括稳定的英文 `id`、网页显示的中文 `label`，以及用于从标题、摘要和已保存 AI 总结打标的 `terms`。网页会显示这些标签，并支持点击一个或多个标签检索论文。

也可以通过 URL 按标签查询，例如 `?tags=world-models,physical-ai`。多个标签之间是“或”关系；该模式会输出匹配论文的 JSON，适合分享检索条件或供其他工具调用。

标签更新不读取 PDF，也不重新调用大模型。每日工作流会运行 `tag_papers.py`，只根据仓库中已经保存的标题、摘要、中文总结和旧 `tags` 字段更新 JSONL。首次为旧论文补标签后，后续更新只执行版本迁移。

替换标签时必须同时维护迁移记录：

1. 将 `schema_version` 加一。
2. 在 `tags` 中加入新的规范标签，并删除被替换的旧标签。
3. 在 `migrations` 末尾追加连续版本迁移。一个旧标签可以映射到一个或多个新标签。

例如将旧标签 `video-ai` 拆成两个标签：

```json
{
  "from_version": 1,
  "to_version": 2,
  "replace": {
    "video-ai": ["video-generation", "world-models"]
  }
}
```

提交后可以先在本地验证：

```bash
uv run python tag_papers.py --data-dir data
uv run python -m unittest discover -s tests -v
```

迁移链不连续、标签 ID/中文名重复、数量偏离约 30 个，或者旧标签无法迁移到当前标签时，任务会直接失败，避免历史标签被静默丢弃。

## Search historical papers by keyword

`search_arxiv.py` searches all matching arXiv papers from oldest to newest and
exports their titles, abstracts, authors, dates, categories, abstract links, and
PDF links. The end date is inclusive, and searches are automatically paginated
until the configured result limit has been reached.

Set keywords in `keywords.txt` and the remaining search options in the
configuration block near the top of `search_arxiv.py`, then run the script
without arguments. `MAX_RESULTS` controls
the maximum number of exported papers; set it to `None` to export every match.
Add phrases to `keywords.txt`, and use `KEYWORD_OPERATOR = "OR"` to match any
phrase or `"AND"` to require all phrases. Set `SEARCH_CATEGORIES = ["cs"]` for
all computer science categories, list exact categories such as `cs.AI` and
`cs.CV`, or use an empty list to search without a category restriction.

```bash
uv run python search_arxiv.py
```

You can also override that setting for one run by passing one or more keywords:

```bash
uv run python search_arxiv.py "large language model" "vision language model" \
  --start-date 2018-01-01 \
  --end-date 2024-12-31 \
  --output papers.ris
```

The default output is an RIS file that can be imported directly into EndNote.
Use `--output papers.csv` for CSV, `--output papers.jsonl` for JSON Lines,
`--field title` to search titles only, or
`--match all` to require every word instead of matching an exact phrase. Run
`uv run python search_arxiv.py --help` for all options. arXiv requests are rate
limited by default, so a large historical search can take some time.

The search resumes by default. It appends to the existing output and stores the
next arXiv offset in `<output>.checkpoint.json`. If a request is rate limited or
the process is interrupted, wait for arXiv access to recover and run the same
command again. The query and output format must stay unchanged. Use a different
output path for a different query. `--no-resume` explicitly discards the old
output and starts over.

# Contributors
Thanks to the following special contributors for contributing code, discovering bugs, and sharing useful ideas for this project!!!
<table>
  <tbody>
    <tr>
      <td align="center" valign="top">
        <a href="https://github.com/JianGuanTHU"><img src="https://avatars.githubusercontent.com/u/44895708?v=4" width="100px;" alt="JianGuanTHU"/><br /><sub><b>JianGuanTHU</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://github.com/Chi-hong22"><img src="https://avatars.githubusercontent.com/u/75403952?v=4" width="100px;" alt="Chi-hong22"/><br /><sub><b>Chi-hong22</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://github.com/chaozg"><img src="https://avatars.githubusercontent.com/u/69794131?v=4" width="100px;" alt="chaozg"/><br /><sub><b>chaozg</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://github.com/quantum-ctrl"><img src="https://avatars.githubusercontent.com/u/16505311?v=4" width="100px;" alt="quantum-ctrl"/><br /><sub><b>quantum-ctrl</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://github.com/Zhao2z"><img src="https://avatars.githubusercontent.com/u/141019403?v=4" width="100px;" alt="Zhao2z"/><br /><sub><b>Zhao2z</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://github.com/eclipse0922"><img src="https://avatars.githubusercontent.com/u/6214316?v=4" width="100px;" alt="eclipse0922"/><br /><sub><b>eclipse0922</b></sub></a><br />
      </td>
    </tr>


  </tbody>
  <tbody>
   <tr>
      <td align="center" valign="top">
        <a href="https://github.com/xuemian168"><img src="https://avatars.githubusercontent.com/u/38741078?v=4" width="100px;" alt="xuemian168"/><br /><sub><b>xuemian168</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://github.com/Lrrrr549"><img src="https://avatars.githubusercontent.com/u/71866027?v=4" width="100px;" alt="Lrrrr549"/><br /><sub><b>Lrrrr549</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://github.com/AinzRimuru"><img src="https://avatars.githubusercontent.com/u/59441476?v=4" width="100px;" alt="AinzRimuru"/><br /><sub><b>AinzRimuru</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://github.com/fengxueguiren"><img src="https://avatars.githubusercontent.com/u/153522370?v=4" width="100px;" alt="fengxueguiren"/><br /><sub><b>fengxueguiren</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://github.com/zerocpp"><img src="https://avatars.githubusercontent.com/u/2630297?v=4" width="100px;" alt="fengxueguiren"/><br /><sub><b>zerocpp</b></sub></a><br />
      </td>
   </tr>
  </tbody>
</table>

# Acknowledgement
We sincerely thank the following individuals and organizations for their promotion and support!!!
<table>
  <tbody>
    <tr>
      <td align="center" valign="top">
        <a href="https://x.com/GitHub_Daily/status/1930610556731318781"><img src="https://pbs.twimg.com/profile_images/1660876795347111937/EIo6fIr4_400x400.jpg" width="100px;" alt="Github_Daily"/><br /><sub><b>Github_Daily</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://x.com/aigclink/status/1930897858963853746"><img src="https://pbs.twimg.com/profile_images/1729450995850027008/gllXr6bh_400x400.jpg" width="100px;" alt="AIGCLINK"/><br /><sub><b>AIGCLINK</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://www.ruanyifeng.com/blog/2025/06/weekly-issue-353.html"><img src="https://avatars.githubusercontent.com/u/905434" width="100px;" alt="阮一峰的网络日志"/><br /><sub><b>阮一峰的网络日志 <br> 科技爱好者周刊 <br> （第 353 期）</b></sub></a><br />
      </td>
      <td align="center" valign="top">
        <a href="https://hellogithub.com/periodical/volume/111"><img src="https://github.com/user-attachments/assets/eff6b6dd-0323-40c4-9db6-444a51bbc80a" width="100px;" alt="《HelloGitHub》第 111 期"/><br /><sub><b>《HelloGitHub》<br> 月刊第 111 期</b></sub></a><br />
      </td>
    </tr>
  </tbody>
</table>


# Star history

[![Stargazers over time](https://starchart.cc/dw-dengwei/daily-arXiv-ai-enhanced.svg?variant=adaptive)](https://starchart.cc/dw-dengwei/daily-arXiv-ai-enhanced)

# Buy me a coffee
[here](./buy-me-a-coffee/README.md)
