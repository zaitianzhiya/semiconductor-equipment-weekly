# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project overview

**Semiconductor Equipment Weekly Digest** (半导体设备每周周报) is an automated pipeline that collects global semiconductor equipment industry news weekly, enriches them with web search data, generates AI-powered Chinese summaries (via Gemini), and publishes structured Markdown reports to a GitHub Pages site.

Key numbers: 25 information sources (18 Tier 1 DDG + 7 Tier 2 keyword), 10-dimension categorization, 5-dimension scoring, ~8,000-character weekly reports with AI summary + deep analysis.

## Architecture

```
Multi-source Collectors (DDG news) -> Dedup/Merge -> Quality Filter -> 5-dim Scorer -> Gemini AI (summary + deep analysis) -> Markdown Renderer -> GitHub Actions commit/push
```

**Entry point for GitHub Actions:** `run.py --mode weekly`
**Local testing:** `python run.py --mode weekly`

## Key modules

| Module | Path | Purpose |
|--------|------|---------|
| Collectors | `src/collectors/` | Scrape DDG news for semiconductor equipment topics, fallback to keyword skeleton |
| Filters | `src/filters/` | Dedup (JSON state file), quality gates, 5-dim scoring with confidence grades |
| AI | `src/ai/` | LLM client (multi-provider), weekly deep analyzer, feedback loader |
| Render | `src/render/` | Markdown weekly reports with bilingual CN+EN event titles |
| Config | `config/` | YAML: sources (Tier 1/2), keywords (positive/negative), quality thresholds + scoring weights |
| Prompts | `prompts/` | Editable Markdown files that define AI behavior (weekly-deep, taxonomy) |

## Data flow

1. **Collect**: `RealSearchCollector` searches DDG news for each Tier 1 source (equipment-specific queries). Tier 2 sources use keyword skeleton fallback.
2. **Filter**: `QualityFilter` checks title + citations present. Graceful -- missing data passes through as "D" grade.
3. **Score**: `Scorer` computes confidence from cross-ecosystem citation weighting (6 ecosystems: us_equip, jp_equip, eu_equip, cn_equip, kr_equip, global_equip).
4. **AI**: `DeepAnalyzer` sends top 15 events to Gemini 2.5 Flash with structured Chinese prompt (no bare jargon, 3-second hooks, five-layer analysis angles). Fallback to data-only table if LLM unavailable.
5. **Render**: `MarkdownRenderer` generates weekly report + category sections. Bilingual titles via `_generate_cn_titles()` (keyword + LLM batch translation).

## Configuration patterns

- **Sources** (`config/sources.yml`): 25 sources total. Tier 1 (18 sources: top equipment news outlets, company IR, Chinese media) vs Tier 2 (7 sources: research firms, industry reports). Keywords tailored for DDG news search.
- **Keywords** (`config/keywords.yml`): Positive keywords boost category matching (EUV, High-NA, etch, deposition, ALD, CMP, GAA, etc.). `tracked_companies` for key equipment makers.
- **Quality** (`config/quality.yml`): 5-dimension scoring: tech_significance 30%, market_impact 25%, supply_chain 20%, geopolitical 15%, industry_novelty 10%. Ecosystem weights for 6 regions.

## Category system (EVENTS_CATEGORY in src/main.py)

10 equipment-specific categories:
- `#lithography` — 光刻/曝光设备
- `#etch` — 刻蚀设备
- `#deposition` — 薄膜沉积设备
- `#cmp` — 平坦化/抛光设备
- `#metrology` — 量检测设备
- `#cleaning` — 清洗设备
- `#thermal_implant` — 热处理/离子注入
- `#packaging_test` — 封装测试设备
- `#china_equip` — 中国半导体设备
- `#equip_supplychain` — 设备供应链/零部件

## Important implementation details

- **Imports**: All modules use absolute imports (`from src.collectors.base import ...`) for compatibility with `run.py` at repo root.
- **GitHub Actions secrets**: Uses `GH_TOKEN` (not `GITHUB_TOKEN`) for push access. `GEMINI_API_KEY` for AI summaries.
- **Concurrency control**: Workflow uses `concurrency: group: equipment-weekly-digest` with `cancel-in-progress: false`.
- **Cron times**: UTC 22:10 Monday = Beijing 06:10 Tuesday. Off-peak to avoid GitHub scheduler congestion.
- **git add -f**: The `.gitignore` excludes `output/*`, so workflow commit step must use `git add -f output/`.
- **Graceful degradation**: If Gemini API is unavailable, the pipeline falls back to data-only reports without AI summaries.
- **Feedback loop**: Reports include a feedback section. Weekly `feedback/*.md` files can contain tier corrections and permanent rules injected into AI prompts via `FeedbackLoader`.

## Local development

```bash
# Install
pip install -r requirements.txt

# Run full pipeline (requires GEMINI_API_KEY)
export GEMINI_API_KEY="..." GH_TOKEN="..."
python run.py --mode weekly
```

## Deployment

Deployed at https://github.com/zaitianzhiya/semiconductor-equipment-weekly. Two workflows active:

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| Equipment Weekly Digest | UTC 22:10 Monday | Full collection + deep analysis |
| Watchdog | 3x Monday | Self-healing: dispatches weekly if missed |

Reports published to `output/weekly/YYYY/YYYY-Www.md`.

## 关键实现要求

- **双语标题**: 所有表格的事件列必须使用中英文双语格式。EN标题为主文本，CN翻译放在 `<br/><small>` 标签中。
- **实现路径**: `markdown_weekly.py` 中的 `_event_title()` 方法 + `main.py` 中的 `_generate_cn_titles()` LLM批量翻译全部事件
- **Fallback**: 所有项目必须有足够大的 `_PREPROCESS` 字典（30+对），保证无LLM时的基本可读性
- **LLM速率保护**: LLM翻译使用 `BATCH_SIZE=15` + `time.sleep(2)` + 3次重试，避免Gemini 429错误
- **审核**: 首次部署后检查 `grep '<br/><small>' output/` 确认双语渲染
