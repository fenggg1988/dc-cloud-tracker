# 美国数据中心建设 & 云企融资监控看板

每日监控美国数据中心建设进度、云企（超大规模厂商）融资情况、GPU 用卡与资本支出。

**看板入口（GitHub Pages）**：https://fenggg1988.github.io/dc-cloud-tracker/

## 监控内容

| 板块 | 数据来源 | 更新方式 |
|---|---|---|
| 资本支出 CapEx（四大+Oracle+CoreWeave） | 财报/指引（调研整理） | 财报季或重大调整时 AI 调研更新 |
| 发债（金额/利率/期限） | 公开报道（调研整理） | 重大事件时更新 |
| 发股/股权融资、资金缺口、信用风险 | 公开报道（调研整理） | 重大事件时更新 |
| GPU 用卡台账（已部署/计划购买） | 公开披露（调研整理） | 重大事件时更新 |
| 数据中心建设进度（GW/状态） | Stargate/Meta/微软等公开信息 | 重大事件时更新 |
| 股价走势（6 家，近 6 个月） | Yahoo Finance API | **每日自动抓取** |
| 债券利率/信用利差走势（10Y 美债、Baa、HY/IG OAS） | FRED | **每日自动抓取** |
| 个券收益率与 CDS 关键点位 | 公开报道（调研整理） | 重大事件时更新 |
| 行业新闻头条 | Google News RSS（9 组关键词） | **每日自动抓取** |

## 架构

- `scrape_dc_cloud.py`：每日抓取新闻 → `data/news.json`
- `data/curated.json`：调研型结构化数据（AI 调研后更新）
- `index.html`：中文单页看板（读取上述 JSON）
- GitHub Actions `daily.yml`：每日 09:30（北京时间）抓取新闻并提交；Pages（legacy 模式，main 分支根目录）自动生效
- 链式调度：由 `purr-mnav-tracker` 工作流旁支触发（同 china-semi-tracker 模式）

## 更新调研数据

在 WorkBuddy 对话中说「**更新数据中心看板**」即可：AI 会调研最新发债/GPU/融资/建设新闻并更新 `data/curated.json` 后推送。
