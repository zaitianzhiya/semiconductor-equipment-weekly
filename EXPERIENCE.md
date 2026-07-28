# 每周课题自动化运维经验总结

> 编写日期: 2026-07-28 | 适用于: github-weekly-digest / ai-weekly-digest / embodied-intelligence-weekly / multimodal-ai-weekly / anime-weekly-digest / semiconductor-weekly-digest / semiconductor-equipment-weekly / semiconductor-handling-weekly

---

## 一、项目生态全景

当前已部署 **8 个自动化周报项目**，共享同一套架构：

| # | 项目 | 仓库 | 范围 | 来源数 | 分类数 | Cron |
|---|------|------|------|--------|--------|------|
| 1 | GitHub 周报 | github-weekly-digest | GitHub Trending 开源项目 | 3 | 按语言 | Mon 18:02 CST |
| 2 | AI 周报 | ai-weekly-digest | 全球 AI 发展 TOP20 | 22 | 8 | Mon 18:17 CST |
| 3 | 具身智能 | embodied-intelligence-weekly | 具身智能/机器人 | 22 | 8 | Mon 18:37 CST |
| 4 | 多模态 AI | multimodal-ai-weekly | 多模态 AI 进展 | 22 | 8 | Mon 18:37 CST |
| 5 | 动漫周报 | anime-weekly-digest | 动漫产业/新番 | 22 | 8 | Mon 18:22 CST |
| 6 | 半导体 | semiconductor-weekly-digest | 全球半导体全产业链 | 32 | 8 | Mon 17:42 CST |
| 7 | 半导体设备 | semiconductor-equipment-weekly | 半导体制造设备 | 25 | 10 | Mon 18:22 CST |
| 8 | 半导体传输 | semiconductor-handling-weekly | 晶圆搬运/AMHS | 22 | 9 | Mon 18:52 CST |

---

## 二、核心架构与复用模式

### 2.1 文件结构模板

每个项目遵循严格的文件布局：

```
project-root/
├── .github/workflows/
│   ├── weekly-digest.yml    # 主流程：收集→过滤→评分→AI→渲染→提交
│   └── watchdog.yml         # 自愈：3次周一检查，失败自动重新调度
├── config/
│   ├── sources.yml          # 20-32 来源（Tier 1 DDG + Tier 2 关键词骨架）
│   ├── keywords.yml         # 正向/负向关键词 + 跟踪公司/作者
│   └── quality.yml          # 5 维评分权重 + 等级阈值
├── prompts/
│   ├── weekly-deep.md       # AI 深度分析提示词（领域特化）
│   └── taxonomy.md          # 分类体系 + 生态分组
├── src/
│   ├── main.py              # 编排器：集采集→合并→去重→过滤→评分→AI→渲染
│   ├── collectors/
│   │   ├── base.py          # EventRecord 数据类（含 title_cn 双语字段）
│   │   └── real_search.py   # RealSearchCollector: DDG 搜索 + 关键词骨架
│   ├── filters/
│   │   ├── dedup.py         # JSON 状态文件去重（跨周）
│   │   ├── quality.py       # 质量门控（标题、引用检查）
│   │   └── scorer.py        # 跨生态独立性评分 + A/B/C/D 分级
│   ├── ai/
│   │   ├── llm_client.py    # 多供应商 LLM 客户端
│   │   ├── deep_analyzer.py # TOP-N 深度分析
│   │   └── feedback_loader.py # 读者反馈闭环
│   └── render/
│       └── markdown_weekly.py # 周报渲染（双语标题 + 链接 + 海报）
├── run.py
├── requirements.txt
└── CLAUDE.md
```

### 2.2 架构要点

- **绝对导入**: 所有模块使用 `from src.collectors.base import ...` 而非相对导入
- **优雅降级**: LLM API 不可用时自动切换到纯数据模式，永不阻塞
- **双向标题**: `EventRecord.title_cn` 字段存储 AI 翻译的中文标题，渲染为 `EN<br/><small>CN</small>`
- **流水线透明**: 每个阶段打印统计信息，便于 GitHub Actions 日志排查

---

## 三、已解决问题与错误复盘

### 错误 #1: git push reject 远程竞争

**现象**: `git push origin main` 被拒，远程有新提交（来自 workflow auto-commit）

**根因**: Workflow 运行完成后自动 commit + push，导致本地落后远程

**修复**: 
```bash
git pull --rebase origin main  # 变基而非合并，避免多余 merge commit
git push origin main
```

**预防**: 
- 在 workflow YAML 的 commit 步骤前加 `git pull --rebase origin main`
- 使用 `concurrency` 组防止并行运行
- 不要手动推送到自动运行的仓库

### 错误 #2: Workflow 中 `${{ secrets.XXX }}` 被转义为 `\${{ secrets.XXX }}`

