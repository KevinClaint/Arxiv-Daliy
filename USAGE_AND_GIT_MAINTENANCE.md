# daily-arXiv-ai-enhanced 使用与 Git 更新维护指南

本文适用于当前仓库：

```text
/Users/kevin/Desktop/code/research/tools/arxiv/daily-arXiv-ai-enhanced
```

项目每天抓取指定 arXiv 分类的新论文，调用兼容 OpenAI API 的大语言模型生成摘要，再通过 GitHub Pages 展示结果。推荐把 GitHub Actions 作为正式运行环境，把本地环境用于调试和开发。

## 1. 项目结构

| 路径 | 用途 |
| --- | --- |
| `.github/workflows/run.yml` | 每日自动抓取、AI 处理、生成页面数据并提交到 GitHub |
| `daily_arxiv/` | Scrapy 爬虫和论文去重逻辑 |
| `ai/` | 调用大语言模型生成结构化摘要 |
| `to_md/` | 把 AI 增强后的 JSONL 转为 Markdown |
| `data/` | 运行时生成的论文数据；线上数据主要保存在 `data` 分支 |
| `index.html`、`settings.html`、`statistic.html` | GitHub Pages 静态网站入口 |
| `js/`、`css/` | 前端逻辑和样式 |
| `run.sh` | 本地完整/部分调试流程 |
| `setup-local-auth.sh` | 本地页面密码配置脚本 |
| `pyproject.toml`、`uv.lock` | Python 依赖定义和锁文件 |

项目要求 Python 3.12，依赖由 `uv` 管理。

## 2. 推荐用法：通过 GitHub Actions 每日运行

### 2.1 配置 Actions 权限

工作流需要向 `main` 和 `data` 分支提交内容。在 GitHub 仓库中打开：

```text
Settings -> Actions -> General -> Workflow permissions
```

选择 `Read and write permissions` 并保存。如果仓库设置了分支保护，还需要允许 GitHub Actions 写入相应分支。

### 2.2 配置 Secrets

打开：

```text
Settings -> Secrets and variables -> Actions -> Secrets
```

添加以下 Repository secrets：

| 名称 | 是否必需 | 说明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 是 | 模型服务的 API Key |
| `OPENAI_BASE_URL` | 是 | OpenAI 兼容接口地址，以模型服务商文档为准 |
| `TOKEN_GITHUB` | 否 | 查询论文代码仓库信息时使用，可降低 GitHub API 限流影响 |
| `ACCESS_PASSWORD` | 否 | 网页访问密码；不设置时网站不启用密码保护 |

API Key、Token 和密码只能放在 Secrets 中，不要写入代码、提交记录或普通 Variables。

### 2.3 配置 Variables

在同一页面进入 `Variables`，添加：

| 名称 | 示例 | 说明 |
| --- | --- | --- |
| `CATEGORIES` | `cs.AI, cs.CL, cs.CV` | arXiv 分类，使用英文逗号分隔 |
| `LANGUAGE` | `Chinese` | AI 摘要的输出语言 |
| `MODEL_NAME` | `deepseek-chat` | 与 API 服务匹配的模型名称 |
| `EMAIL` | `your-email@example.com` | Actions 自动提交时使用的 Git 邮箱 |
| `NAME` | `Your Name` | Actions 自动提交时使用的 Git 用户名 |

上述五个 Variables 建议全部配置。尤其不要把 `CATEGORIES` 留空，否则爬虫会构造无效的分类地址。

### 2.4 手动测试工作流

首次运行前，必须检查两个前端配置文件。当前检出的版本已经包含原项目运行后生成的值，而工作流只会替换占位符：

```javascript
// js/data-config.js
repoOwner: 'PLACEHOLDER_REPO_OWNER',
repoName: 'PLACEHOLDER_REPO_NAME',

// js/auth-config.js
passwordHash: 'PLACEHOLDER_PASSWORD_HASH',
```

对于当前 fork，应采用下面两种方式之一：

1. 推荐在首次运行前把上述三个字段恢复为占位符并提交。Actions 会注入 `KevinClaint`、仓库名和密码哈希；
2. 如果不需要工作流注入仓库信息，可直接把 `repoOwner` 固定为 `KevinClaint`，把 `repoName` 固定为 `daily-arXiv-ai-enhanced`。

