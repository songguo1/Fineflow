# PineFlow

[English](README.md)

<p align="center">
  <img src="apps/desktop/src/assets/pineflow-wordmark.png" alt="PineFlow" width="360">
</p>

PineFlow 是一个面向 QGIS 工作流的 tool-calling GIS agent。它通过类似 ReAct 的“观察状态、调用工具、读取 observation、继续下一步”的执行循环，将自然语言 GIS 请求转化为经过规则校验的 QGIS Processing / PyQGIS 操作。

PineFlow 目前是本科毕业设计原型项目，适合结构化 GIS 处理流程，不用于替代完整的 QGIS 桌面体验，例如地图符号化、交互式编辑、制图版面设计或人工视觉检查。

## 相关链接

- 演示视频：[Bilibili](https://www.bilibili.com/video/BV1N6Jg6xEYT)
- 公众号文章：[微信公众号](https://mp.weixin.qq.com/s/NMACoA4dCgp8wsIiV35ovQ)

## 项目特性

- 自然语言驱动 GIS 工作流
- 基于类似 ReAct 的 observe-act loop 执行流程
- 使用 LLM 原生 tool calling
- 通过独立 PyQGIS runtime worker 调用 QGIS Processing 工具
- 使用 ToolKit 机制按需暴露工具能力，减少模型上下文噪音
- 使用 Skills 机制注入 GIS 领域经验
- 通过规则网关进行语义校验和执行前检查
- 支持会话状态、运行事件、输出产物和工作区状态管理
- 提供 FastAPI 后端服务
- 提供 Tauri v2 + React 桌面端界面

## 项目结构

```text
src/
  pineflow_agent/
    core/             智能体状态、工作区模型、消息、产物记录
    llm/              LLM 客户端、模型适配器、prompt 和上下文构建
    orchestration/    ReAct 执行循环、运行执行、恢复流程、结果投影
    policies/         输出、坐标系、自主性等策略
    risks/            风险诊断、风险分类和转换逻辑
    rules/            语义校验、执行前检查、恢复规则
    tools/            工具定义、工具注册、ToolKits、QGIS 工具封装

  pineflow_api/
    application/      运行任务、会话、状态查询、QGIS runtime 等应用服务
    contracts/        API 契约、运行生命周期、事件、快照模型
    entrypoints/      FastAPI 应用入口和 PyQGIS worker 入口
    persistence/      SQLite 会话状态、事件流、运行快照持久化
    routing/          Slash command、意图路由、会话路由

  pineflow_runtime/
    runtime.py        具体 PyQGIS 执行逻辑
    errors.py         运行时错误定义

apps/
  desktop/
    src/              React 前端源码
    src-tauri/        Tauri v2 原生桌面端工程
    package.json      桌面端依赖和脚本
    vite.config.js    Vite 配置

resources/
  skills/             智能体加载的 GIS 领域知识指导文件
  toolkits/           ToolKit 能力定义文件

.pineflow/            本地运行状态和默认会话输出，不进入 Git
```

## 系统架构

```text
Desktop UI
  |
FastAPI Backend
  |
ReAct GIS Agent
  |
QGIS / PyQGIS Runtime
```

桌面端不直接执行 GIS 操作。它通过后端 API 创建运行任务、轮询运行事件，并渲染会话状态、工作流步骤、输出结果和分析报告。

后端负责管理 session、run、事件流、状态快照、slash command、意图路由和执行编排。

Agent 负责把用户请求转化为一系列经过校验的 GIS 工具调用：

```text
读取当前工作区状态
  |
构建 ReAct prompt
  |
调用 LLM 选择一个原生工具
  |
通过规则网关校验工具参数
  |
执行工具
  |
记录 observation
  |
继续下一轮、请求用户确认，或输出最终答案
```

Runtime 层负责真正执行 QGIS 操作，例如 buffer、clip、fix geometries、raster calculator、重投影、结果导出等。

## ToolKits

PineFlow 会按 ToolKit 组织工具能力。在一次运行中，只有当前相关的 ToolKit 会暴露给模型。

| ToolKit | 主要能力 |
| --- | --- |
| `data_io` | 加载 vector/raster/CSV、CSV 转点、图层摘要、结果导出 |
| `vector_transform` | 重投影、几何修复、质心、面内点、多部件转单部件、几何简化 |
| `vector_analysis` | 缓冲区、融合、图层合并、属性筛选、空间连接、最近邻连接、面内点计数、字段计算 |
| `vector_overlay` | 裁剪、相交、差集、联合、对称差分、按空间关系提取 |
| `raster` | 栅格重投影、掩膜裁剪、范围裁剪、栅格计算、分区统计、栅格采样、矢量栅格化、栅格转面 |
| `qgis_generic` | 发现 QGIS 算法、查询算法帮助、必要时使用受控通用算法入口 |

## Skills

Skills 位于 `resources/skills/`，是模型在决策时可以按需加载的 GIS 领域经验提示。它们不是执行器，不会直接调用 QGIS，也不会替代规则校验。典型内容包括米制缓冲的 CRS 风险、CSV 经纬度字段识别、边界筛选条件、空间连接的图层类型和空间关系检查等。

## 环境要求

- Python 3.10+
- Node.js 18+
- Rust toolchain
- QGIS LTR
- OpenAI-compatible LLM provider，例如 DeepSeek、OpenAI-compatible APIs、Qwen 或 GLM

真实 GIS 处理需要本地安装 QGIS。普通代码检查和部分 UI 开发不一定需要启动 QGIS。

## 配置方式

PineFlow 从进程环境变量和桌面端设置面板读取配置。本项目不要求本地环境配置文件。

启动后端前，至少需要配置一个 LLM provider：

```powershell
$env:PINEFLOW_LLM_PROVIDER="deepseek"
$env:PINEFLOW_LLM_BASE_URL="https://api.deepseek.com"
$env:PINEFLOW_LLM_MODEL="deepseek-v4-pro"
$env:DEEPSEEK_API_KEY="your_api_key"
```

如果要执行真实 QGIS 处理，还需要配置本地 QGIS runtime：

```powershell
$env:QGIS_LAUNCHER="D:\software\QGIS\bin\python-qgis-ltr.bat"
$env:QGIS_PREFIX_PATH="D:\software\QGIS\apps\qgis-ltr"
```

这些值也可以在桌面端设置界面中填写。

## QGIS 配置

PineFlow 会把后端/Agent 的普通 Python 环境和 PyQGIS runtime 分开。FastAPI 服务和 Agent 可以运行在普通 Python 环境中；真正的 GIS 处理会在需要时委托给本地 QGIS 安装环境执行。

QGIS 相关配置主要有两个路径：

- `QGIS Launcher`：QGIS Python 启动器，通常是一个 `.bat` 文件或可执行文件。PineFlow 用它启动 QGIS 自带 Python 环境中的 runtime worker，从而让 PyQGIS imports 和 Processing providers 可用于真实 GIS 操作。
- `QGIS Prefix Path`：QGIS application prefix directory。QGIS 通过这个路径定位自身库、插件、资源文件和 Processing algorithms。

Windows 的 QGIS LTR 常见配置示例：

```text
QGIS Launcher:
D:\software\QGIS\bin\python-qgis-ltr.bat
C:\Program Files\QGIS 3.34.*/bin/python-qgis-ltr.bat
C:\Program Files\QGIS 3.40.*/bin/python-qgis.bat

QGIS Prefix Path:
D:\software\QGIS\apps\qgis-ltr
C:\Program Files\QGIS 3.34.*/apps/qgis-ltr
C:\Program Files\QGIS 3.40.*/apps/qgis
```

launcher 和 prefix path 都不是输入数据目录。它们描述的是 PineFlow 如何找到并启动本机 QGIS runtime。

如果没有正确配置 QGIS，API 和桌面端界面可能仍能启动，但真实 GIS 执行会失败，例如 buffer、clip、重投影、栅格处理和结果导出等操作。

## 快速开始

在项目根目录安装 Python 包：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e .
```

在终端 1 启动后端 API：

```powershell
py -m pineflow_api --host 127.0.0.1 --port 8765
```

后端默认监听：

```text
http://127.0.0.1:8765
```

主要 API 路由位于：

```text
/qgis/*
```

在终端 2 启动桌面端：

```powershell
cd apps/desktop
npm install
npm run dev
```

浏览器调试模式：

```powershell
npm run dev:web
```

构建 Web 版本：

```powershell
npm run build:web
```

构建原生桌面端：

```powershell
npm run build
```

## 本地运行状态和输出

PineFlow 会把本地运行状态保存在 `.pineflow/` 下。这个目录不是源码，也不会提交到 Git。

默认会话输出路径是：

```text
.pineflow/sessions/{session_id}/outputs/
```

仓库会忽略本地 GIS 数据、生成结果、缓存、构建产物、助手元数据和测试临时文件。

## 开发状态

PineFlow 仍然是实验性项目。当前重点是围绕 QGIS Processing / PyQGIS 工作流构建稳定的 tool-calling agent harness，包括规则校验、工作区状态、事件轨迹和可复现输出。

## License

MIT License. See [LICENSE](LICENSE).