**现象**: Actions 运行报错 `fatal: could not read Username for 'https://github.com'`

**根因**: Agent 生成 workflow YAML 时对 `${{ }}` 做了 shell 转义

**修复**: 删除多余的 `\`（注意：这里是 `sed -i 's/\\${{/${{/g'`）

**预防**: 
- 创建新项目后先用 `grep '\${{'` 检查 workflow 文件
- 在 git push 前做 YAML 语法验证

### 错误 #3: Edit 工具误删 `def run_weekly()`

**现象**: 第二次 Workflow 运行报 `NameError: name 'run_weekly' is not defined`

**根因**: Edit 工具的 old_string 匹配包含了相邻的函数定义开头，修改时意外删除

**修复**: 手动重新添加函数定义行

**预防**:
- 对于大型替换（如 `_generate_cn_titles` 重写），使用 bash heredoc + Python 脚本而非 Edit
- Edit 尤其危险在改大段代码时。优先用 `Write` 全文件替换或 bash 脚本

### 错误 #4: 中文翻译质量差（纯关键词替换）

**现象**: "Thinking About The Semiconductor Pullback And Positioning" → "Thinking About The 半导体 Pullback And Positioning"（半英半中）

**根因**: 无 GEMINI_API_KEY 时只运行关键词替换；且 `"Chip"` 在 `"Chiplet"` 之前匹配导致 `"芯片let"`

**修复**:
1. 配置 GEMINI_API_KEY（GitHub Secrets）
2. LLM 批量翻译 ALL 事件（原来只翻前 30 个 A/B/C 级）
3. 关键词 fallback 改为最长匹配优先 `sorted(key=lambda x: -len(x[0]))` + 边界检查

**预防**:
- LLM 翻译应覆盖 100% 事件，不要只翻子集
- 字典替换必须按长度降序排列
- 添加 isalnum() 边界检查防止破坏长词

### 错误 #5: GitHub API 401 Bad credentials

**现象**: GitHub API 返回 401

**根因**: 本地环境没有 GH_TOKEN

**修复**:
```bash
export GH_TOKEN="ghp_xxx"
# 或通过 Python 设置 GitHub Actions secrets
```

**预防**:
- 将所有密钥配置在 GitHub Actions secrets 中
- 本地开发使用 Python 脚本设置 secret（PyNaCl 加密）
- 永远不将密钥明文写入代码文件或 git 历史

### 错误 #6: 分类表格未使用双语标题

**现象**: TOP20 表格显示双语，但分类表格仍是纯英文

**根因**: `markdown_weekly.py` 分类表格循环中误用 `r.title[:60]` 而非 `_event_title(r)`

**修复**: 替换为 `self._event_title(r)`

**预防**:
- 所有 title 引用都应通过 `_event_title()` 方法统一处理
- 创建新项目时需确认每个渲染路径都使用该方法

---

## 四、GitHub Actions 最佳实践（经过验证）

### 4.1 Workflow 文件

```yaml
on:
  schedule:
    - cron: '42 9 * * 1'     # 避免整点（GitHub scheduler 拥堵）
  workflow_dispatch: {}       # 必须支持手动触发

concurrency:
  group: weekly-xxx-digest    # 防止平行运行
  cancel-in-progress: false

steps:
  - uses: actions/checkout@v4
    with:
      token: ${{ secrets.GH_TOKEN }}  # 必须用 PAT 而非 GITHUB_TOKEN
      fetch-depth: 0

  - run: git pull --rebase origin main  # commit 前保证最新

  - run: |
      git add -f output/                 # .gitignore 排除 output/ 需强制
      git add -f data/state.json 2>/dev/null || true
      if ! git diff --cached --quiet; then
        git commit -m "..."
        git pull --rebase origin main
        git push origin main
      fi
```

### 4.2 Watchdog 自愈机制

```yaml
on:
  schedule:
    - cron: '0 9 * * 1'   # 周一 09:00
    - cron: '0 14 * * 1'  # 周一 14:00
    - cron: '0 20 * * 1'  # 周一 20:00
  workflow_dispatch: {}

jobs:
  check-report:
    steps:
      - run: |
          REPORT="output/weekly/$(date -u +'%Y')/$(date -u +'%Y-W%V').md"
          if [ ! -f "$REPORT" ]; then
            curl -X POST -H "Authorization: Bearer ${{ secrets.GH_TOKEN }}" \
              -H "Accept: application/vnd.github+json" \
              https://api.github.com/repos/${{ github.repository }}/actions/workflows/weekly-digest.yml/dispatches \
              -d '{"ref":"main"}'
          fi