当前 `js/data-config.js` 中的 `repoOwner` 是 `dw-dengwei`。如果不处理，fork 的网页仍会读取原作者的数据。当前 `js/auth-config.js` 中的密码值是禁用状态；如果需要密码保护，必须先恢复 `PLACEHOLDER_PASSWORD_HASH`，仅添加 `ACCESS_PASSWORD` Secret 不会替换现有禁用值。

工作流会把生成后的值提交到 `main`。以后修改 `ACCESS_PASSWORD` 时，需要再次把 `passwordHash` 恢复为 `PLACEHOLDER_PASSWORD_HASH` 并触发工作流，否则新密码不会生效。

打开：

```text
Actions -> arXiv-daily-ai-enhanced -> Run workflow
```

首次运行可能耗时较长。依次检查以下步骤是否成功：

1. 安装依赖；
2. 抓取 arXiv 论文；
3. 去重；
4. AI 摘要；
5. Markdown 转换；
6. 更新 `main` 分支的配置；
7. 创建或更新 `data` 分支。

工作流配置的定时表达式是 `30 1 * * *`，即每天 UTC 01:30，上海时间通常为 09:30。GitHub 的定时任务可能有一定延迟。

### 2.5 启用 GitHub Pages

打开：

```text
Settings -> Pages
```

设置：

```text
Source: Deploy from a branch
Branch: main
Folder: /(root)
```

当前 fork 对应的默认页面地址通常是：

```text
https://KevinClaint.github.io/daily-arXiv-ai-enhanced/
```

页面源码位于 `main` 分支，论文 JSONL/Markdown 数据由工作流写入 `data` 分支。不要把 `data` 分支合并进 `main`。

密码校验发生在浏览器端，公开仓库的 `data` 分支及其原始文件仍可被直接访问。因此 `ACCESS_PASSWORD` 只能阻挡普通页面访问，不能作为敏感或私密数据的安全隔离措施。

## 3. 本地安装和运行

### 3.1 安装 uv 和 Python 3.12

macOS 可使用 Homebrew：

```bash
brew install uv
```

也可以使用 uv 官方安装脚本：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

然后进入项目并安装锁定版本的依赖：

```bash
cd /Users/kevin/Desktop/code/research/tools/arxiv/daily-arXiv-ai-enhanced
uv python install 3.12
uv sync --frozen
source .venv/bin/activate
```

`uv sync --frozen` 严格使用现有 `uv.lock`，适合日常运行。如果主动修改了依赖，再使用 `uv sync` 更新环境和锁文件。

### 3.2 设置本地环境变量

