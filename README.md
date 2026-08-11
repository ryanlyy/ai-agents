# SkillAgents — AI Agent 开发学习与实训仓库

面向"从 0 到能独立交付一个生产级 AI Agent"的**教学 + 参考实现**仓库,
包含 **36 课时的完整课程**、**独立参考文档** 与一个**端到端 Demo 项目**。

---

## 仓库结构

```text
SkillAgents/
├── docs/                         ← 独立参考文档(可脱离课程单独阅读)
│   ├── agent-development-guide.md          知识体系总览(9 Step 方法论)
│   ├── mcp-server-basics.md                MCP 协议 & FastMCP 上手
│   └── develop-and-publish-cursor-skill.md Cursor Skill 开发发布指南
│
├── course/                       ← 36 课时培训课程(教师使用)
│   ├── README.md                           课程说明(与本目录 README 联动)
│   ├── outline/
│   │   └── 36-lessons-outline.md           大纲版(学员自学 / 复习)
│   ├── lesson-plans/                       讲师讲稿版(M1 – M7)
│   │   ├── README.md
│   │   ├── M1-基础与认知.md
│   │   ├── M2-第一个Agent.md
│   │   ├── M3-MCP协议与工具层.md
│   │   ├── M4-记忆与上下文.md
│   │   ├── M5-高级架构与规划.md
│   │   ├── M6-工程化与生产.md
│   │   ├── M7-部署与综合实战.md
│   │   └── assets/                         教案配套代码 / 素材
│   └── tests/                              课程用例可执行性测试(T01 – T11)
│       ├── _env.py                         共享环境(读 examples/hello-agent/.env)
│       └── T01_… T11_….py
│
├── examples/                     ← 可运行的参考实现
│   └── hello-agent/                        9 Step + Reflexion + Multi-Agent 完整 Demo
│       ├── README.md                       项目自身说明
│       ├── requirements.txt
│       ├── .env.example
│       ├── agent.py / main.py / tools.py …
│       ├── docs/system-architecture-lld.md 系统 LLD
│       └── evals/                          Eval 用例 + 评测脚本
│
├── _backup/                      ← 本地重组时归档的历史 / 冗余内容(不进版本库)
│   ├── my-agent/                           历史实验目录(仅含空 venv)
│   └── hello-agent-runtime/                历史 traces / 老报告
│
├── .gitignore
└── README.md                     ← 本文件
```

---

## 快速起步

### 我想**读懂 Agent 概念**
1. 先看 [`docs/agent-development-guide.md`](./docs/agent-development-guide.md) —— 9 Step 建立完整心智模型
2. 再看 [`docs/mcp-server-basics.md`](./docs/mcp-server-basics.md) —— 补齐 MCP 工具层

### 我要**跟着上课(自学)**
1. 主线读 [`course/outline/36-lessons-outline.md`](./course/outline/36-lessons-outline.md)
2. 每课练习看 [`course/lesson-plans/`](./course/lesson-plans/) 对应模块(有骨架代码 + 参考答案)
3. 想跑通某节代码时,直接看 [`examples/hello-agent/`](./examples/hello-agent/)

### 我要**开课带学员**
1. 教案主入口 [`course/lesson-plans/README.md`](./course/lesson-plans/README.md)
2. 每一课都是"照本宣科"的讲师讲稿:
   - 五、教学过程(含开场、讲解、练习、测查、小结的板书文本)
   - 六、测查(4 选 1 单选,含答案与解析)
   - 七、课堂练习(完整发放版 = 任务 + 骨架 + 验收清单 + 参考答案 + 常见陷阱 + 挑战题)
3. 每课末尾附**教学准备**(环境、代码、教具、应急预案)
4. 想验证例子仍可执行 → 运行 [`course/tests/`](./course/tests/) 下的 T01 – T11(读 `examples/hello-agent/.env` 里的 LLM 配置)

### 我要**跑 Demo**
```powershell
cd examples/hello-agent
Copy-Item .env.example .env       # 填入 OPENAI_API_KEY / OPENAI_BASE_URL / AGENT_MODEL
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py "现在北京时间几点?"
```

更详细的开关、评测、Trace 查看器等见 [`examples/hello-agent/README.md`](./examples/hello-agent/README.md)。

---

## 内容规模

| 部分 | 数量 |
|------|------|
| 讲师讲稿(教案) | 7 模块 / 36 课 / 约 76 万字符(合并) |
| 单元测试(可执行) | 11 个覆盖 M1 – M7 主要用例 |
| 独立参考文档 | 3 篇 |
| 完整 Demo 代码 | 15+ Python 模块,含 Reflexion / Multi-Agent |

---

## 关于 `_backup/`

以下内容在本次重组时移入 `_backup/`,已从 git 版本库中排除:

- `_backup/my-agent/` —— 早期空实验目录(仅含 pip venv)
- `_backup/hello-agent-runtime/traces/` —— 30+ 老 trace jsonl 历史数据
- `_backup/hello-agent-runtime/reports/` —— 早期 Issues Agent 生成的示例报告

如需查阅历史数据可直接进入 `_backup/` 目录浏览;确认无需保留后可直接删除整个目录。
新的运行时产物(traces / reports / memory.db / evals report-*.jsonl)会重新写入
`examples/hello-agent/` 里,并同样被 `.gitignore` 排除。

---

## 许可 / 使用建议

- **学员**:可以直接使用 `course/outline/` + `examples/hello-agent/` 做自学
- **讲师**:`course/lesson-plans/` 是"打开就能上课"的完整讲稿
- **开发者**:`examples/hello-agent/` 是可以 fork 修改的项目基线,遵循 9 Step 架构
