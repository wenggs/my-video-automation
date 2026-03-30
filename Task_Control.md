# Task_Control

## Status
- Directory scaffold: completed
- Web 剪辑+自动发布需求文档 v1：completed
- Web 架构设计文档 v1：completed
- 客户决策同步：MVP 本机 Windows、路径可配置、抖音优先 9:16、登录持久化、演唱会内容 — 已写入 PRD/ARCHITECTURE
- 字幕策略：**全程跟唱词**（时间轴对齐、覆盖成片全程）— 已写入 PRD/ARCHITECTURE
- 唱词来源：**官方底稿 + 允许 UI 微调 + 确认稿烧录**（运营提供词 + 强制对齐到成片；LLM 不写词）— 已写入 PRD/ARCHITECTURE
- Phase 1 Spike：官方歌词对齐 PoC 已跑通（输入歌词+词级时间戳JSON，输出SRT）
- Phase 3 Execute（阶段性）：已实现 lyrics ingest / confirmed / force_align 的最小可运行流水线并完成样例验证
- Phase 3 Execute（里程碑2）：已接入服务层、统一错误码、JSONL结构化日志，并完成成功/失败双路径验证
- Phase 4 Execute（里程碑1）：已实现本地 API `PUT/GET/PATCH /api/v1/library/videos/{id}/lyrics*` 并完成真实请求回归
- Phase 4 Execute（里程碑2）：已实现 `POST /api/v1/jobs` + `GET /api/v1/jobs/{id}`，可触发 lyrics_flow_service 并返回作业产物路径
- Phase 5 Execute：已补 `tests/api_smoke_test.py` 自动化回归脚本，并新增 `docs/DEMO.md` 演示说明
- Phase 6 Execute：已补充 `tests/api_failure_test.py`（404/422 失败路径）、HTTP 状态映射说明见 `docs/DEMO.md` §5，仓库根 `README.md` 快速接入

## Todo
- [x] Recreate required folders and files
- [x] 输出 Web 需求文档 v1（含 MVP 边界/验收口径）
- [x] 输出 Web 架构设计 v1（MVP 路线图）
- [x] Phase 1 Spike：官方歌词强制对齐最小 PoC
- [x] Phase 2 Blueprint：补齐 lyrics_ingest / lyrics_confirmed 数据结构与 API 详细字段
- [x] Phase 3 Execute（里程碑1）：实现 lyrics ingest / confirmed + lyrics_force_align 最小集成链路
- [x] Phase 3 Execute（里程碑2）：接入真实作业目录规范、错误码与结构化日志、为后续API封装服务层
- [x] Phase 4 Execute（里程碑1）：实现 API 层（/library/videos/{id}/lyrics*）与服务层对接
- [x] Phase 4 Execute（里程碑2）：将 /jobs 流程接入 API（触发 lyrics_flow_service 并回传作业状态）
- [x] Phase 5 Execute：补最小自动化测试脚本（API 回归）并准备首个可演示版本说明
- [x] Phase 6 Execute：补充 /jobs 失败场景回归与返回码映射（400/404/422），并整理 README 接入指南