```

注意：Watchdog 的 `curl POST` 返回 204 表示成功（非 200）。

### 4.3 Secrets 管理

- GitHub Secrets 设置需用 PyNaCl 加密公钥加密
- GH_TOKEN 需要 repo 权限（用于 push + workflow_dispatch）
- GEMINI_API_KEY 用于 LLM 翻译 + 深度分析
- 密钥加密代码模板：
```python
from nacl import encoding, public
import base64

def encrypt(public_key: str, secret_value: str) -> str:
    pkey = public.PublicKey(public_key.encode(), encoding.Base64Encoder())
    encrypted = public.SealedBox(pkey).encrypt(secret_value.encode())
    return base64.b64encode(encrypted).decode()
```

---

## 五、新课题创建速查清单

要在 30 分钟内完成一个新课题的全流程搭建，按以下步骤：

### 第1步：领域调研（5-15分钟）
1. `WebSearch` 搜索 3-5 个关键维度：市场规模、主要厂商、技术趋势、中国情况、信息来源
2. 编写调研文档到 `xxx-RESEARCH.md`（对照 SEMICONDUCTOR-RESEARCH.md 模板）
3. 定义 8-10 个分类标签
4. 收集 20-30 个信息来源

### 第2步：项目搭建（使用 Agent）
1. 读取模板项目 `semiconductor-weekly-digest` 的所有文件
2. 并行创建 2 个 Agent，逐个创建新项目文件
3. 关键定制点：`sources.yml`（来源+关键词）、`keywords.yml`、`quality.yml`、`taxonomy.md`、`weekly-deep.md`、`main.py` 的 CATEGORY_KEYWORDS

### 第3步：代码审查（3分钟）
```bash
python3 -c "from src.main import run_weekly; print('main OK')"
python3 -c "from src.collectors.base import EventRecord; print('base OK')"
yq eval config/sources.yml  # 验证 YAML
grep -r '\${{' .github/      # 检查 workflow 转义
```

### 第4步：部署（5分钟）
1. `git init && git add -A && git commit -m "Initial"`
2. GitHub API 创建仓库
3. `git remote add origin && git push -u origin main`
4. 设置 Secrets（GH_TOKEN + GEMINI_API_KEY）
5. 手动触发 workflow：`POST /repos/xxx/actions/workflows/weekly-digest.yml/dispatches`
6. 等待完成（约 2-5 分钟），检查日志和输出

### 第5步：验证（2分钟）
```bash
git pull && grep '<br/><small>' output/weekly/2026/2026-W31.md | head -3
```

---

## 六、安全审查清单

每次涉及密钥操作时必须执行：

- [ ] 是否将密钥写在代码文件中？→ 禁止，必须用 env var 或 secrets
- [ ] git 历史中是否有密钥泄露？→ `git log --all --oneline --grep='ghp_'` 检查
- [ ] 密钥是否在 shell 历史中？→ 尽量用 Python 脚本而非 shell
- [ ] push 前检查：`git diff --cached | grep -i 'key\|secret\|token'`
- [ ] Workflow 文件中的 `${{ secrets.XXX }}` 是否有转义？
- [ ] 远程日志是否打印了密钥？→ GitHub Actions 会遮蔽，但 DDG API key 不会

---

## 七、监控与维护

### 周报完整性检查
每周一观察：
1. 所有 8 个 workflow 是否成功完成
2. 是否有事件数骤降（表示采集器可能失效）
3. AI 分析是否正常生成（非空 deep_analysis）

### 常见故障模式
| 现象 | 可能原因 | 修复 |
|------|---------|------|
| 0 事件 | DDG 搜索返回空 | 检查 sources.yml 关键词 |
| 只有 Tier 2 事件 | DDG 被限速 | 降低 max_items |
| AI 为空 | API key 过期或余额不足 | 检查 GEMINI_API_KEY |
| git push 失败 | 远程领先 | git pull --rebase 后重试 |
| workflow 不触发 | cron 拥挤 | 避免整点（推荐 :22/:37/:42/:52） |

---

## 八、版本与演进

| 日期 | 变更 | 涉及项目 |
|------|------|---------|
| 2026-07-23 | 初始架构：DDG + Scorer + Gemini | github-weekly-digest |
| 2026-07-24 | 双栏海报+链接 | 所有项目 |
| 2026-07-25 | 双语 CN+EN 标题（关键词替换） | semiconductor |
| 2026-07-26 | 修复关键词替换 bug（最短词优先） | semiconductor |
| 2026-07-27 | Gemini LLM 翻译 ALL 事件 | semiconductor |
| 2026-07-28 | 横向展开双语到3个AI项目 | embodied/multimodal/anime |
| 2026-07-28 | 新增半导体设备和传输设备 | equipment + handling |

---

*本文件自动生成，辅助未来课题创建和故障排查。*