在当前终端中执行，值按自己的服务替换：

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="your-openai-compatible-base-url"
export MODEL_NAME="deepseek-chat"
export LANGUAGE="Chinese"
export CATEGORIES="cs.AI, cs.CL, cs.CV"
export TOKEN_GITHUB="your-optional-github-token"
```

这些 `export` 只对当前终端会话生效，关闭终端后不会保留。不要把真实密钥写入本指南或任何被 Git 跟踪的文件。

### 3.3 运行完整流程

确认已经激活 `.venv`，然后在项目根目录执行：

```bash
mkdir -p data
./run.sh
```

脚本会执行：抓取当天数据、与历史数据去重、生成 AI 摘要、转换 Markdown、更新文件列表。

注意：

- 脚本按 UTC 日期生成当天文件，重复运行会先删除当天已有的 JSONL；需要保留旧结果时应先备份。
- 去重脚本使用本机本地日期。在上海时区的 00:00 至 08:00 左右运行时，可能和 UTC 文件日期不一致；遇到“今日数据文件不存在”时应在 08:00 后重试，或统一两个脚本的时区逻辑。
- 完整流程会产生模型 API 费用并访问 arXiv、模型接口、GitHub API及项目配置的内容检查接口。
- 未设置 `OPENAI_API_KEY` 时，脚本会询问是否只执行抓取和去重；部分模式不会生成 AI 摘要和 Markdown。
- 生成文件通常不应和功能代码混在同一次提交中。

### 3.4 本地预览网页

在项目根目录启动静态服务器：

```bash
python -m http.server 8000
```

浏览器访问：

```text
http://localhost:8000/
```

不要直接双击 HTML 文件打开，浏览器对本地文件的跨域限制可能导致数据加载失败。当前 `js/data-config.js` 决定网页从哪个 GitHub 仓库的 `data` 分支读取数据。

### 3.5 本地密码保护的注意事项

`setup-local-auth.sh` 会读取项目根目录的 `.env`，并修改 `js/auth-config.js`。当前仓库的 `.gitignore` 没有忽略根目录 `.env`，因此使用前应先设置本仓库的本地排除规则：

```bash
printf ".env\njs/auth-config.js.backup\n" >> .git/info/exclude
```

再创建 `.env`：

```dotenv
ACCESS_PASSWORD=replace-with-your-password
```

执行：

```bash
./setup-local-auth.sh
```

测试结束后，确认没有误提交密码或本地生成的认证配置：

```bash
git status --short
git restore js/auth-config.js
```

## 4. 当前仓库的 Git 远端关系

当前本地仓库的 `origin` 是你的 fork：

```text
origin -> https://gh-proxy.com/https://github.com/KevinClaint/daily-arXiv-ai-enhanced.git
```

原项目应配置为 `upstream`：

```text
upstream -> https://github.com/dw-dengwei/daily-arXiv-ai-enhanced.git
```

只需执行一次：

```bash
cd /Users/kevin/Desktop/code/research/tools/arxiv/daily-arXiv-ai-enhanced
git remote add upstream https://github.com/dw-dengwei/daily-arXiv-ai-enhanced.git
git remote -v
```

如果直连 GitHub 不可用，可以让 `upstream` 也使用与 `origin` 相同的代理形式：

```bash
git remote set-url upstream https://gh-proxy.com/https://github.com/dw-dengwei/daily-arXiv-ai-enhanced.git
```

约定如下：

- `origin/main`：你自己的线上主分支；
- `upstream/main`：原项目的主分支；
- `origin/data`：Actions 自动生成的数据分支；
- 本地功能分支：你正在开发、尚未合并的修改。

## 5. 日常同步上游更新

推荐使用“合并上游”的方式，这样会保留 fork 中已有的定制提交。

### 5.1 更新前检查

```bash
cd /Users/kevin/Desktop/code/research/tools/arxiv/daily-arXiv-ai-enhanced
git status --short --branch
```

如果有未提交修改，优先提交到功能分支。临时修改也可以暂存：

```bash
git stash push -u -m "wip before upstream sync"
```

### 5.2 拉取并合并上游

```bash
git fetch --all --prune
git switch main
git pull --ff-only origin main
git merge upstream/main
git push origin main
```

如果之前使用了 stash，在同步成功后恢复：

```bash
git stash pop
```

不要使用 `git reset --hard upstream/main` 来做常规更新。它会丢弃 fork 在 `main` 上独有的提交，也可能覆盖你尚未保存的工作。

### 5.3 处理合并冲突

合并出现冲突时：

```bash
git status
```

打开冲突文件，处理 `<<<<<<<`、`=======`、`>>>>>>>` 标记，确认最终内容后执行：

```bash
git add path/to/resolved-file
git commit
git push origin main
```

如果不确定如何解决，可以先取消本次合并，工作区会回到合并前：

```bash
git merge --abort
```

重点检查容易产生定制冲突的文件：

- `.github/workflows/run.yml`；
- `js/data-config.js`；
- `js/auth-config.js`；
- `README.md`；
- AI 模型和提示词相关文件。

## 6. 开发和提交自己的修改

不要长期直接在 `main` 上开发。先同步主分支，再建立功能分支：

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/short-description
```

修改后先检查差异：

```bash
git status --short
git diff
git diff --check
```

### 6.1 选择要提交的文件

如果只想提交本次功能涉及的文件，逐个指定路径：

```bash
git add path/to/file1 path/to/file2
git diff --staged
```

例如，提交历史论文检索功能：

```bash
git add README.md search_arxiv.py tests/test_search_arxiv.py
git diff --staged
```

如果确认当前仓库里的所有新增、修改和删除都应该提交，可以使用：

```bash
git add -A
git status
git diff --staged
```

`git add -A` 会把 `.vscode` 配置、未跟踪文档、文件删除等内容一并暂存。执行后务必检查 `git status` 和 `git diff --staged`，确认其中没有 `.env`、API Key、Token、临时输出或当天生成的数据。

暂存错了某个文件时，可以只取消暂存，不删除本地修改：

```bash
git restore --staged path/to/file
```

### 6.2 创建提交并推送

确认暂存内容无误后创建提交：

```bash
git commit -m "feat: describe the change"
```

如果当前使用功能分支，第一次推送时设置上游分支：

```bash
git push -u origin feat/short-description
```

然后在 GitHub 上创建 Pull Request，检查通过后合并到自己的 `main`。

如果这个提交就是在自己的 `main` 分支上创建的，先确认当前分支显示为 `main`，再拉取远端变化并推送：

