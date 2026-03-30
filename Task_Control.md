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
- Phase 7 Execute（最小竖切）：`video_pipeline vertical-slice` — 歌词对齐 + ffmpeg 1080×1920 字幕烧录；`services/video_export_service.py`；`tests/vertical_slice_test.py`（依赖本机 ffmpeg）
- Phase 7b：`POST /api/v1/jobs` 支持可选 `video_relative_path`，成功后 `artifacts.douyin_vertical`；`common/paths.py` 防止路径穿越；冒烟/失败单测覆盖
- Phase 8：`GET /api/v1/config`、`GET /api/v1/library/videos`（`library_scan`）、`GET /api/v1/jobs` 列表；`words_relative_path` 与视频一致做安全解析；`JobStore.list_recent`
- Phase 9：**异步 Job** — `POST /api/v1/jobs` 返回 **202**，`services/job_execution.py` 后台线程执行对齐/导出；失败码写入 job 记录，`GET /jobs/{id}` **200** 读终端状态
- Phase 10：异步 Job 的工程化补齐（轮询示例、`GET /api/v1/jobs/{id}/logs`、`POST /api/v1/jobs/{id}/cancel`、并发上限 429）
- Phase 11：剪辑成片（trim master + shift SRT）接入同一条竖切 end-to-end（worker 与 CLI 同链路）
- Phase 12：UI 上传准备/发布确认（stub）+ `GET /ui` 静态页展示最近 job
- Phase 13：Douyin 上传服务层（manual + Playwright auto-first fallback）接入 prepare API

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
- [x] Phase 7 Execute：最小可演示竖切（本地视频 + 官方词 + 词级 JSON → 9:16 烧录成片）
- [x] Phase 7b：`/jobs` 接入竖切导出与路径校验、回归测试
- [x] Phase 8：工作区与素材发现 API（config / library scan / jobs 列表）+ `words` 路径安全
- [x] Phase 9：`POST /jobs` 异步入队（202 + 轮询），流水线错误体现在 job JSON
- [x] Phase 10：logs/cancel/队列上限/轮询示例（docs + 回归测试）
- [x] Phase 11：剪辑成片（trim master + shift SRT）接入竖切 end-to-end，字幕时间轴保持一致并完成回归
- [x] Phase 12：UI 上传准备/发布确认（stub）+ `web/ui/index.html` 页面与对应 API
- [x] Phase 13：上传服务层接入（`DOUYIN_UPLOAD_MODE=auto` + manual fallback）