```bash
git branch --show-current
git pull --rebase --autostash origin main
git push origin main
```

不要在功能分支提交后直接切换到 `main` 并推送，否则该功能提交仍然只存在于功能分支。以后当前分支已经设置上游时，也可以把推送命令简写为 `git push`。不确定远端地址时，执行：

```bash
git remote -v
```

常用提交前缀可以保持简单一致：

| 前缀 | 用途 |
| --- | --- |
| `feat:` | 新功能 |
| `fix:` | 修复问题 |
| `docs:` | 文档修改 |
| `refactor:` | 不改变行为的代码整理 |
| `chore:` | 依赖、工作流或维护任务 |

如果 Actions 刚好自动更新了远端 `main`，本地推送可能被拒绝。不要强制推送，先执行：

```bash
git pull --rebase origin main
git push origin main
```

功能分支则把最后两条命令中的 `main` 替换为对应分支名。

## 7. `data` 分支的维护原则

`data` 分支由 GitHub Actions 自动创建和更新，用于保存 JSONL、Markdown 和 `assets/file-list.txt`。建议遵循：

1. 不把 `data` 合并进 `main`；
2. 不在 `data` 分支开发功能；
3. 不手工改历史数据，除非已经确认 Actions 的生成逻辑；
4. 清理数据前先保留备份，并确认网页不会继续引用它；
5. Actions 失败时先查日志，不要立刻强制覆盖分支。

只读查看远端数据分支：

```bash
git fetch origin data
git log --oneline -10 origin/data
git show origin/data:assets/file-list.txt
```

需要完整查看时，可以用独立 worktree，避免切换当前开发目录：

```bash
git worktree add ../daily-arxiv-data origin/data
```

查看结束后，在项目根目录执行：

```bash
git worktree remove ../daily-arxiv-data
```

## 8. 依赖和代码质量维护

当前仓库没有现成的自动化测试或 lint 配置。修改 Python 或 Shell 代码后，至少执行以下基础检查：

```bash
uv sync --frozen
uv run python -m compileall ai daily_arxiv to_md
bash -n run.sh setup-local-auth.sh
git diff --check
```

涉及抓取或 AI 调用的改动，还应在功能分支手动运行一次对应流程。完整流程会访问外部服务并可能产生费用。

依赖升级应单独建立维护分支：

```bash
git switch main
git pull --ff-only origin main
git switch -c chore/update-dependencies
uv lock --upgrade
uv sync
git diff pyproject.toml uv.lock
```

验证无误后再提交 `pyproject.toml` 和 `uv.lock`。不要只改其中一个文件。

## 9. 常见问题

### Actions 无权 push

检查仓库的 `Workflow permissions` 是否为读写权限，以及 `main`/`data` 分支保护规则是否允许 Actions 写入。

### 工作流抓取不到论文

确认 `CATEGORIES` 使用合法的 arXiv 分类和英文逗号，例如 `cs.AI, cs.CL`；再查看 Actions 中 `Crawl arXiv papers` 的日志。

### AI 摘要失败

依次检查 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`MODEL_NAME` 是否属于同一个服务商，并确认账户额度和模型权限。

### 页面能打开但没有数据

检查 `data` 分支是否存在、`assets/file-list.txt` 是否生成，以及 `js/data-config.js` 中的仓库所有者和仓库名是否指向当前 fork。

### `git push` 被拒绝

通常是 Actions 或其他设备先更新了远端。先获取并整合远端提交，不要直接 `--force`：

```bash
git pull --rebase origin main
git push origin main
```

### 上游更新导致定制配置被覆盖

使用 `git merge upstream/main` 并在冲突时保留需要的 fork 配置。同步完成后重点复查 Actions Secrets/Variables、工作流、数据仓库地址和 Pages 配置。

## 10. 建议维护节奏

- 每周：查看 Actions 是否正常运行，检查 API 余额和失败日志；
- 每两周或每月：同步一次 `upstream/main`；
- 每月：检查依赖更新、安全公告和 GitHub Token 有效期；
- 修改后：通过功能分支和 Pull Request 合并，不强制推送主分支；
- 定期：确认 Secrets 未进入 Git 历史，删除已经不用的 Token 并轮换长期密钥。

最常用的安全同步命令可以简化为：

```bash
git status --short --branch
git fetch --all --prune
git switch main
git pull --ff-only origin main
git merge upstream/main
git push origin main
```
