# 模块 3:MCP 协议与工具层(L13–L18)讲师讲稿版

> 本模块核心动作:把 M2 的"内嵌工具"重构成可复用的 **MCP Server**。
> 配套资料:`../../docs/mcp-server-basics.md`、`examples/hello-agent/mcp_server.py`、`examples/hello-agent/issues_agent.py`。

---

## L13 — MCP 协议介绍与价值

### 一、基本信息
- **课时编号**:L13
- **课时时长**:90 分钟
- **课型**:理论 + 业务案例
- **前置**:M2
- **教具**:N×M 与 N+M 对比图、主流 MCP 客户端列表(Cursor / Claude Desktop / Windsurf / Cline 等)。

### 二、教学目标
**知识目标**
- 解释 MCP 的出处(Anthropic 2024 年 11 月)与定位("USB-C for AI")。
- 区分 MCP 与传统 function calling 在标准化 / 传输 / 状态 / 原语 / 复用 5 个维度的差异。

**能力目标**
- 给定一个跨产品集成需求,能说清 MCP 带来的工程收益。
- 能反驳"个人小脚本也要上 MCP"的过度设计。

### 三、教学重点与难点
- **重点**:N×M → N+M 思维转变;MCP 的复用价值。
- **难点**:让做过单一 LLM 集成的学员意识到"不是所有事情都该写在 Agent 里"。

### 四、教学准备

**【教学素材】**
- **工具地图卡片**(A4 打印,分组讨论 20 分钟用):列本团队(或虚拟团队)5 个工具 + 4 个 AI 产品。示例:
  - **工具**:GitHub API / Jira API / Slack API / 内部知识库检索 / Postgres 报表 SQL
  - **AI 产品**:Cursor / Claude Desktop / 内部客服 Agent / 内部代码 review Bot
  - **画法**:左侧列 4 产品,右侧列 5 工具,让学员用连线表示"如果各自集成"会有多少 → 通常 4×5=20 条线,即 20 处胶水代码。**MCP 的价值**:变成 4+5=9 处。
- **MCP vs function calling 对比表**(五.3 已内嵌,课前熟读):架构 / 复用 / 隔离 / 生态 / 学习曲线 5 维。
- **1 个真实 MCP server 例子**(讲师现场演示 3 分钟):`filesystem` MCP server (Anthropic 官方) 在 Cursor 里 `@` 出来,让 AI 读本地 README。
- **1 个"不该用 MCP"反例**:"我只需要给 LLM 加一个 `add(a,b)` 就本进程用" → 手写 tool 30 秒搞定,上 MCP 是过度设计。

**【教学材料】**
- **MCP 类比板书**:"USB-C 于外设"(视觉)、"HTTP 于浏览器"(网络)、"LSP 于 IDE"(生态)—— 三个类比,五.2 讲。
- **架构图 mermaid**:Host(Cursor)-Client(session)-Server(工具进程),清楚区分三层职责。

**【学员课前】**
- 已用过至少 1 款 AI IDE(Cursor / Claude Desktop / VS Code + Copilot 均可),知道"AI 能读文件"的用户体验。
- (可选)提前浏览 [Anthropic MCP 官方文档首页](https://modelcontextprotocol.io/) 3 分钟建立宏观印象。

**【备用方案】**
- 若讨论环节冷场(团队工具都不共享) → 讲师换用虚拟场景"假设你们做一个 AI 客服平台,20 家客户,每家有自己的工单/CRM 系统",逼出 MCP 复用价值。
- 若学员完全没接触过 MCP,概念抽象 → 现场用 Cursor 演示 3 分钟 `filesystem` MCP,视觉冲击最有效,胜过 20 张 slide。

### 五、教学过程

#### 1. 导入:N×M 的痛(8 min)

**提问**:"如果你团队既用 Cursor 又用 Claude Desktop,内部 GitHub API 工具集要写几遍?"

讲师在白板画一个矩阵:
```
              Cursor  Claude  Windsurf  自研Agent
GitHub          ✅      ✅       ✅         ✅
内部API         ✅      ✅       ✅         ✅
DB 查询         ✅      ✅       ✅         ✅
邮件            ✅      ✅       ✅         ✅
```
"每个 ✅ 都是一次集成开发。4 个 host × 4 个工具 = **16 次开发**。"

> 【讲师讲稿】"这就是 LLM 应用生态在 MCP 之前的真实状况——**组合爆炸**。每出一个新模型/新 host,你就要把所有工具再适配一遍;每出一个新工具,你就要在所有 host 里再接一遍。维护成本是 N×M,N 和 M 越大,成本越爆炸。"

> "MCP 把这个问题降到 N+M——只要工具按 MCP 标准实现,任何 MCP 兼容的 host 都能用。这是 MCP 之于 LLM 生态的本质价值。今天我们就来理解 MCP 是什么、为什么需要它,以及它和我们已经会的 function calling 有什么不同。"

---

#### 2. MCP 是什么(15 min)

**定义**:**MCP(Model Context Protocol)** 是 Anthropic 于 **2024 年 11 月**发布的一个**开放标准**,定义了"AI 应用(host)"与"外部工具/数据/服务(server)"之间的统一通信协议。

**关键修饰词**:
- **开放**:不绑定 Anthropic,任何厂商/团队都可以实现 host 或 server。
- **标准**:不是某个 SDK,而是协议规范(基于 JSON-RPC 2.0)。
- **统一**:所有 MCP server 长得一样,所有 MCP host 都能调用。

**生动比喻**——**USB-C for AI**:

> 【讲师讲稿】"以前每个手机充电口都不一样:苹果 Lightning、安卓 micro-USB、Type-C、各种私有接口……你出门要带一堆线。USB-C 出现以后,理论上一根线就够了。MCP 之于 AI 工具,就像 USB-C 之于充电——**一个标准,适配万物**。"

**对应到我们已经会的 function calling**:
- function calling 是"OpenAI 让你怎么定义工具",每家厂商一套;
- MCP 是"如果你按这套规则定义工具,**所有兼容 host 都能用**"。

---

#### 3. N×M → N+M 的工程意义(15 min)

讲师画对比图:

```
没 MCP:N 个 Host × M 个 Server = N × M 个集成(组合爆炸)
                    
有 MCP:N 个 Host + M 个 Server = N + M(线性增长)
                    
        Host                      Server
      ┌──────┐                   ┌──────┐
      │ Cur. │ ──┐         ┌──── │github│
      └──────┘   │         │     └──────┘
      ┌──────┐   │ ┌────┐  │     ┌──────┐
      │ Cla. │ ──┼─│MCP │──┼──── │ slack│
      └──────┘   │ │spec│  │     └──────┘
      ┌──────┐   │ └────┘  │     ┌──────┐
      │ Win. │ ──┘         └──── │  db  │
      └──────┘                   └──────┘
```

**真实案例**:
- 一个 GitHub MCP Server 写一次,Cursor / Claude Desktop / Windsurf / Cline / 自研 Agent **全部能用**。
- 你团队 5 个 AI 产品共享同一套"内部 BI 工具",升级一处所有人受益。
- 鉴权、限流、日志统一在 server 端,**不再散落在 5 个 Agent 里**。

> 【讲师讲稿】"这种'写一次,多处用'听起来简单,但是 SaaS 生态过去十年都在追求这件事——OpenAPI、SOAP、REST 都是这个动机的不同尝试。MCP 是**专为 AI/LLM 场景设计**的版本,带了 AI 特有的'Tools / Resources / Prompts'三类原语(L15 详讲)。"

---

#### 4. MCP vs Function Calling 五维对比(20 min)

讲师在白板列出表格(`../../docs/mcp-server-basics.md` 第 10 节):

| 维度 | OpenAI Function Calling | ChatGPT Plugins(已废弃) | **MCP** |
|---|---|---|---|
| **标准化** | 厂商专有(OpenAI 一套、Anthropic 一套) | 厂商专有 | **开放规范** |
| **传输** | 仅 HTTP API | HTTPS(OpenAPI) | stdio / Streamable HTTP / SSE |
| **状态** | 无状态 | 无状态 | **有会话状态**(session) |
| **原语** | Tools only | Tools only | **Tools + Resources + Prompts** |
| **复用** | 锁厂商 | 锁 OpenAI | **任何兼容 host** |

逐维度讲:

**(1) 标准化**:Function Calling 每家不一样——OpenAI 的 schema 和 Anthropic 的 tool_use 字段不同,你换模型就要改适配代码。MCP 是**协议级标准**,server 实现一次,任何兼容 client 都能用。

**(2) 传输**:Function Calling 完全活在 LLM API 的 HTTP 请求里。MCP 有自己的传输层,**三种可选**:
- **stdio**:本地进程间通信,host 启动 server 作为子进程。桌面 host 最常用。
- **Streamable HTTP**:远程 server 的现代标准(2025 spec 推出),支持流式响应。
- **SSE**:旧版远程协议,已被 Streamable HTTP 替代。

**(3) 状态**:Function Calling 是无状态的——每次请求带全部上下文。MCP 是**会话式**,client 与 server 建立长连接,server 可以记住 client 之前查询过什么。这对"打开数据库连接 / 维持登录态"等场景非常有用。

**(4) 原语**:Function Calling 只有 Tools。MCP 三原语(L15 详讲):
- **Tools**:模型决定调用的动作。
- **Resources**:应用决定塞给模型的只读数据(文件、DB 行)。
- **Prompts**:用户主动触发的模板(斜杠命令)。

**(5) 复用**:这是前面已经讲过的"N+M",不再重复。

> 【讲师讲稿】"我经常被问:'我们已经用 function calling 了,还需要 MCP 吗?' 答案取决于:**你的工具集会不会被多个 AI 产品复用?** 如果你只在一个 Agent 里用,function calling 就够;如果同一个工具集要同时给 Cursor、Claude Desktop、你的 web app 用,MCP 是更优解。"

---

#### 5. 案例研讨:何时该上 MCP(15 min)

**【活动】** 分发 3 张案例,小组判断"该不该上 MCP",并说理由。

**案例 1**:某创业公司,内部有 GitHub、Linear、Slack、自研 BI 工具集,4 个工程师团队各用不同 AI 产品(Cursor、Claude Desktop、自研 Agent)。
- **答案**:**强烈建议上 MCP**。典型 N+M 受益场景,统一鉴权日志,工具维护成本骤降。

**案例 2**:个人开发者周末写一个小脚本,定时整理今日新闻发到自己 Telegram。
- **答案**:**不需要**。一个人用一个脚本,直接 function calling 就够,引入 MCP 反而增加学习/维护成本。

**案例 3**:公司想给 Cursor 接一个"内部代码风格审查器",当前只在 Cursor 用,但**未来 3~6 个月可能扩展到 Claude Code 和 IDE 插件**。
- **答案**:**可以上 MCP**。未来明确多 host 复用,提前 MCP 化避免后期重写。

> 【讲师讲稿】"判断口诀:**当下复用 + 未来 3~6 个月可见复用 → 上 MCP;只有一处用 → function calling 即可**。不要为'万一'付费,这是 L6 决策原则的延伸。"

---

#### 6. 测查 + 小结(15 min)

**测查(10 min)**:
1. 投影第八节 3 道选择题,**学员举手抢答**(30 秒思考),公布答案后讲师针对每题陷阱**点 1~2 句**——尤其第 1 题"Anthropic 2024.11 推出"是 MCP 起源的必知节点,第 3 题"Host / Client / Server 三角色"是后续所有课的基础。
2. **简答 + 场景题**(第 4、5 题)分两组讨论 3 分钟,代表口头作答——场景题"Cursor / Claude Desktop / 自研 Agent 共享工具"是 MCP 价值的最直观体现,讲师要把"统一鉴权 / 升级解耦"展开讲。

**小结(5 min)**:讲师投影 "今天必须带走的 3 句话":

> **今天必须带走的 3 句话**:
> 1. **MCP 解决 N×M → N+M 的组合爆炸**——统一标准让任意 Host 接任意 Server,工具开发者与 Agent 开发者解耦,长远维护成本骤降。
> 2. **三角色**:**Host(应用)** ↔ **Client(协议客户端,每个 server 一个)** ↔ **Server(工具/资源提供方)**——记住这个一对多结构,后面所有 MCP 课都基于它。
> 3. **不是所有工具都该上 MCP**——跨产品复用才值;单点用 function calling 即可,"为'万一'付费"是 L6 选型铁律的延伸。

> 【讲师讲稿】"今天讲的是 MCP 的'为什么'——为什么 2024.11 出现、为什么这么快成事实标准。下节课 L14 我们进入'怎么做'——JSON-RPC 协议、生命周期、传输方式,你将真正动手用 MCP Inspector 看到一个 server 在网线上是怎么说话的。"

#### 7. 作业(2 min)
- 列出自己工作中"至少有 2 个 AI 产品需要同一套工具"的真实场景,下节课分享 2 位。

**参考答案(范例,3 个常见场景)**:

| 场景 | 共享工具 | ≥2 个 AI 产品 |
|---|---|---|
| 客服支撑系统 | `query_order(id)`、`refund(order_id, amount)`、`search_kb(text)` | 客服坐席端 Copilot(微信内嵌)+ 自动 IVR Agent(电话语音)+ 内部 Slack Bot(运营查单) |
| 销售知识库 | `search_product_doc`、`get_pricing(sku)`、`generate_quote(items)` | 售前 Cursor 插件 + 客户官网在线 Agent + 销售 Salesforce 内嵌助手 |
| DevOps 运维 | `query_metrics`、`tail_log(service, n)`、`restart_pod(pod_id)` | 值班 Slack Bot + Cursor 内 SRE 助手 + 客户 Status Page 自动撰写 Agent |

**核心特征**(选场景的判断标准):
1. **同一组工具**被 **2+** 个不同 UI/前端调用(IM、Web、IDE、电话等);
2. 当工具升级时(如 `query_order` 加字段),**所有产品同时受益**;
3. 没有 MCP 之前,每个产品都自己写一遍接入代码,且口径不一致(产品 A 用 `order_id`,产品 B 用 `orderId`,数据团队抓狂)。

**评分维度**:① 至少 1 个具体场景;② 列出至少 3 个共享工具名 + 2 个 AI 产品名;③ 说明"为什么共享比各写一份更好"(N×M 痛点)。

### 六、板书设计
```
MCP = Anthropic 2024.11 开放协议,USB-C for AI

价值:N×M ──▶ N+M(线性,不再爆炸)

vs Function Calling:
  开放标准 | 多传输(stdio/HTTP) | 有状态 | 三原语 | 跨 host 复用

何时上:多个 AI 产品要复用同一套工具 → 上
       只在一处用 → 不上,function calling 够

三角色:Host(含 Client) ── Server
```

### 七、课堂练习(完整发放版)

> 讲师提示:本节练习不涉及代码,考察 **"何时该上 MCP"的判断力**。分 2 题:场景卡分类 + 团队工具地图。总时长 25 分钟。

#### 练习 1:6 个场景做 "MCP or 手写 tool" 判断(15 min,3 人小组)

**任务**:阅读 6 个场景,每场景给出 (选择 / 理由 / 反选理由),3 项都写完整。

| # | 场景 | 选择 | 理由 | 为何不选另一个 |
| - | ---- | ---- | ---- | ---- |
| A | 项目里就 1 个工具 `add(a,b)`,只本进程用 | | | |
| B | 4 个 AI 产品(Cursor/Claude/内部客服/内部 code bot)都要访问同一套 5 个业务 API | | | |
| C | Python Agent 内部要访问自家用户数据库,不打算给其他工具复用 | | | |
| D | 想让 Cursor 能读你个人电脑上任意目录的文件 | | | |
| E | 云端 Agent 服务,10 个团队共用一套 GitHub 集成 | | | |
| F | 单次实验:用 Python 脚本测试 GPT-4 的 function calling 效果 | | | |

**决策口诀**(讲师板书):
```
1 个工具、1 个宿主 → 手写(function calling)
N 个宿主共用同 M 个工具 → MCP(把 N×M 变 N+M)
IDE 侧场景("我要 Cursor 读文件") → MCP(生态已成熟,一装即用)
实验/一次性脚本 → 手写(setup 成本 > 收益)
```

**参考答案**:

| # | 选择 | 理由 | 反选 |
| - | ---- | ---- | ---- |
| A | **手写** | 单工具单宿主,MCP 是过度设计 | MCP:setup + 跨进程通信开销毫无收益 |
| B | **MCP** | 典型 N×M 痛点,MCP 让 5 个 server + 4 个 Host 即可 | 手写:4 处胶水代码,任一改动都要全同步 |
| C | **手写** | 单宿主 + 数据库敏感,无跨进程需求 | MCP:引入进程隔离反而复杂化 |
| D | **MCP** | Cursor + 文件系统是 MCP 官方最经典场景 | 手写:Cursor 里没法插自定义函数 |
| E | **MCP** | 10 团队共用 = 复用最大化 | 手写:每团队一份 duplicate,维护地狱 |
| F | **手写** | 一次性实验,不需要复用 | MCP:装 fastmcp + 起进程完全浪费时间 |

**验收 checklist**:
- [ ] 6 张卡都填齐 3 列
- [ ] "反选理由"不是"我不熟",必须是场景 vs 能力错配
- [ ] 至少 4 张答对(A/B/D/F 是最典型的)

**常见误判**:
- 看 A 想上 MCP 显得"高大上" → 记住"手写≠落后",单场景手写最快
- 看 C 想上 MCP 觉得"生产系统必须 MCP" → 单宿主不 MCP,只是把简单事复杂化

---

#### 练习 2:画自己团队的工具地图(10 min,个人 or 小组)

**任务**:5 分钟内画出下面矩阵,填空后回答 3 问。

**矩阵模板**:
```
             │ 产品/宿主 A │ 产品/宿主 B │ 产品/宿主 C │ 产品/宿主 D │
─────────────┼─────────────┼─────────────┼─────────────┼─────────────┤
 工具 1      │             │             │             │             │
 工具 2      │             │             │             │             │
 工具 3      │             │             │             │             │
 工具 4      │             │             │             │             │
 工具 5      │             │             │             │             │
```

**填法**:
- 左列填**你/你们团队要接的 5 个业务工具**(如 Jira / Slack / 内部 CRM / RAG 知识库 / SQL 报表)
- 顶行填**要接入这些工具的 4 个 AI 产品/宿主**(如 Cursor / 客服 Agent / 内部 code review Bot / 日报 Agent)
- 交叉格打 ✓ 表示"这个产品需要这个工具",✗ 表示"不需要"

**3 问**:
1. 打了多少个 ✓?(通常 10-15 个 = 需要多少处胶水)
2. 如果用 MCP,server 数 + client 数各是多少?
3. 用 MCP 后代码量减少几倍?

**参考样例**:
```
             │ Cursor │ 客服 Agent │ Code Bot │ 日报 Agent │
─────────────┼────────┼────────────┼──────────┼────────────┤
 Jira        │   ✓    │     ✓      │    ✗     │     ✓      │
 Slack       │   ✗    │     ✓      │    ✓     │     ✓      │
 内部 CRM    │   ✗    │     ✓      │    ✗     │     ✗      │
 RAG 知识库  │   ✓    │     ✓      │    ✗     │     ✗      │
 SQL 报表    │   ✗    │     ✗      │    ✗     │     ✓      │
```
- ✓ 数 = 10 个(手写胶水 = 10 处)
- MCP 版:5 个 server + 4 个 client = 9(改动只需在 server 侧一次)
- 缩减 ≈ 10 → 4(某工具改动只需改一处而不是 4 处)

**验收**:
- [ ] 矩阵填完,✓ 数 ≥ 8(说明确实有复用价值)
- [ ] 三问都数值化回答
- [ ] 判断结论:"我们团队值得 / 不值得引入 MCP,理由是..."

**挑战延伸(选做)**:
- 如果 2 年后再加 2 个新 AI 产品(比如"内部值班机器人"、"周报 Agent"),MCP 版 vs 手写版新增工作量差多少?
- 有哪些工具是"敏感度高不适合 MCP"(如涉及密码/生产 DB)?为什么?

### 八、测查题与参考答案

1. MCP(Model Context Protocol)由谁、何时推出?  A. OpenAI 2024.04  **B. Anthropic 2024.11**  C. Google 2025.01  D. 开源社区匿名贡献 → **B**。Anthropic 2024 年 11 月开源,Claude Desktop、Cursor、Windsurf 等很快跟进,2025 年成事实标准。
2. 把 MCP 比喻为 "USB-C for AI" 的核心价值是?  **A. 统一标准、即插即用——任意 Host 接任意 Server,不再 N×M 重复开发**  B. 数据传输速度极快  C. 强制使用 USB-C 物理接口  D. 仅适用于 Anthropic 的模型 → **A**。USB-C 类比的核心是"标准接口让设备解耦",MCP 也是这个思想——工具与 Agent 解耦。
3. MCP 架构里包含哪 3 个角色?  **A. Host(宿主应用) / Client(协议客户端) / Server(工具服务器)**  B. Client / Server / Database  C. Frontend / Backend / Database  D. User / Agent / LLM → **A**。Host 是 Cursor / Claude Desktop 这样的应用;每个 Host 内部为每个外接 Server 起一个 Client;Server 是工具/资源提供方。
4. **简答**:N+M 比 N×M 重要在哪?
   - **参考答案**:N+M 是线性,N×M 是组合爆炸;工具/Host 越多差距越大;团队无需为每种组合重复开发集成,长远维护成本极低。
5. **场景**:同时用 Cursor / Claude Desktop / 自研 Agent,共享内部 API 工具集,MCP 帮什么?
   - **参考答案**:把内部 API 封装成一个 MCP Server,三端通过各自 MCP Client 接入,实现"一处实现、处处可用";统一鉴权、限流、日志;升级工具不动 Agent 代码。

### 九、教学反思要点
- 学员能否真理解"组合爆炸"的可怕?如果不能,多举企业真实例子(如 5 个团队 8 个工具的矩阵)。
- 反例:个人脚本是否值得上 MCP?提前埋下"MCP 不是万灵药"的预期。

---

## L14 — MCP 架构与生命周期

### 一、基本信息
- **课时编号**:L14
- **课时时长**:90 分钟
- **课型**:理论 + 抓包(可选)
- **前置**:L13
- **教具**:MCP Inspector(`npx @modelcontextprotocol/inspector`)、一个已知能跑的 demo server。

### 二、教学目标
**知识目标**
- 画出 Host / Client / Server 数据流。
- 区分 stdio / SSE / Streamable HTTP 三种传输的适用场景。
- 列出会话生命周期 4 个阶段并能解释每个阶段做什么。

**能力目标**
- 用 MCP Inspector 连一个本地 server,看到完整的握手 JSON。
- 能根据"本地 vs 远程"选择正确的传输方式。

### 三、教学重点与难点
- **重点**:生命周期 4 阶段 + 传输选择。
- **难点**:学员对 JSON-RPC 与 SSE/HTTP 不熟,需要简短铺垫。

### 四、教学准备

**【环境 / 依赖】**
- **Python**:讲师机 `pip install "mcp[cli]" fastmcp`,3.10+。
- **Node.js 18+**:MCP Inspector 是 npm 包,现场跑 `npx @modelcontextprotocol/inspector`。**课前必装**并 `node -v` 确认。
- **端口**:Inspector 默认 6274(UI)+ 6277(proxy),课前检查这两个端口未被占用(`netstat -ano | findstr 6274`)。

**【代码素材】**
- **已跑通的 demo server**:`examples/hello-agent/mcp_server.py`(FastMCP 版),至少含 1 个 `@mcp.tool` 装饰的 `now_time` 或 `add`。**课前跑一次** `python mcp_server.py` 确认能启动。
- **原始 JSON-RPC 报文样本**(五.3 讲协议):
  - Request:`{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}`
  - Response:`{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"now_time",...}]}}`
  - Error:`{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"Method not found"}}`
- **stdio vs HTTP 对比** minimal 两段:同一个 server,分别用 stdio(subprocess pipe)和 HTTP(uvicorn) 起,让学员看差异。

**【数据 / 样例】**
- **Inspector 演示步骤**(现场跟着做):
  1. 终端 A:`python mcp_server.py`(stdio 版可通过 Inspector 直连)
  2. 终端 B:`npx @modelcontextprotocol/inspector python mcp_server.py`
  3. 浏览器打开 http://localhost:6274,点 `Tools → list`,看到 `now_time`
  4. 点 `Call`,填空参数,看到返回时间戳
- **报文截屏**:课前把 Inspector 里的 raw JSON 截图 4 张(list_tools request / response / call_tool request / response),备投影。

**【教学材料】**
- **JSON-RPC 3 要素**板书:`jsonrpc / id / method+params`,响应 `result 或 error 二选一`。
- **传输 3 种**对比表:stdio(本地进程,零配置)/ HTTP(远程,需鉴权)/ SSE(流式,已被 HTTP streamable 替代但历史遗留)。

**【学员课前】**
- 已装 Node 18+ 并跑 `npx -v` 能出版本号。
- 熟悉 L13 的 MCP 架构三层(Host/Client/Server),知道 Inspector 扮演 Host+Client 的角色。

**【备用方案】**
- 若 npx 走不通(内网 npm) → 讲师本地已 clone `@modelcontextprotocol/inspector` 源码,`npm install && npm run dev` 起本地版。
- 若 Inspector UI 挂了 → 讲师 fallback 到**手写 curl / Postman** 直接打 HTTP 版 server 的 `/messages` 端点发 raw JSON-RPC,同样能演示协议。

### 五、教学过程

#### 1. 导入(5 min)

**提问**:"假设你刚连上一个新 MCP server,你怎么知道它提供了哪些工具?"

> 【讲师讲稿】"答案肯定不是'去 README 里查'——那是给人看的。Client 与 Server 之间有一套**自我描述**的协议:Client 一连上就先问'你能干什么',Server 列出全部工具/资源/提示。今天我们就把这套协议的'生命周期'走一遍,看清每个阶段发生了什么。"

---

#### 2. 角色与数据流(15 min)

讲师画完整图:

```
┌────────────────┐                              ┌────────────────┐
│   MCP Host     │   JSON-RPC 2.0 over          │   MCP Server   │
│ (Cursor / CD)  │ ◀────────────────────────▶   │  (your tool)   │
│  ┌──────────┐  │   stdio / HTTP / SSE         │                │
│  │MCP Client│  │                              │   - Tools      │
│  └──────────┘  │                              │   - Resources  │
└────────────────┘                              │   - Prompts    │
                                                └────────────────┘
                                                        │
                                                        ▼
                                            外部 API / DB / 文件 / 网络
```

**三角色澄清**:

| 角色 | 谁 | 职责 |
|---|---|---|
| **Host** | 用户直接交互的 AI 应用 | 决定何时连 server、把 LLM 与工具粘合 |
| **Client** | Host 内置的连接器 | 与 server 1:1 长连接,JSON-RPC 通信 |
| **Server** | 你写的工具程序 | 暴露 tools/resources/prompts,执行调用 |

> 【讲师讲稿】"很多人把 Client 和 Host 混为一谈。准确说:**Host 是用户能看到的应用,Client 是 Host 内部的一个组件**。你不会单独看到 Client。一个 Host 通常会启动多个 Client,每个 Client 连接一个 Server。"

**底层协议**:**JSON-RPC 2.0**——一种轻量级的 RPC 规范,长这样:

```json
// 请求
{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

// 响应
{"jsonrpc": "2.0", "id": 1, "result": {"tools": [...]}}

// 错误响应
{"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "Method not found"}}
```

> 【讲师讲稿】"JSON-RPC 2.0 是一个非常老但仍然好用的标准——比 REST 简单,比 gRPC 易调试。MCP 选它是务实选择。每条消息都有 `id`,**请求和响应靠 id 对应**,所以你可以并发发多条请求不混乱。"

---

#### 3. 三种传输精讲(20 min)

| 传输 | 场景 | 优点 | 缺点 |
|---|---|---|---|
| **stdio** | 本地 server | 简单、零网络配置 | 仅同机 |
| **Streamable HTTP** | 远程 server(2025 后推荐) | 跨网络、支持流式 | 需考虑鉴权/CORS |
| **SSE(legacy)** | 远程 server(旧) | 兼容旧版 | 已被 Streamable HTTP 替代,不再推荐 |

**stdio 工作原理**:
- Host 把 Server 当**子进程**启动(比如 `python my_server.py`)。
- Server 的 **stdin** 是接收请求,**stdout** 是发送响应,**stderr** 留给日志。
- 进程间通过管道(pipe)通信,**不走网络**,延迟极低。
- 进程结束 = 连接结束。

> 【讲师讲稿】"stdio 的简单和优雅怎么强调都不过分——你的 server 就像一个命令行工具,Host 把 stdin/stdout 接过去就完事。所有的'监听端口 / 鉴权 / CORS'都不用考虑。**只要你的 server 跑在本地,优先选 stdio**。"

**Streamable HTTP 工作原理**:
- Server 跑在 HTTP 服务端,Host 通过 HTTP 请求与之通信。
- 支持流式(增量返回结果)、SSE 风格的事件推送。
- 通常配合 Bearer Token / OAuth 做鉴权。
- 适合**远程团队共享**的 server。

**SSE 已经 deprecated**,不要在新项目里用。

---

#### 4. 生命周期 4 阶段(20 min)

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│Initialize│ → │Discovery │ → │Invocation│ → │ Shutdown │
└──────────┘   └──────────┘   └──────────┘   └──────────┘
  握手协议      列工具/资源    调用 tool/读   清理关闭
  + 能力交换    /prompts       resource
```

**(1) Initialize(握手)**

Client 发请求:
```json
{"method": "initialize", "params": {
  "protocolVersion": "2025-06-18",
  "capabilities": {"sampling": {}, "roots": {}},
  "clientInfo": {"name": "Cursor", "version": "0.42"}
}}
```
Server 响应:
```json
{"result": {
  "protocolVersion": "2025-06-18",
  "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
  "serverInfo": {"name": "demo-server", "version": "1.0"}
}}
```

**关键**:双方交换"自己支持什么能力(capabilities)",后续 client 只调用 server 声明支持的能力。

**(2) Discovery(发现)**

Client 调用:
- `tools/list` → 拿到所有工具的 name + description + schema。
- `resources/list` → 拿到所有可用资源 URI。
- `prompts/list` → 拿到所有 prompt 模板。

讲师演示:用 MCP Inspector 跑 `tools/list`,看返回结构。

**(3) Invocation(调用)**

Client 调用:
- `tools/call` + 工具名 + 参数 → server 执行返回结果。
- `resources/read` + URI → 拿资源内容。
- `prompts/get` + prompt 名 → 拿模板。

**(4) Shutdown(关闭)**

正常关闭通常是 client 主动结束(关闭 host 或断开 server),stdio 模式 server 进程被回收。

> 【讲师讲稿】"这 4 个阶段每次都跑一遍——Cursor 每次启动都会对每个 server 做 initialize → discovery,然后才让 LLM 用。**你写的 server 必须正确响应 initialize 和 list 请求,否则 host 看不到你的工具**。这是新手最常见的故障。"

---

#### 5. MCP Inspector 现场演示(20 min)

```bash
npx @modelcontextprotocol/inspector python examples/hello-agent/mcp_server.py
```

讲师在浏览器打开 Inspector UI(通常 http://localhost:5173),逐步骤点:

1. 点击 "Connect" → 看 initialize 请求/响应 JSON。
2. 切到 "Tools" 标签 → 自动触发 tools/list,看返回。
3. 选一个工具,填参数,点 "Call" → 看 tools/call 请求/响应。
4. 切到 "Resources"、"Prompts" 看其他原语。
5. 关闭 → 看 shutdown。

> 【讲师讲稿】"MCP Inspector 是写 MCP server 的'最佳调试伴侣'。它让协议层完全可视化,你写错任何 schema、漏任何字段,这里立刻看出来。**永远在接入 Host 之前,先用 Inspector 验证 server**。"

---

#### 6. 测查 + 小结(10 min)

**测查(7 min)**:投影第八节 3 道选择题,**学员举手抢答**(30 秒思考),公布答案后讲师针对每题陷阱**点 1 句**——尤其第 3 题"2025+ 用 Streamable HTTP 替代老 SSE"是规范更新点,跟不上会出现"按老文档抄不通"的坑。简答与场景题作为课后练习。

**小结(3 min)**:讲师投影 "今天必须带走的 3 句话":

> **今天必须带走的 3 句话**:
> 1. **MCP 底层 = JSON-RPC 2.0 + 4 阶段生命周期**(initialize → capabilities 协商 → 调用 → close)——所有 MCP server 都按这个剧本走。
> 2. **传输选型**:**stdio 走本地、Streamable HTTP 走远程**(2025+ 替代老 SSE)——选错传输跨网络场景直接跑不起来,且非常隐蔽难排查。
> 3. **MCP Inspector 是必备调试器**——接 Host 之前先 Inspector 验证 server,90% 协议层问题在这一步暴露。

> 【讲师讲稿】"L14 把'协议层'讲透了,L15 我们进入 MCP 的'语义层'——三大原语 Tools / Resources / Prompts。今天讲的 JSON-RPC 是怎么传,L15 讲的是传什么、传的语义边界。回家先用 Inspector 连一个公开 server,看看 initialize 真实交换的 capabilities 长什么样。"

#### 7. 作业(5 min)
- 用 MCP Inspector 连一个公开的 server(如 `@modelcontextprotocol/server-filesystem`),提交一份"initialize 时交换了哪些 capabilities"的笔记。

**参考答案(操作步骤 + sample 笔记)**:

```bash
# 启动 Inspector 连 filesystem server,允许它读 /tmp
npx -y @modelcontextprotocol/inspector \
    npx -y @modelcontextprotocol/server-filesystem /tmp

# 浏览器自动打开 http://localhost:6274,点 "Connect"
```

**Sample 笔记**(把 Inspector 左侧 "History" 标签里的 `initialize` 请求/响应抄下来):

```jsonc
// → Client → Server (initialize request)
{
  "jsonrpc": "2.0",
  "id": 0,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-03-26",
    "capabilities": {
      "roots": { "listChanged": true },
      "sampling": {}
    },
    "clientInfo": { "name": "mcp-inspector", "version": "0.x" }
  }
}

// ← Server → Client (initialize response)
{
  "jsonrpc": "2.0",
  "id": 0,
  "result": {
    "protocolVersion": "2025-03-26",
    "capabilities": {
      "tools":     { "listChanged": true },   // 该 server 提供 tools
      "resources": { "listChanged": true, "subscribe": true }
      // 注意:没有 "prompts" 字段 → 该 server 不提供 prompts
    },
    "serverInfo": { "name": "filesystem-server", "version": "0.x" }
  }
}
```

**笔记应回答的 3 个问题**:
1. **client 声明了什么能力**?(`roots` = 客户端可被查询 workspace 根目录;`sampling` = 客户端可被 server 反请 LLM)
2. **server 声明了什么能力**?(`tools` / `resources` 必有,`prompts` 视 server 定;`listChanged` 表示该 namespace 变化时会主动推 notification)
3. **双方对 `protocolVersion` 是否一致**?不一致会失败或降级。

**评分要点**:
1. 截图或抄录真实 JSON-RPC(假数据扣分);
2. 标注 client 与 server 各自的 capabilities;
3. 至少识别出 1 个"该 server 不支持的能力"(如 filesystem 通常不提供 prompts)。

### 六、板书设计
```
Host(含 Client) ──JSON-RPC 2.0──▶ Server
传输:stdio(本地,首选) | Streamable HTTP(远程) | SSE(legacy)

生命周期 4 阶段
  initialize  → 握手 + capabilities 交换
  discovery   → tools/list, resources/list, prompts/list
  invocation  → tools/call, resources/read, prompts/get
  shutdown    → 清理

调试:npx @modelcontextprotocol/inspector <command>
```

### 七、课堂练习(完整发放版)

> 讲师提示:本节练习让学员**亲手用 MCP Inspector 抓包**,从 UI 到 raw JSON-RPC 看透协议。需 Node 18+ + Python 环境已装(见教学准备)。总时长 30-40 分钟。

#### 练习 1:用 Inspector 抓完整生命周期(20 min,个人)

**任务**:用 MCP Inspector 连接讲师提供的 `mcp_server.py`,完成 4 步抓包,把每步的 **raw JSON-RPC 请求 + 响应** 记录下来。

**准备**:
```bash
# 讲师提供的 mcp_server.py(见教学准备)
# 学员机上直接跑:
npx @modelcontextprotocol/inspector python C:/path/to/mcp_server.py
# 打开浏览器 http://localhost:6274
```

**4 步任务**:
1. **initialize**:点 Connect 按钮,观察左侧 "History" 里第一条 request/response
2. **tools/list**:点 Tools 面板,记录 request/response,数一数返回了几个 tool
3. **tools/call**:选一个 tool 填参数点 Call,记录 request/response
4. **shutdown**:点 Disconnect,观察是否有终止 notification

**记录模板**(填 4 段):
```json
// 1. initialize
Request:  { "jsonrpc":"2.0", "id":..., "method":"initialize", "params":{...} }
Response: { "jsonrpc":"2.0", "id":..., "result":{...} }

// 2. tools/list  ← 请求为空,响应含 tools 数组
Request:  ...
Response: ...

// 3. tools/call
Request:  { "jsonrpc":"2.0", "id":..., "method":"tools/call", "params":{"name":"now_time","arguments":{}} }
Response: ...

// 4. shutdown / disconnect
...
```

**验收 checklist**:
- [ ] 4 段 raw JSON 都抓到并粘贴到笔记
- [ ] 能指出每次 request 的 `id` 与 response 的 `id` **一一对应**(JSON-RPC 关键机制)
- [ ] 能指出 `method` 字段的作用(路由到哪个 handler)
- [ ] 能区分 **request(有 id 等结果)** vs **notification(无 id,fire-and-forget)**

**参考答案样本**(以 `mcp_server.py` 含 `now_time` tool 为例):
```json
// tools/list request
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}

// tools/list response(示意)
{"jsonrpc":"2.0","id":2,"result":{
  "tools":[
    {"name":"now_time","description":"...","inputSchema":{"type":"object","properties":{...}}}
  ]
}}

// tools/call request
{"jsonrpc":"2.0","id":3,"method":"tools/call",
 "params":{"name":"now_time","arguments":{"timezone":"Asia/Shanghai"}}}

// tools/call response
{"jsonrpc":"2.0","id":3,"result":{
  "content":[{"type":"text","text":"2026-07-03T15:00:00+08:00"}]
}}
```

**常见坑**:
- Inspector UI 里 tool result 显示为漂亮 UI,忘了看 raw JSON → **必须打开 "Raw" tab**
- id 每次自增,反例:客户端如果 hardcode id=1 会导致响应对不上号
- notification 例(`notifications/initialized`)没有 id 字段,不需要响应,与 request 区别务必分清

---

#### 练习 2:手动伪造 JSON-RPC 请求(15 min,个人)

**任务**:不用 Inspector,直接用 **curl 或 httpx** 向 HTTP 版 mcp server 发原始 JSON-RPC 请求,验证协议无神秘感。

**准备**:改 `mcp_server.py` 最后一行:
```python
mcp.run(transport="http", port=8765)
```

启动后,用 curl 打:
```bash
# initialize
curl -X POST http://localhost:8765/mcp \
  -H "content-type: application/json" \
  -H "accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"initialize",
    "params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}
  }'

# tools/list
curl -X POST http://localhost:8765/mcp \
  -H "content-type: application/json" \
  -H "accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: <上一步 response header 里返的>" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

**任务要求**:
1. 完整跑一遍 initialize → tools/list → tools/call 3 次调用
2. 记下每次 request/response 完整内容
3. 观察 `Mcp-Session-Id` header 的作用

**验收 checklist**:
- [ ] 3 次调用都返 200 + 合法 JSON
- [ ] `id` 严格递增
- [ ] 能解释 `Mcp-Session-Id` 是干什么的(会话状态标识,让 server 知道你是谁)

**参考答案**:HTTP transport 会在 initialize 响应 header 返 `Mcp-Session-Id`,后续请求必须带上,类似 HTTP session cookie。

**常见坑**:
- 缺 `accept: application/json, text/event-stream` header → 服务器可能返 406
- 不带 `Mcp-Session-Id` → 后续 request 会返 "session not initialized"
- 打了 `id=1` 两次 → 服务器会认为重复 request,行为未定义

**挑战延伸(选做)**:
- 尝试打一个**错误的 method**(如 `"method":"foo/bar"`),观察 error 响应格式:`{"jsonrpc":"2.0","id":...,"error":{"code":-32601,"message":"Method not found"}}`
- 尝试**错误的 tool 参数**(必填漏了),观察 error code 和 message
- 用 Python `httpx` 或 `requests` 复刻 curl 请求,写成一个 20 行的最小 MCP client

### 八、测查题与参考答案

1. MCP 消息层使用的底层协议是?  A. gRPC  **B. JSON-RPC 2.0(基于 JSON 的请求/响应/通知规范)**  C. GraphQL  D. 自定义二进制协议 → **B**。JSON-RPC 2.0 简单、跨语言、可读,SSE/stdio/HTTP 三种传输都把 JSON-RPC payload 包在里面。
2. 桌面 Host 连接本地 Server 最常用的传输是?  A. WebSocket  **B. stdio(进程标准输入/输出)**  C. UDP  D. gRPC streaming → **B**。本机进程间通信 stdio 最简单——Host 直接 fork 子进程,通过 stdin/stdout 收发 JSON-RPC,无需端口、无需鉴权。
3. 远程(跨网络)Server,2025 年后官方推荐的传输是?  A. 老 SSE(HTTP + Server-Sent Events)单向  **B. Streamable HTTP(双向流式 HTTP,2025 年 MCP 规范更新后的首选)**  C. 直接 TCP  D. FTP → **B**。老 SSE 已被 Streamable HTTP 替代:支持 GET/POST 双向、断点重连、更易在企业 LB / 反代后部署。
4. **简答**:`initialize` 阶段交换的 capabilities 包含什么?
   - **参考答案**:协议版本、双方各自支持的能力(client 端如 sampling/roots;server 端如 tools/resources/prompts),决定后续可用功能集。
5. **场景**:本地跑通、云端连不通,可能原因?
   - **参考答案**:① 还在用 stdio(跨网络不行,应改 Streamable HTTP);② 缺鉴权 / Token;③ 防火墙/网关阻塞;④ URL/路径错;⑤ Host 不支持远程 MCP 或版本太旧。

### 九、教学反思要点
- Inspector 安装(需要 Node)是否顺利?提前在邀请邮件提醒装好 Node。
- 学员能否复述生命周期 4 阶段?可让 2 位上台画图。

---

## L15 — MCP 三大原语:Tools / Resources / Prompts

### 一、基本信息
- **课时编号**:L15
- **课时时长**:90 分钟
- **课型**:理论 + 案例选型
- **前置**:L14
- **教具**:三种原语各一段最小代码示例。

### 二、教学目标
**知识目标**
- 区分三原语的控制方(model / app / user)与典型用途。
- 列举每种原语至少 2 个真实案例。

**能力目标**
- 给定一个需求(如"让 Agent 读项目某文件"),正确选择原语。
- 能反驳"把所有东西塞成 Tools" 的反模式。

### 三、教学重点与难点
- **重点**:三原语的"控制方"差异——谁决定何时使用。
- **难点**:学员习惯把所有东西塞 Tools,需要打破这个直觉。

### 四、教学准备

**【环境 / 依赖】**
- 继承 L14 环境(`fastmcp` + Node)。
- 讲师本地已跑通一个"三原语齐全"的 `demo_server.py`:1 个 `@mcp.tool`、1 个 `@mcp.resource("data://weather/{city}")`、1 个 `@mcp.prompt("summarize")`。

**【教学素材】**
- **5 张需求卡片**(A5 打印,分组讨论 15 分钟用),正确答案分布在三原语之间:
  | # | 需求 | 应该用 | 常见错答 |
  | - | ---- | ---- | ---- |
  | 1 | 查天气 API 实时返回 | **Tool**(有副作用/需入参) | 有人写成 Resource |
  | 2 | 用户历史订单 top 10(只读列表) | **Resource** | 有人写成 Tool |
  | 3 | "分析这份日志"的固定 prompt 模板 | **Prompt** | 有人写死在 code |
  | 4 | 项目 README(纯文档) | **Resource** | 有人塞 system_prompt |
  | 5 | 发邮件 | **Tool**(明确副作用) | 有人不知道该选哪个 |
- **三原语最小代码**(五.3、5.4、5.5 各一段,课上分屏投影):
  - Tool:`@mcp.tool()\ndef add(a:int, b:int) -> int: return a+b`
  - Resource:`@mcp.resource("data://users/{uid}")\ndef user(uid: str) -> dict: return db.fetch(uid)`
  - Prompt:`@mcp.prompt()\ndef summarize(text: str) -> str: return f"请用 3 句话总结:{text}"`

**【数据 / 样例】**
- **判断口诀**(五.6 讲):
  - 有**副作用**或需要**入参驱动的动作** → **Tool**
  - **只读**、URI 可寻址、结构化 → **Resource**
  - 可复用的**文本模板** → **Prompt**
- **反面案例**:某学员把"pip install openai"包成 Resource → 错。**Resource 必须只读无副作用**。

**【教学材料】**
- **三原语职责表**(五.2 已内嵌):Verb(是不是动作)/ Side effect(副作用)/ Cache-friendly(是否可缓存)/ 客户端语义。
- **Cursor 里三原语的呈现方式**:
  - Tool → AI 自动调用
  - Resource → 用户 `@` 引用
  - Prompt → Slash command

**【学员课前】**
- 已在 L14 跑通 Inspector 看到 tool 列表。
- 想清楚"自己团队的常用需求里,哪些是只读 vs 有副作用",本课要给它们分类。

**【备用方案】**
- 若学员对 URI scheme(`data://xxx/{yyy}`)完全没直觉 → 类比 HTTP URL:host+path+query 三段,`data://` 就是自定义 scheme。
- 若讨论环节 5 张卡片答得都对(团队水平高) → 增补 3 张边界卡片:如"查询余额"(其实是 Resource 但很多人直觉 Tool)、"扫描漏洞"(Tool 但很多人误 Prompt)。

### 五、教学过程

#### 1. 导入:同一件事,三种做法(5 min)

**提问**:"你想让 LLM 读一份 100 行的项目 README,该怎么做?"

收集学员答案,通常会有三种:
- A:写一个 `read_file` 工具,LLM 想读就调。
- B:Host 启动时直接把 README 内容塞进 system prompt。
- C:做一个 `/load-readme` 斜杠命令,用户主动触发。

> 【讲师讲稿】"这三种做法**没有对错,但对应的是 MCP 的三种不同原语**——A 是 Tools(模型决定),B 是 Resources(应用决定),C 是 Prompts(用户决定)。今天我们要把这三者的边界讲清楚,以及为什么不能'万事皆 Tools'。"

---

#### 2. 三原语精讲(30 min)

##### 2.1 Tools(model-controlled)

**定义**:LLM 自己决定何时调用、用什么参数的**动作**。

**最小代码**:
```python
@mcp.tool()
def create_github_issue(repo: str, title: str, body: str) -> str:
    """Create a new GitHub issue. Use when user asks to file an issue."""
    issue = gh_client.create_issue(repo, title, body)
    return f"Created issue #{issue.number}"
```

**典型场景**:`create_issue` / `send_email` / `query_db` / `delete_file` / `book_flight`。

**关键特征**:
- **由模型 token-by-token 选用**——选用准确率受 description 影响极大(回顾 L3)。
- 通常**有副作用**(写、删、发送)。
- Host 通常会**弹窗让用户确认**(防危险动作,L29 HITL 详讲)。

##### 2.2 Resources(application-controlled)

**定义**:Host 应用决定何时塞给 LLM 的**只读数据**,通过 URI 唯一寻址。

**最小代码**:
```python
@mcp.resource("file://{path}")
def read_file(path: str) -> str:
    """Read contents of a file. URI format: file:///absolute/path."""
    with open(path) as f:
        return f.read()
```

**典型场景**:文件内容、数据库行、最近 N 条日志、配置项。

**关键特征**:
- **由 Host 决定何时读**——通常是用户"@文件"或 Host 启动时预加载。
- **只读**,LLM 不会主动改它。
- 用 URI 寻址(`file://`、`db://`、`http://`、自定义 scheme 都行)。

> 【讲师讲稿】"为什么文件读取做成 Resource 而不是 Tool?有两个原因:第一,**用户通常知道要给 LLM 看哪个文件**,不需要 LLM 在 50 个文件里猜;第二,**Tools 描述吃 context window**,如果你把 `read_file_1, read_file_2, ...` 全做成 tool,模型注意力会被稀释,选用准确率反而下降。Resources 不进入 tools 列表,只在被用到时塞进上下文,**对模型决策更友好**。"

##### 2.3 Prompts(user-controlled)

**定义**:用户主动触发的**模板**,通常表现为斜杠命令(slash commands)。

**最小代码**:
```python
@mcp.prompt()
def summarize_pr(diff: str) -> str:
    """Generate a PR summary from a diff."""
    return f"""请对以下 diff 写一份 100 字以内的中文摘要:

{diff}

要求:
- 列出主要改动点
- 说明可能的风险
- 用 markdown bullet 列表
"""
```

**典型场景**:`/summarize-pr`、`/explain-code`、`/translate-to-en`、`/draft-reply`。

**关键特征**:
- **用户主动触发**——通常是 host UI 里的斜杠命令或按钮。
- **模板化复用**——避免用户反复打同样的 prompt 前缀。
- 通常**不直接调工具**,只是把模板填好的 prompt 喂给 LLM。

---

#### 3. 选型决策(20 min)

讲师画出选型决策树:

```
这件事是?
├── 让 LLM 执行动作(写、删、发送)   ──▶ Tools
├── 给 LLM 提供只读数据(文件、行、API 结果)  ──▶ Resources
└── 用户想一键复用的提示词模板  ──▶ Prompts
```

**【活动】** 5 张卡片选型练习,学员独立写答案,讲师核对:

1. "删除一个 GitHub issue" → **Tool**(有副作用动作)。
2. "读取项目根目录的 README.md" → **Resource**(只读数据 + URI)。
3. "一键生成本周开发周报" → **Prompt**(用户触发模板)。
4. "查询某个用户的当前订单状态" → **Tool**(LLM 决定何时查、查谁,有 LLM 决策成分)。
   - 但如果是"用户点击订单详情时自动塞 LLM",那是 **Resource**。
5. "把代码翻译成 Python" → **Prompt**(用户触发模板,代码作为参数)。

> 【讲师讲稿】"第 4 题的微妙之处值得品味:**同样一件事,谁决定的不同,就该选不同原语**。'LLM 决定'是 Tool,'应用决定'是 Resource,'用户决定'是 Prompt。这三个维度希望大家记住:Model / Application / User —— **MAU**(顺便记个易记口诀)。"

---

#### 4. "为什么不能全塞 Tools"(15 min)

讲师列出 3 个核心理由:

**(1) Tools 描述吃 context window**

每个工具的 description + schema 都要进 LLM 的请求 token,**工具越多,system 越长,实际 user/history 能用的空间越小**。10 个工具可能就吃几千 token。

**(2) Tools 多 → 模型选择准确率下降**

实验证明:工具数从 3 个增加到 30 个,选用准确率显著下降。模型在更多选项里"分心",经常选错或选错最相似的。

**(3) 语义不清**

`read_file` 做成 Tool,模型每次都要"决定要不要读",但很多场景下**用户已经明确要给 LLM 看哪个文件**——LLM 不需要决策,直接读了塞进去就好,这就是 Resource。

> 【讲师讲稿】"我曾经看过一个团队把 40 个内部 API 全做成 Tool,结果 LLM 经常选错。后来把'查询类'API 改成 Resource(由 Host 在合适时机主动塞),'动作类'保留为 Tool,工具数从 40 降到 12,准确率反而大幅上升。**这是 MCP 三原语设计的核心智慧**。"

---

#### 5. 测查 + 小结(10 min)

**测查(7 min)**:投影第八节 3 道选择题,**学员举手抢答**(30 秒思考),公布答案后讲师针对每题陷阱**点 1 句**。**重点**强调三道题集中考"谁主导调用"——Tools = LLM 主导;Resources = Host 主导;Prompts = User 主导,这是三原语的根本区别。简答与场景题作为课后练习。

**小结(3 min)**:讲师投影 "今天必须带走的 3 句话":

> **今天必须带走的 3 句话**:
> 1. **三原语按"谁主导"区分**:**Tools(LLM 主导,有副作用)** / **Resources(Host 主导,只读数据)** / **Prompts(用户主导,模板)**。
> 2. **不要把所有东西塞 Tools**——工具描述吃 context window,数量多稀释模型注意力、选错率上升;读操作改 Resource、用户触发改 Prompt,工具数下降准确率反升。
> 3. **真实 GitHub Server 设计示例**:`list_issues` → Resource,`create_issue` / `delete_issue` → Tool,`/code_review` → Prompt;这是三原语在生产场景的标准用法。

> 【讲师讲稿】"今天讲的三原语是 MCP server 设计能力的'分水岭'——能正确划分的人写出来的 server 简洁好用,不会划分的人写出来的 server 工具数膨胀、模型选错率高。L16 我们用 FastMCP 真的写一个 server,看三原语在 Python 装饰器里怎么落地。"

#### 6. 作业(5 min)
- 设计 1 个 Resources 与 1 个 Prompts(与自己业务相关),写出最小代码,下节课展示。

**参考答案(以"客服 KB"业务为例)**:

```python
from fastmcp import FastMCP

mcp = FastMCP("customer-kb-server")

# ──────────────── Resource:静态/半静态的"知识" ────────────────
@mcp.resource("kb://product/{sku}/spec")
def product_spec(sku: str) -> str:
    """返回某 SKU 的产品规格文档(Markdown 全文,可被客服 Agent 一次性读完)."""
    # 真实场景从 DB 或 S3 拉取;这里 mock
    return f"# 产品 {sku} 规格\n\n- 重量: 1.2kg\n- 颜色: 黑/白\n- 保修: 2 年"

@mcp.resource("kb://policy/refund")
def refund_policy() -> str:
    """退款政策全文(让模型严格按此政策回答,不要编造)."""
    return "1. 收货 7 天内无理由退款\n2. 拆封后只能换不能退\n3. ..."

# ──────────────── Prompt:模板化的"对话起点" ────────────────
@mcp.prompt()
def handle_complaint(customer_msg: str, order_id: str) -> list[dict]:
    """生成一个'处理客户投诉'的对话模板,由用户在 Cursor/Claude Desktop 里选用."""
    return [
        {
            "role": "system",
            "content": "你是一名资深客服。务必先查询订单详情,再确认退款政策,然后回复客户。绝不编造产品信息。",
        },
        {
            "role": "user",
            "content": (
                f"客户(订单 {order_id})投诉:\n{customer_msg}\n\n"
                f"请按以下步骤处理:\n"
                f"1) 调 `query_order(order_id={order_id})` 拿订单详情\n"
                f"2) 读资源 `kb://policy/refund`\n"
                f"3) 生成 3 行简短回复"
            ),
        },
    ]

if __name__ == "__main__":
    mcp.run()                  # 默认 stdio transport
```

**Resource vs Prompt 选择决策**:
- **Resource**:"模型/Agent **主动读** 的知识"(产品文档、政策、用户档案) → URI 寻址、可缓存。
- **Prompt**:"**用户在 UI 里点击选用**的对话模板"(/handle-complaint、/code-review) → 接收参数、返回 `messages` 数组。

**评分要点**:
1. 至少 1 个 Resource 用 URI 模板(`{sku}` 参数化);
2. 至少 1 个 Prompt 返回 `list[dict]`(messages 数组,含 system + user);
3. 三者(Tools/Resources/Prompts)**职责清晰**——不要把"动作"塞到 Resource 里;
4. 装饰器写对:`@mcp.resource(uri)` / `@mcp.prompt()` / `@mcp.tool()`。

### 六、板书设计
```
三原语口诀:MAU = Model / Application / User

Tools     ─ Model       ─ 动作执行           ─ create_issue / send_email
Resources ─ Application ─ 只读数据塞入       ─ file://... / db://...
Prompts   ─ User        ─ 模板 / 斜杠命令    ─ /summarize-pr

反模式:把所有东西塞 Tools → 描述吃 context、选错率上升、语义混乱
```

### 七、课堂练习(完整发放版)

> 讲师提示:本节练习考察"三原语选型"直觉 + "最小代码"落地能力。总时长 30-35 分钟,分组讨论 + 独立编码结合。

#### 练习 1:12 张需求卡片选型(15 min,3 人小组)

**任务**:阅读 12 张需求卡,每张贴 **Tool / Resource / Prompt** 标签,给一句话理由。

**卡片清单**:

| # | 需求描述 | 你的选择 | 理由 |
| - | -------- | -------- | ---- |
| 1 | 实时查上海天气(返回当前温度) | | |
| 2 | 用户历史订单 top 10(只读列表) | | |
| 3 | 项目 README 全文(纯文档,给 AI 读) | | |
| 4 | 生成 draft 邮件模板"给客户 X 发退款通知" | | |
| 5 | 发送邮件到指定收件人(会实发) | | |
| 6 | 按 URI `data://users/{uid}` 拉某用户资料 | | |
| 7 | "分析这段日志"的通用 prompt 模板 | | |
| 8 | 删除某个数据库行(危险操作) | | |
| 9 | 数据库 schema 元数据(表结构 read-only) | | |
| 10 | 数值计算 `add(a,b)` | | |
| 11 | 常用错误码字典(id → 描述,只读查表) | | |
| 12 | 一段可复用的"客服话术"模板(给用户填参数) | | |

**判断口诀**:
- **动词 + 有副作用/带入参驱动** → **Tool**
- **只读、URI 可寻址、结构化** → **Resource**
- **可复用的文本模板** → **Prompt**

**参考答案**:

| # | 选择 | 理由 |
| - | ---- | ---- |
| 1 | **Tool** | 有入参 city,是"查询动作"(虽只读) |
| 2 | **Resource** | 只读列表,URI 可表示 `data://orders/top?user=alice` |
| 3 | **Resource** | 纯只读文档,典型 resource |
| 4 | **Prompt** | 模板生成动作,给用户填空即可 |
| 5 | **Tool** | **有真实副作用**(发出去邮件) |
| 6 | **Resource** | URI 语义清晰,只读 |
| 7 | **Prompt** | 可复用文本模板,是典型 prompt |
| 8 | **Tool** | 有副作用(且危险,需 HITL) |
| 9 | **Resource** | 只读元数据 |
| 10 | **Tool** | 有入参且是动作(即使纯函数) |
| 11 | **Resource** | 只读查表 |
| 12 | **Prompt** | 模板 + 用户填参数 |

**易错点**:
- #1 查天气有人写 Resource,理由"只读" — **错**,查天气有 city 入参 + 需实时计算,是 tool
- #10 add 有人写 Resource,理由"数学是数据" — **错**,有入参 + 需计算 = tool
- #6 拉用户资料有人写 Tool,理由"有 uid 入参" — **错**,resource URI 允许有模板参数(`{uid}`)

**验收 checklist**:
- [ ] 12 张全部填齐
- [ ] 至少 10 张答对
- [ ] 能说清 Tool 和 Resource 的差别:**Tool 是动词,Resource 是名词;Tool 有副作用/驱动语义,Resource 只读且 URI 可寻址**

---

#### 练习 2:三段最小代码实现(15 min,个人)

**任务**:在自己的 `mcp_server.py` 里,分别写一个最小的 Tool / Resource / Prompt,能被 Inspector 看到。

**骨架代码**:
```python
from fastmcp import FastMCP
mcp = FastMCP("demo-server")

# ============ Tool ============
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers. Use for any addition; do NOT do it in your head."""
    return a + b

# ============ Resource ============
@mcp.resource("data://greeting/{name}")
def greeting(name: str) -> str:
    """A friendly greeting for the given name."""
    return f"Hello, {name}! Welcome to MCP."

# ============ Prompt ============
@mcp.prompt()
def summarize(text: str) -> str:
    """Return a summarization prompt template for the given text."""
    return f"请用 3 句话总结下面的内容:\n\n{text}\n\n输出格式:1) ... 2) ... 3) ..."

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**验收步骤**:
1. `python mcp_server.py` 无报错
2. `npx @modelcontextprotocol/inspector python mcp_server.py`
3. Inspector 里能看到:
   - Tools 面板:1 个 `add`
   - Resources 面板:1 个 `data://greeting/{name}` 模板
   - Prompts 面板:1 个 `summarize`
4. 各自测试:
   - `add(3, 4)` → 返 7
   - Resource URI `data://greeting/Alice` → 返 "Hello, Alice! ..."
   - Prompt `summarize` 填 text 参数 → 返模板字符串

**验收 checklist**:
- [ ] Inspector 里 3 个面板各有 1 项
- [ ] 3 项都能正确 call 出预期结果
- [ ] 每个装饰器函数都有 type-hint + docstring

**常见坑**:
- Resource 里 URI 拼写错 `data:/greeting/{name}`(少斜杠)→ Inspector 里看不到
- Prompt 忘写 docstring,description 变空 → LLM 拿不到用途说明,不会主动调
- `mcp.run(transport="stdio")` 版**不能 print 到 stdout**(会污染协议),用 `import sys; print(..., file=sys.stderr)`

**参考答案**:见上骨架(即完整答案)

---

#### 挑战延伸(选做)

- 给 `greeting` Resource 加入模板参数校验:如果 name 含非字母 → 返 `[ERROR] name must be alphabetic`
- 写第 2 个 Prompt `translate(text, target_lang)`,支持传入文本 + 目标语言
- 让 Tool `add` 拒绝浮点数(强制整数),异常返回改成 fastmcp 建议的 `ToolError` 类
- 用同一 server 同时暴露 tool/resource/prompt,配合 Cursor 观察 3 类原语在 IDE 里 UI 的差别

### 八、测查题与参考答案

1. MCP 三大原语中,Resources 的访问由谁主导发起?  A. LLM 自主决定何时读取  **B. Host 应用主导(如用户 @ 引用文件、Host 把上下文塞进 prompt)**  C. Server 主动推送给所有连接的 Client  D. 由 MCP 协议定时轮询 → **B**。Resources 是"application-controlled context":数据是只读的、由应用层挑选哪些塞给模型,LLM 不主动 select。
2. `/explain-code` 这种斜杠命令对应哪种 MCP 原语?  A. Resource(只读数据)  B. Tool(可执行动作)  **C. Prompt(用户触发的预定义模板)**  D. Sampling(让 Server 反向请求 LLM) → **C**。Prompts 是"user-controlled":用户在 Host UI 里手动点 / 输斜杠,Server 返回填好参数的 prompt 模板。
3. "删除 GitHub issue" 这类带副作用的操作应封装为?  **A. Tool(可执行动作,由 LLM 自主选用,有副作用)**  B. Resource(只读)  C. Prompt(模板)  D. Sampling → **A**。Tools 是"model-controlled action":LLM 决定调不调,有副作用、可能改变外部世界状态。读 issue 列表可用 Resource;删/改 issue 必须 Tool。
4. **简答**:为什么不能把所有东西塞 Tools?
   - **参考答案**:① 工具描述吃 context window,数量多→ 模型注意力稀释、选错率上升;② 只读数据用 Resource 更自然,不需要 LLM 每次决策;③ 用户触发的模板更适合 Prompts,语义清晰。
5. **场景**:"@文件 让 Claude 阅读项目某文件",用哪个原语?
   - **参考答案**:**Resources**。文件内容是应用提供给模型的只读数据,由 Host 主动塞入,语义最贴合。

### 九、教学反思要点
- 学员是否仍倾向把所有东西塞 Tools?可以让大家盘点自己 M2 项目的"工具列表",哪些可以重构成 Resource。
- 卡片选型环节最好替换成本团队真实需求,效果更好。

---

## L16 — 用 FastMCP 编写第一个 MCP Server

### 一、基本信息
- **课时编号**:L16
- **课时时长**:120 分钟(实战课加长)
- **课型**:实操
- **前置**:L15
- **配套代码**:`examples/hello-agent/mcp_server.py`。

### 二、教学目标
**知识目标**
- 解释 `FastMCP` 的装饰器机制(`@mcp.tool / @mcp.resource / @mcp.prompt`)。
- 知道 **docstring 直接成为 LLM 看到的 description**,影响选用率。

**能力目标**
- 写出包含 1 个 Tool、1 个 Resource、1 个 Prompt 的最小 MCP Server。
- 用 MCP Inspector 调试自己的 server。
- 把 M2 的工具迁移到 MCP Server。

### 三、教学重点与难点
- **重点**:装饰器使用、docstring 的重要性。
- **难点**:学员容易忘加 docstring 或写得太短(等同 L3 的 description 问题)。

### 四、教学准备

**【环境 / 依赖】**
- **必装**:`pip install "mcp[cli]" fastmcp`(讲师机课前跑一遍,确保无 pip 报错)。
- **可选**:`pip install httpx`(如果本课演示 HTTP 版 tool 需要外发请求)。
- 学员机 Python 3.10+;上课前 5 分钟统一跑 `python -c "import fastmcp; print(fastmcp.__version__)"` 确认 ≥ 3.0。

**【代码素材】**
- **参考实现 `mcp_server.py`**(讲师提供完整可跑版,课末对比用),包含:
  - 3 个 `@mcp.tool`:`now_time` / `add(a,b)` / `get_weather(city)`(mock 数据即可)
  - 1 个 `@mcp.resource("data://greeting/{name}")` 返回 hello 字符串
  - 1 个 `@mcp.prompt("summarize")` 模板
  - `if __name__ == "__main__": mcp.run(transport="stdio")` 或 `"http"`
- **半成品版 `mcp_server_todo.py`**(学员补全用):留 4 处 `TODO`(装饰器空的、docstring 空的、参数类型空的、run() 调用空的)。
- **type-hint + docstring 两个正反对照**:
  - 反面:`def get_weather(city): return "sunny"` (无 type、无 docstring → 生成 schema 描述为空)
  - 正面:完整签名带 3 行 docstring,schema 描述丰满

**【数据 / 样例】**
- **验证 checklist**(五.5 讲师带学员逐条过):
  - [ ] `python mcp_server.py` 无报错启动
  - [ ] Inspector 里能 list 出 3 个 tool + 1 个 resource + 1 个 prompt
  - [ ] Call `add(2,3)` 返 5
  - [ ] Resource `data://greeting/Alice` 返 "hello Alice"
  - [ ] Prompt `summarize` 能拿到模板字符串

**【教学材料】**
- **schema 自动生成机制**图解:type-hint + docstring → FastMCP 反射 → JSON schema → 客户端拿到。
- **命名规范**:tool 名 snake_case、动词开头、≤ 3 词(便于 LLM 记住)。
- **常见坑**列表:
  1. 忘 `if __name__ == "__main__"` 直接跑 `mcp.run()` 导致重复启动
  2. `stdio` 版不能 print 到 stdout(会破坏协议),必须走 stderr 或 logger
  3. 参数用 `dict` 而非 Pydantic Model,schema 会太宽松

**【学员课前】**
- 已完成 L15 三原语选型练习,今天要把 3 个原语代码化。
- IDE 里已开好 `examples/hello-agent/` 项目,能创建新文件。

**【备用方案】**
- 若 FastMCP 版本大变(3.x → 4.x)API 有 break → 讲师课前锁版本 `pip install fastmcp==3.5.*`,或临时切官方 `mcp` 底层写法。
- 若 stdio 调试太抽象 → 直接用 `mcp.run(transport="http", port=8765)` 起 HTTP 版,用 curl / Postman 打接口,可视化更好。

### 五、教学过程

#### 1. 导入:从 @tool 到 @mcp.tool(5 min)

> 【讲师讲稿】"L9 我们写了自己的 `@tool` 装饰器,把工具注册到本地表。今天要把这个本地表'搬到外部',让任何 MCP host 都能用——这就是 MCP server。语法上几乎一样,但**功能上你的工具立刻获得了'任何兼容 host 都能调'的能力**。这是 MCP 的魔法。"

---

#### 2. FastMCP 三装饰器精讲(20 min)

讲师从空文件开始,逐行写完整 server:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo-server")

# ─── Tool ───
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers and return the sum.
    
    Use this when the user asks for arithmetic addition.
    Do NOT use this for floating point math (use `add_float` instead).
    """
    return a + b

# ─── Resource ───
@mcp.resource("greeting://{name}")
def greeting(name: str) -> str:
    """Return a personalized greeting for the given name."""
    return f"Hello, {name}! Welcome to MCP."

# ─── Prompt ───
@mcp.prompt()
def review_pr(diff: str) -> str:
    """Generate a code review prompt for the given diff."""
    return f"""Please review the following diff and give constructive feedback:

{diff}

Focus on:
- Correctness
- Readability
- Performance
- Potential bugs
"""

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**逐行讲解**:

- **`FastMCP("demo-server")`**:创建一个 server 实例,字符串是 server 的名字,会出现在 host 的 server 列表里。
- **`@mcp.tool()`**:把这个函数注册成 Tool。FastMCP 会:
  - 用 `function.__name__` 作为工具 name。
  - 用 **docstring 作为 description**(`add` 的多行 docstring 全部进去)。
  - 用 type hints + parameter names 自动生成 JSON Schema(`a: int, b: int` → `{"a":{"type":"integer"},...}`)。
- **`@mcp.resource("greeting://{name}")`**:注册资源。
  - URI 模板里的 `{name}` 是路径参数,会传给函数同名参数。
  - 客户端用 `resources/read` 时传完整 URI 如 `greeting://Alice`。
- **`@mcp.prompt()`**:注册 Prompt 模板。参数是用户在调用时填入的变量。

> 【讲师讲稿】"FastMCP 的设计哲学是'把 Python 函数变成 MCP 端点的最短路径'。**你只要按正常方式写函数 + 写 docstring + 加 type hints,装饰器帮你搞定所有协议细节**。这一点和 FastAPI 的设计完全一致——所谓"Fast"指的就是开发速度。"

---

#### 3. docstring 对比实验(20 min)

讲师准备两版同样的 server:

**A 版(详细 docstring)**:
```python
@mcp.tool()
def get_weather(city: str) -> str:
    """Get current weather for a given city.
    
    Use this tool whenever the user asks about today's weather,
    temperature, or sky conditions. Pass the city name in either
    English or Chinese (e.g., "Beijing" or "北京"). Returns a
    short text description.
    """
    ...
```

**B 版(单行 docstring)**:
```python
@mcp.tool()
def get_weather(city: str) -> str:
    """Get weather."""
    ...
```

两版都接入 Cursor,跑同样的 prompt "对比北京和上海今天天气"。**A 版**模型主动并行调两次,**B 版**模型经常选不上,可能直接编。

> 【讲师讲稿】"看见没?docstring 不是装饰品,是工具的'工作说明书',**直接决定 LLM 是否/何时选用你这个工具**。一个好的工具 docstring 应该回答 4 个问题:1) 它做什么?2) 何时该用?3) 何时**不**该用?4) 参数怎么填?把这 4 个写清,模型选用率会高很多。"

---

#### 4. 学员实操:写一个完整 server(50 min)

任务清单:

每人写一个 server,包含:
- **1 个 Tool**:`divide(a: float, b: float) -> str`,处理除零(返回 `"ERROR: division by zero"`)。
- **1 个 Resource**:`config://{key}` → 返回硬编码 dict 里 key 对应的值。
- **1 个 Prompt**:`/summarize` → 模板:"请用 100 字总结以下内容:{text}"。

**助教验收点**:
- 每个端点都有完整 docstring。
- 用 MCP Inspector 能看到三种端点。
- `divide` 调用 `(10, 0)` 不抛异常,返回错误字符串。

讲师中途巡视,提示常见错误:
- 忘了 `if __name__ == "__main__": mcp.run(...)`,导致直接 import 不启动。
- Resource 的 URI 模板和函数参数名不一致(必须同名)。
- docstring 写中文也可以,LLM 都能理解。

---

#### 5. 用 Inspector 调试 + 测查(20 min)

学员各自跑:
```bash
npx @modelcontextprotocol/inspector python your_server.py
```

确认:
- initialize 成功(显示 server 名)。
- tools 标签下能看到 `divide`,调用 `(10, 2)` 返回 `5`,调用 `(10, 0)` 返回错误字符串。
- resources 能读 `config://timeout`。
- prompts 能 get `summarize`,填入 `text`。

---

#### 6. 测查 + 小结 + 作业(5 min)

**作业**:把 M2 的工具 `now_time` / `get_weather` 迁移到 MCP Server,作为 L17 接入 Cursor 的素材。

### 六、板书设计
```
FastMCP("name")

@mcp.tool()           docstring → LLM 看到的 description
def fn(a:int)->int:    type hints → 自动生成 JSON Schema
    """..."""

@mcp.resource(uri)    URI 模板 + 同名参数
@mcp.prompt()         模板函数,返回最终 prompt 文本

if __name__ == "__main__":
    mcp.run(transport="stdio")   # 默认 stdio

调试:npx @modelcontextprotocol/inspector python server.py
docstring 4 问:做什么 / 何时该用 / 何时不该用 / 参数怎么填
```

### 七、课堂练习(完整发放版)

> 讲师提示:本节练习是"从零写一个完整 MCP server"。学员基于 L14/L15 环境,50-60 分钟完成 3 tool + 1 resource + 1 prompt 的完整实现,并用 Inspector 逐一验证。

#### 练习 1:完整 MCP server 实现(50 min,个人)

**任务**:创建 `mcp_server.py`,实现:
- **3 个 Tool**:`add(a,b) / now_time(timezone) / echo(text, prefix)`
- **1 个 Resource**:`data://users/{user_id}` 返回 mock 用户 profile
- **1 个 Prompt**:`code_review(code, style)` 返回 code review 请求模板

然后用 Inspector 逐一验证。

**验收 checklist**(每项都必须通过):

**A. 环境 & 启动**
- [ ] `pip install "mcp[cli]" fastmcp` 已装
- [ ] `python mcp_server.py` 无报错启动
- [ ] `npx @modelcontextprotocol/inspector python mcp_server.py` 能连上

**B. Tools 面板**
- [ ] 出现 3 个 tools:add / now_time / echo
- [ ] `add(3, 5)` 返回 8
- [ ] `now_time("Asia/Shanghai")` 返 ISO 时间
- [ ] `echo("hello", ">>>")` 返 `">>> hello"`

**C. Resources 面板**
- [ ] 出现 1 个 resource template:`data://users/{user_id}`
- [ ] `data://users/alice` 返 mock profile

**D. Prompts 面板**
- [ ] 出现 1 个 prompt:`code_review`
- [ ] 传参 `code="print(1)", style="严格"` 返回 render 后的模板文本

**E. 编码质量**
- [ ] 每个 tool/resource/prompt 都有 type-hint
- [ ] 每个都有 docstring(≥ 2 句,含 what/when)
- [ ] `mcp_server.py` 不超过 100 行

**参考答案**:

```python
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastmcp import FastMCP

mcp = FastMCP("demo-server")

# ============ Tools ============
@mcp.tool()
def add(a: int, b: int) -> int:
    """
    Add two integers and return the sum.
    Use for any arithmetic addition; do NOT compute in your head.
    Params: a, b (int).
    Returns: int sum.
    """
    return a + b

@mcp.tool()
def now_time(timezone: str = "UTC") -> str:
    """
    Get current time in ISO 8601 format for the specified IANA timezone.
    Use whenever the user asks 'what time is it' or 'now'.
    Params: timezone (IANA name like 'Asia/Shanghai', default 'UTC').
    Returns: ISO string like '2026-07-03T15:00:00+08:00'.
    """
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        return f"[ERROR] unknown timezone: {timezone}"
    return datetime.now(tz).isoformat(timespec="seconds")

@mcp.tool()
def echo(text: str, prefix: str = "") -> str:
    """
    Return the text (optionally prefixed).
    Use for simple echo/formatting tasks; do NOT use for translation.
    Params: text (required), prefix (optional).
    Returns: str.
    """
    return f"{prefix}{text}" if prefix else text

# ============ Resource ============
_MOCK_USERS = {
    "alice": {"name": "Alice", "role": "admin", "theme": "dark", "font_size": 14},
    "bob":   {"name": "Bob",   "role": "user",  "theme": "light", "font_size": 12},
}

@mcp.resource("data://users/{user_id}")
def user_profile(user_id: str) -> dict:
    """
    User profile by user_id. Read-only; used to fetch personal preferences.
    URI: data://users/{user_id}
    Returns: dict {name, role, theme, font_size} or {error: ...} if not found.
    """
    if user_id not in _MOCK_USERS:
        return {"error": f"user {user_id} not found"}
    return _MOCK_USERS[user_id]

# ============ Prompt ============
@mcp.prompt()
def code_review(code: str, style: str = "礼貌") -> str:
    """
    Generate a code review prompt template.
    Use when the user wants AI to review a snippet.
    Params: code (source code str), style ('礼貌' | '严格', default '礼貌').
    Returns: str prompt to feed to an LLM.
    """
    tone = "严格挑刺,不留情面" if style == "严格" else "礼貌建设性,先夸优点再提改进"
    return (
        f"你是一位资深工程师,请对下面代码做 review。风格:{tone}。\n"
        f"输出格式:\n"
        f"1. 优点(≤3 条)\n"
        f"2. 改进建议(≤5 条,按优先级)\n"
        f"3. 严重 bug(若无写'无')\n\n"
        f"代码:\n```\n{code}\n```"
    )

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**常见坑**:
- Resource URI `data://users/{user_id}` 少了斜杠或大括号名对不上 → Inspector 里看不到
- `mcp.run(transport="stdio")` 里如果 print 到 stdout(不加 `file=sys.stderr`)会污染协议 → 用 stderr 或 logger
- fastmcp 版本 3.x 与 4.x API 有变,课上锁 `fastmcp>=3.0,<4.0`
- 参数类型写 `dict` 而非 Pydantic Model → schema 太宽松,LLM 传参易出错

---

#### 练习 2:反面代码找 bug(10 min,个人)

**任务**:下面 server 代码看起来能跑,但有 4 个不足,找出并说明:

```python
from fastmcp import FastMCP
mcp = FastMCP("bad-server")

@mcp.tool()
def foo(a, b):
    return a + b

@mcp.resource("greeting")
def greeting():
    return "hello"

@mcp.prompt()
def analyze(text):
    return "analyze: " + text

mcp.run()
```

**参考答案**:

| # | 问题 | 后果 | 修法 |
| - | ---- | ---- | ---- |
| 1 | `foo(a, b)` 无 type-hint | schema 里参数类型未知,LLM 可能传字符串 | 加 `a: int, b: int -> int` |
| 2 | 全部函数无 docstring | LLM 拿不到用途说明,不会主动调 | 加 docstring(what/when/params/returns) |
| 3 | `resource("greeting")` 不是合法 URI | Inspector 里可能报错或不显示 | 改为 `"data://greeting"` |
| 4 | `mcp.run()` 无 transport 参数 | 默认可能是 stdio,但如果想 HTTP 需显式 | `mcp.run(transport="stdio")` 或 `transport="http"` |

**挑战延伸(选做)**:
- 加入 `list_users()` tool 返 `list[str]`(测多种返回类型)
- 加 `Field(..., description="...")` 用 pydantic Model 让 schema 更详细
- 用 `mcp.run(transport="http", port=8765)` 起 HTTP 版,curl 打接口验证

### 八、测查题与参考答案

1. FastMCP 在 MCP 生态里的作用?  A. 一个 MCP Host 实现  **B. Python 的高级 MCP Server 开发框架,用 `@mcp.tool()` 等装饰器快速声明工具/资源/prompt**  C. 用来压测 MCP server 的工具  D. 一个 MCP 协议解析器 → **B**。FastMCP 把 JSON-RPC、生命周期、schema 推断都封装好,让开发者只写业务函数。
2. MCP 官方推荐的本地调试工具是?  A. Postman  **B. MCP Inspector(`npx @modelcontextprotocol/inspector ...`,可视化 list/call 工具)**  C. curl  D. tcpdump → **B**。Inspector 能列出 tools/resources/prompts、可视化调用、查看 JSON-RPC 原始消息,是开发 Server 时的"必备调试器"。
3. 在 FastMCP 里 `@mcp.tool()` 装饰器会把函数注册为哪种原语?  A. Resource  **B. Tool**  C. Prompt  D. Sampling → **B**。对应关系:`@mcp.tool()`→ Tool,`@mcp.resource(uri)`→ Resource,`@mcp.prompt()`→ Prompt。
4. **简答**:为什么 docstring 很重要?
   - **参考答案**:docstring 会自动作为 tool description 暴露给 LLM,直接决定模型是否/何时选用。短或不清的 docstring 等于让模型瞎选。
5. **编程**:写 `divide(a, b)` MCP 工具处理除零。
   - **参考答案**:
     ```python
     @mcp.tool()
     def divide(a: float, b: float) -> str:
         """Divide a by b. Returns an error message if b is zero.
         
         Use this for floating point division. Do NOT use for integer
         division (use `floordiv` instead).
         """
         if b == 0:
             return "ERROR: division by zero"
         return str(a / b)
     ```

### 九、教学反思要点
- 学员的 server 是否都能被 Inspector 看到工具?未看到通常是 transport 错或 docstring/装饰器缺。
- docstring 对比实验非常震撼,务必保留。

---

## L17 — 在 Cursor / Claude Desktop 中接入 MCP Server

### 一、基本信息
- **课时编号**:L17
- **课时时长**:90 分钟
- **课型**:实操
- **前置**:L16
- **教具**:Cursor 或 Claude Desktop(已装)、提前生成的低权限 GitHub PAT。

### 二、教学目标
**知识目标**
- 写出符合规范的 `mcp.json` / `claude_desktop_config.json`。
- 列出 3 类最常见的接入配置坑:路径转义、PATH、环境变量。

**能力目标**
- 把 L16 写好的 server 接入 Cursor,在聊天中真实调用工具。
- server 红色未连接时,按系统化步骤排查到根因。

### 三、教学重点与难点
- **重点**:配置文件位置 + 重启 host 流程。
- **难点**:Windows 学员的路径与 PATH 问题。

### 四、教学准备

**【环境 / 依赖】**
- **Cursor** 或 **Claude Desktop** 已安装最新版(讲师建议 Cursor,因为 MCP 支持最完善)。
- Node 18+(GitHub MCP server 官方是 Node 版)。
- L16 的 `examples/hello-agent/mcp_server.py` 已跑通,能用 stdio 启动。
- **Cursor 配置文件路径**(讲师板书):
  - Windows: `%USERPROFILE%\.cursor\mcp.json`
  - macOS/Linux: `~/.cursor/mcp.json`
- **Claude Desktop 配置文件路径**:`%APPDATA%\Claude\claude_desktop_config.json`(Win) / `~/Library/Application Support/Claude/`(macOS)

**【代码素材】**
- **两份配置模板**(五.3、5.4 用):
  - **本地 Python server 模板**:
    ```json
    {
      "mcpServers": {
        "hello": {
          "command": "python",
          "args": ["C:/RyanLIU/.../examples/hello-agent/mcp_server.py"]
        }
      }
    }
    ```
  - **GitHub server 模板**(官方 `@modelcontextprotocol/server-github`):
    ```json
    {
      "mcpServers": {
        "github": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-github"],
          "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"}
        }
      }
    }
    ```

**【数据 / 样例】**
- **低权限 GitHub PAT**(讲师课前生成):**只授 `public_repo` 或 fine-grained 只读**,过期时间 ≤ 7 天,防误上仓库。
  - **强调**:课上千万别用讲师私人 PAT 或高权限 token 做演示,截屏一旦泄露风险极大。**每人自己生成自己的**。
- **验证 3 步**:
  1. Cursor `Settings → MCP`,看服务列表出现 `hello` 或 `github`,状态绿灯
  2. 新聊天里输入 "现在几点?" → 触发本地 `now_time` tool
  3. 输入 "列出我 star 的仓库" → 触发 github tool

**【教学材料】**
- **常见 4 类配置错误** cheat sheet:
  1. path 反斜杠没转义(Windows `C:\\...` 或 `/`)
  2. python 用系统 python 而非 venv 的(找不到 fastmcp)
  3. args 数组少括号变成字符串
  4. env 里 PAT 有多余引号
- **safety 提示**:PAT 一律走 `env` 而非 hard-code 到脚本;`.cursor/mcp.json` 加入 `.gitignore`。

**【学员课前】**
- 已在 GitHub Settings → Developer settings 会生成 fine-grained PAT(懂如何限权限、限时长)。
- Cursor / Claude Desktop 已经能正常聊天(基本使用无障碍)。

**【备用方案】**
- 若 Cursor 版本不支持 MCP → fallback Claude Desktop(macOS/Win 都有原生 MCP 支持)。
- 若学员的 GitHub 账号没 admin 权限生成 PAT(公司账号锁定) → 用讲师提供的**只读 sample repo demo 账号**,或跳过 github server 只演示本地 server。
- 若 npx 网络不通 → 讲师本地提前 `npm install -g @modelcontextprotocol/server-github`,配置改 `"command": "server-github"`。

### 五、教学过程

#### 1. 导入(5 min)

让一位学员描述自己 L16 server 的绝对路径,讲师把它写进 Cursor 配置示范。

> 【讲师讲稿】"L16 我们写好了 MCP server,L14 用 Inspector 验证了它能跑。今天要让它**真的为 Cursor 服务**——你聊天问'2 + 3 等于几',Cursor 调你的 server。这一步打通后,你写的每个工具都立刻被 Cursor 的所有 AI 能力复用,这就是 MCP 的兑现时刻。"

---

#### 2. 配置文件结构(15 min)

**Cursor**:`.cursor/mcp.json`(项目级,推荐)或 `~/.cursor/mcp.json`(全局)。

```json
{
  "mcpServers": {
    "demo": {
      "command": "python",
      "args": ["C:\\Users\\me\\projects\\hello-agent\\mcp_server.py"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxxx"
      }
    }
  }
}
```

**Claude Desktop**:`claude_desktop_config.json`,结构基本一致。

**逐字段讲**:
- **`mcpServers`**:顶层 key,固定写法。
- **server key**(如 `"demo"`):这是 host 内部对 server 的标识,**可以随便起,但建议简短**。
- **`command`**:启动 server 的命令。必须能在系统 PATH 找到——常见值:`python`、`npx`、`node`、`uvx`(uv 风格)。
- **`args`**:命令行参数数组,每项一个字符串。
- **`env`**:传给 server 进程的环境变量,**敏感信息从这里走**,不要硬编码到 args。

**Windows 路径注意**:
- JSON 字符串里 `\` 要写成 `\\`(转义),或者用正斜杠 `/`(Windows Python 也认)。
- 路径**必须绝对路径**(host 启动 server 时的工作目录不可预期)。

> 【讲师讲稿】"我每个班都看到 Windows 学员栽在路径上——要么忘了双反斜杠,要么用了相对路径。请大家记住:**Windows 路径,在 JSON 里要么 `\\\\`(原文里两个反斜杠),要么 `/`,绝对路径**。这三个条件齐了才稳。"

---

#### 3. 学员实操:接入 Cursor(40 min)

**步骤**:
1. 创建项目级 `.cursor/mcp.json`,写入 demo server 配置(用自己 L16 的绝对路径)。
2. **完全退出 Cursor**(右键托盘 → Quit,不只是关窗口)。
3. 重新打开 Cursor。
4. 打开 Settings → MCP 标签 → 看自己的 server 是否**绿色**。
5. 在 chat 输入 "用 add 工具算 5+8",看是否触发工具调用。

**助教逐桌检查**,常见问题:
- 没"完全退出"——Windows 任务管理器看是不是有 Cursor 进程残留。
- 路径有 `\`(单)。
- Python 不在 PATH(尤其是 venv 里的 Python)。

---

#### 4. 故障排查训练:系统化口诀(15 min)

讲师故意制造 3 种错误让学员排查:

**(1) 错路径**:把 args 里改成 `xxxxx.py`(故意拼错)。
- **排查**:打开 Cursor 的 MCP 日志面板,看 server 启动报错信息。

**(2) 漏 env**:GitHub server 不传 `GITHUB_PERSONAL_ACCESS_TOKEN`。
- **排查**:server 能启动但 `tools/list` 失败或工具调用报 401。

**(3) PATH 问题**:`command: "python3"` 但 Windows 只有 `python`。
- **排查**:本地命令行试 `python3 --version`,看是不是"未找到命令"。

**排查口诀**(讲师板书):

```
故障排查 4 步:
  1) 看 host 的 MCP 日志(Cursor: Settings → MCP → 点 server 看 Output)
  2) 命令行单独跑 command + args,看是否报错
  3) 用 MCP Inspector 连同样配置,看是否成功
  4) 检查 env 是否齐全
```

> 【讲师讲稿】"碰到 server 红色,不要瞎试,按这 4 步走。**90% 的问题在第 1 步就能看出来**——host 的 MCP 日志会告诉你 server 进程是直接没起来(命令错),还是起来后 initialize 失败(协议错),还是 initialize 成功但 tools 调用失败(权限错)。"

---

#### 5. 测查 + 小结(10 min)

**测查(7 min)**:投影第八节 3 道选择题,**学员举手抢答**(30 秒思考),公布答案后讲师针对每题陷阱**点 1 句**——尤其第 3 题"Windows 路径反斜杠转义"是 Windows 学员最常踩的坑,务必现场让 Windows 学员举手记下。简答与场景题作为课后练习,讲师可在下节课开场抽 1 人复述"server 红色 4 步排查法"。

**小结(3 min)**:讲师投影 "今天必须带走的 3 句话":

> **今天必须带走的 3 句话**:
> 1. **Cursor 配置首选项目级 `.cursor/mcp.json`**(可入 Git 团队共享),含密钥的部分用 `.env` 引用;用户级 `~/.cursor/mcp.json` 适合个人通用工具。
> 2. **配置改完必须重启 Host**——大多数 Host 没有热加载,改了不重启就"以为生效"是高频踩坑。
> 3. **server 红色排查 4 步法**:① 看 host MCP 日志 → ② 命令行单独跑 command+args → ③ 检查 env / Token / PATH → ④ 用 Inspector 单独验证 server。

> 【讲师讲稿】"今天讲的是'怎么用',下节课 L18 我们要把今天学的全部用起来——把 GitHub MCP Server 集成进自己的 Agent,让 Agent 能自动列 issue、拉 PR、做摘要。这是 M3 的里程碑作业,务必把今天的作业 GitHub MCP 接入做完。"

#### 6. 作业(5 min)
- 把 GitHub MCP Server 接入自己的 Cursor,演示一次"列出我的 repo"。

**参考答案(完整步骤)**:

**Step 1**:在 GitHub 创建一个 Fine-grained Personal Access Token
- 打开 https://github.com/settings/tokens?type=beta
- 给 token 起名 `cursor-mcp-readonly`,选 `Read-only` 类权限(列 repo 只需 `metadata: read`)
- 复制 token,下面要用

**Step 2**:在 Cursor 配置 MCP server(项目级 `.cursor/mcp.json` 或全局 `~/.cursor/mcp.json`)

```jsonc
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "github_pat_11AABBCC..."
      }
    }
  }
}
```

**Step 3**:重启 Cursor → 打开 Composer/Agent → 应能看到 `github` MCP server 列出的工具(`list_my_repos`、`search_repositories`、`get_issue` 等)。

**Step 4**:在对话框输入:

```
列出我的所有 GitHub repo,按 star 数倒序,显示前 5 个的名字和 star 数。
```

Cursor Agent 应该:① 调 `list_my_repos`;② 用 LLM 排序;③ 返回类似:

```
1. ryanliu/awesome-agents     ★ 1200
2. ryanliu/llm-course         ★ 800
3. ryanliu/mcp-playground     ★ 350
4. ...
```

**评分要点**:
1. **token 用 fine-grained + readonly**(不能用 classic 全权限 token——这是 production 安全底线);
2. `.env` 文件 / `mcp.json` 都**不能 commit 到 GitHub**(把 `.cursor/mcp.json` 加进 `.gitignore`,或用 env 变量替换);
3. 演示截图含 Cursor 的 MCP tool list 与至少 1 次成功调用;
4. **常见错误**:把 token 直接 commit,1 分钟内会被 GitHub Secret Scanning 自动 revoke + 邮件警告。

**安全延伸**:生产场景永远用 fine-grained token 给到**最小权限**;轮换周期 ≤ 90 天;不同 MCP server 用不同 token,便于审计单一 server 的访问范围。

### 六、板书设计
```
.cursor/mcp.json
{
  "mcpServers": {
    "demo": {
      "command": "python",
      "args": ["C:\\path\\to\\server.py"]   ← 绝对路径,Windows 用 \\
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..."}
    }
  }
}

排查 4 步:
  1) host MCP 日志
  2) 命令行单独跑 command+args
  3) MCP Inspector 验证
  4) env 检查
```

### 七、课堂练习(完整发放版)

> 讲师提示:本节练习是"把自己写的 MCP server 接到 Cursor 或 Claude Desktop",端到端验证宿主侧集成。学员需 Cursor / Claude Desktop 已装,Node 18+。总时长 40-50 分钟。

#### 练习 1:接入自家 MCP server 到 Cursor(25 min,个人)

**任务**:把 L16 的 `mcp_server.py` 接入 Cursor,在 Cursor 聊天里让 AI 主动调用 `now_time` 工具。

**Step 1:定位 Cursor 配置文件**

- Windows: `%USERPROFILE%\.cursor\mcp.json`(约 `C:\Users\<你>\.cursor\mcp.json`)
- macOS/Linux: `~/.cursor/mcp.json`

若文件不存在,新建即可。

**Step 2:填配置**

```json
{
  "mcpServers": {
    "demo-local": {
      "command": "C:/RyanLIU/.../examples/hello-agent/.venv/Scripts/python.exe",
      "args": ["C:/RyanLIU/.../examples/hello-agent/mcp_server.py"]
    }
  }
}
```

**重点**:
- `command` **必须**是 venv 里的 python(否则找不到 fastmcp)
- `args` 里路径用**正斜杠 `/`** 或 **双反斜杠 `\\`**,不要单反斜杠
- macOS/Linux 用绝对路径 `/Users/xxx/.../python`

**Step 3:重启 Cursor**

完全退出(不是关窗口)再打开;`Settings → MCP` 应看到 `demo-local` 状态为 🟢 绿灯。

**Step 4:在聊天里触发**

新开 chat,输入:
```
现在几点?请用工具查,不要靠猜。
```

预期:Cursor 弹出 "MCP tool: demo-local.now_time 是否允许?" → 允许后返回 ISO 时间。

**验收 checklist**:
- [ ] `mcp.json` 里 `demo-local` 显示 🟢 状态
- [ ] Tools 面板列出 `now_time / add / echo` 3 个
- [ ] 聊天成功触发 `now_time` 返回时间
- [ ] Resources 面板出现 `data://users/{user_id}`(可点开)
- [ ] Prompts 面板 slash command 里出现 `code_review`

---

#### 练习 2:故障排查演练(15 min,个人)

**任务**:讲师故意构造 4 种常见故障配置,学员**看到 Cursor 里状态红灯 or 报错**后,诊断 + 修复。

**故障 A**:配置文件语法错(JSON 末尾多逗号)
```json
{
  "mcpServers": {
    "demo": { "command":"python", "args":["mcp_server.py"] },
  }
}
```

**故障 B**:python 用系统 python 而非 venv
```json
{"mcpServers":{"demo":{"command":"python","args":["mcp_server.py"]}}}
```

**故障 C**:路径反斜杠没转义(Windows 单斜杠)
```json
{"mcpServers":{"demo":{"command":"C:\python.exe","args":["C:\proj\mcp_server.py"]}}}
```

**故障 D**:env 里 PAT 有多余引号
```json
{"mcpServers":{"github":{"command":"npx","args":["-y","@modelcontextprotocol/server-github"],"env":{"GITHUB_PERSONAL_ACCESS_TOKEN":"'ghp_xxx'"}}}}
```

**诊断表**(学员填):

| 故障 | 症状 | 原因 | 修法 |
| ---- | ---- | ---- | ---- |
| A | | | |
| B | | | |
| C | | | |
| D | | | |

**参考答案**:

| 故障 | 症状 | 原因 | 修法 |
| ---- | ---- | ---- | ---- |
| A | Cursor Settings → MCP 全部消失 or 红灯 | JSON 末尾多逗号,标准 JSON 不允许 | 去掉最后一个 `,` |
| B | 状态红灯,error 包含 `No module named 'fastmcp'` | 系统 python 没装 fastmcp | 改为 venv 里 python 绝对路径 |
| C | 状态红灯 or "path not found" | Windows JSON 里 `\` 是转义符,`\p` `\r` 是 unknown escape | 用 `/` 或 `\\` |
| D | GitHub server 报 401 | PAT 前后带了引号,变成非法 token | 去掉多余引号 |

**排查系统化口诀**(讲师板书):
```
1. mcp.json 是不是合法 JSON?→ VS Code / jsonlint 验一下
2. command 里的可执行程序能不能直接跑?→ 复制粘贴到终端跑
3. args 里的路径存在吗?→ ls / dir 确认
4. env 里 secret 有没有多余引号/空格?→ 复制到终端 echo 出来看
5. 装的包是否在正确的 venv?→ python -c "import fastmcp"
```

**验收 checklist**:
- [ ] 4 种故障全部诊断并给出修法
- [ ] 能说出"如果状态红灯先查什么"的 5 步排查口诀

**挑战延伸(选做)**:
- 接入官方 `@modelcontextprotocol/server-filesystem` 让 Cursor 能读你本地某目录
- 接入 GitHub server(需 fine-grained PAT 只读权限)让 Cursor 能读你的 star 列表
- 同时接入 3 个 MCP server(本地 demo + filesystem + github),Cursor 里能列出**所有 tools 汇总**

### 八、测查题与参考答案

1. Cursor 中 MCP 配置文件的标准位置?  A. `~/.cursor.json`  **B. 项目级 `.cursor/mcp.json`(或用户级 `~/.cursor/mcp.json`)**  C. `package.json`  D. `mcp.toml` → **B**。项目级配置更推荐:可随项目入 Git,team 成员开箱即用;含密钥的部分用 `.env` 引用。
2. 修改 MCP 配置文件后,通常需要做什么才会生效?  A. 等待自动 reload  **B. 重启 Host(Cursor / Claude Desktop)**  C. 执行 `mcp reload`  D. 重新登录 → **B**。Host 只在启动时读 mcp.json,大多数 Host 没有热加载;改完务必完整退出并重启。
3. Windows 上配置 MCP 路径最常见的错误是?  A. 必须用相对路径  **B. 没用绝对路径,或反斜杠没转义(`C:\foo` 应写成 `C:\\foo` 或 `C:/foo`)**  C. 必须用单引号  D. 路径长度限 8 字符 → **B**。JSON 里 `\` 是转义符,Windows 路径要么双反斜杠,要么改用正斜杠;否则 host 启动 server 时会找不到文件。
4. **简答**:server 红色未连接,排查顺序?
   - **参考答案**:① 看 host MCP 日志;② 命令行单独跑 command + args 看是否报错;③ 检查 env / API key;④ 用 MCP Inspector 单独测;⑤ 看 Python/依赖是否在 PATH。
5. **场景**:配了 github,模型不主动调,只回答文字。
   - **参考答案**:① system prompt 没引导用 GitHub 工具;② 工具描述太短模型选不准;③ Token 权限不足致工具失败被模型忽略;④ Host 未把工具 schema 真正暴露给模型(在调试面板确认 tools/list 返回有工具)。

### 九、教学反思要点
- Windows 与 macOS 学员的卡壳点差异明显,可以分组帮扶。
- "排查 4 步" 是非常珍贵的工程经验,务必让学员抄下来。

---

## L18 — 实战:GitHub Issues Agent(对应 `examples/hello-agent/issues_agent.py`)

### 一、基本信息
- **课时编号**:L18
- **课时时长**:120 分钟(实战课加长)
- **课型**:综合实战
- **前置**:M2 + L13–L17
- **配套代码**:`examples/hello-agent/issues_agent.py`(参考实现)。

### 二、教学目标
**知识目标**
- 把 M2 的 Agent 改造为"LLM + MCP Client + GitHub MCP Server"架构。
- 解释 MCP tool schema 如何转换为 OpenAI tool 格式。

**能力目标**
- 独立交付一个能列出最近 issue、生成 Markdown 摘要的 Agent。
- 跑通最少 1 个真实 repo 的端到端任务。

### 三、教学重点与难点
- **重点**:MCP Client SDK 的会话使用(`session.initialize / list_tools / call_tool`)。
- **难点**:把 MCP tool schema 转成 OpenAI `tools` 数组并把 call 转发回 session。

### 四、教学准备

**【环境 / 依赖】**
- **必装包**:`pip install "mcp[cli]" openai python-dotenv httpx-sse`(注意 mcp 客户端库跟 server 端一起装 `mcp[cli]` 即可)。
- Node 18+(GitHub MCP server 依赖)。
- **`.env` 追加**:`GITHUB_TOKEN=ghp_xxx`(每人自己的 fine-grained PAT,只授 `public_repo` 或指定仓库 read)。
- 讲师本地已跑通完整 `issues_agent.py`(不发学员,仅课末对照)。

**【代码素材】**
- **`issues_agent.py` 参考实现**(讲师本地保存,约 80 行)结构:
  1. `load_dotenv()` 载环境
  2. `mcp.client.session.ClientSession` 通过 `stdio_client` 连接 GitHub MCP server 子进程
  3. `await session.list_tools()` 拉工具清单
  4. **schema 转换**:MCP tool 的 `inputSchema` → OpenAI `tools[i].function.parameters`
  5. 主循环:LLM 返 tool_calls → `await session.call_tool(name, args)` 转发 → 拿到 content 作为 `role="tool"` 消息回填
  6. `max_steps=8` 兜底
- **半成品 `issues_agent_todo.py`**(学员补全,4 处 TODO):MCP session 建立、schema 转换、call_tool 转发、结果回填。
- **schema 转换单元测试**:1 段 20 行的 `assert convert(mcp_schema) == openai_schema`,给学员对齐用。

**【数据 / 样例】**
- **5 个测试 prompt**(五.5 演示):
  1. `"列出 langchain-ai/langgraph 仓库最新 3 个 issue 的标题"` — 简单一次 tool
  2. `"其中哪个 issue 最近有更新?"` — 多次 tool + reasoning
  3. `"给最新那个 issue 加 comment '收到,处理中'"` — **应被拒**(PAT 只读)
  4. `"帮我 star 这个仓库"` — **应被拒**(权限外)
  5. `"这个仓库的 README 前 100 字说了什么?"` — resource 读取
- **MCP tool schema 样本**(讲师课前用 Inspector 抓):`{"name": "get_issues", "inputSchema": {"type":"object", ...}}`,让学员看真实结构。

**【教学材料】**
- **schema 转换 3 要点**板书:
  1. MCP `inputSchema` 就是 JSON Schema,原样搬到 OpenAI `function.parameters` 大部分能用
  2. MCP tool `name` 有时含 `.` 或 `/`,OpenAI 要求 `^[a-zA-Z0-9_-]+$` → 需 sanitize
  3. `description` 若为空,LLM 无法选 → 补 fallback "调用 MCP 工具 {name}"
- **架构对比图**(五.2):自家 tool(进程内)vs MCP tool(跨进程 RPC),延迟从 μs 变 ms 但获得复用。

**【学员课前】**
- 已在 L17 让 Cursor 调通 github MCP server(即 Host 侧已验证)。
- 熟悉 L11 的 wrap_tool 模式,今天要把 wrap 从"包本地 fn"扩到"包远程 RPC 调用"(超时更长、错误更多)。

**【备用方案】**
- 若 GitHub API 全局 rate limit 触发(未授权 60/h,授权 5000/h) → 讲师提供**本地 mock MCP server** 直接返固定 issues JSON,教学不受限。
- 若 stdio 连接一直挂 → 改用 HTTP transport 的 GitHub MCP server,或降级到讲师本地已跑通的 `filesystem` MCP server 做端到端演示。

### 五、教学过程

#### 1. 项目目标 + 架构(15 min)

**输入**:`repo = "owner/name"`。
**输出**:近 10 个 open issue 的标题 + 简要摘要 Markdown,保存为 `report.md`。

**架构图**:
```
User → Agent (LLM 决策)
              │
              │ OpenAI function calling 接口
              ▼
       ┌──────────────┐
       │ MCP Client   │ ──(JSON-RPC over stdio)──▶ github-mcp-server
       │  in Python   │                                  │
       └──────────────┘                                  ▼
                                                   GitHub REST API
```

> 【讲师讲稿】"今天的核心要点:**LLM 不直接调 GitHub API**——它通过我们的代码,代码通过 MCP Client,MCP Client 通过 stdio,启动并通信 github MCP server,server 才最终调 GitHub。一层又一层,看起来繁琐,但每层都有它的解耦价值:LLM 不知道 GitHub 的存在,只知道 MCP 工具;MCP server 不知道 LLM 的存在,只知道 GitHub。**这种解耦让我们可以单独替换任何一层**。"

---

#### 2. MCP Client SDK 关键 API(20 min)

讲师在白板写最小代码:

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os

async def demo():
    # 1. 描述如何启动 server(作为子进程)
    params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": os.environ["GITHUB_TOKEN"]},
    )
    
    # 2. 启动 server,拿到 stdin/stdout 流
    async with stdio_client(params) as (read, write):
        # 3. 在流上建立 MCP session
        async with ClientSession(read, write) as session:
            # 4. initialize + 拿能力
            await session.initialize()
            
            # 5. 列工具
            tools = await session.list_tools()
            print("Available tools:", [t.name for t in tools.tools])
            
            # 6. 调用一个工具
            result = await session.call_tool("list_issues",
                arguments={"owner": "openai", "repo": "openai-python", "state": "open"})
            print(result.content)

asyncio.run(demo())
```

**逐部分讲**:
- `StdioServerParameters`:**描述符**,告诉 Client "怎么启动 server"——和 mcp.json 里的 server 配置一一对应。
- `stdio_client(params)`:**实际启动**子进程,返回 (read, write) 两个异步流。
- `ClientSession(read, write)`:在两个流之上封装 JSON-RPC 会话。
- `session.initialize()`:**必须**先调,完成 L14 讲的握手 + capabilities 交换。
- `session.list_tools()`:返回所有可用工具,每个工具有 `name / description / inputSchema`。
- `session.call_tool(name, arguments=dict)`:调用工具,返回带 `content` 字段的结果对象。

> 【讲师讲稿】"注意 SDK 是异步的(`async`/`await`),如果你的 Agent 主循环还是同步的,得用 `asyncio.run` 包一下。这也是为什么 L10 我们讲了 asyncio,今天直接派上用场。"

---

#### 3. Schema 转换:MCP tool → OpenAI tool(15 min)

**MCP 的 tool 长这样**(`list_tools` 返回):
```python
Tool(
    name="list_issues",
    description="List issues in a repository.",
    inputSchema={
        "type": "object",
        "properties": {
            "owner": {"type": "string"},
            "repo": {"type": "string"},
            "state": {"type": "string", "enum": ["open","closed","all"]},
        },
        "required": ["owner", "repo"],
    },
)
```

**OpenAI 需要这样**:
```python
{
    "type": "function",
    "function": {
        "name": "list_issues",
        "description": "List issues in a repository.",
        "parameters": {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    }
}
```

**转换函数**:
```python
def mcp_tool_to_openai(t):
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.inputSchema,
        }
    }
```

> 【讲师讲稿】"这就是 MCP 和 function calling 的'胶水层'——一个小转换函数,把两端的格式对齐。**字段几乎一一对应**,只是嵌套层级不同。理解这个,你就明白为什么 MCP 协议被设计成跟主流 function calling 兼容——降低生态接入成本。"

---

#### 4. 学员实现(50 min)

讲师给半成品 `issues_agent.py` 骨架,留 4 处 `TODO`:

```python
# TODO 1: 在 stdio_client + ClientSession 内
async def setup(session):
    await session.initialize()
    tools = await session.list_tools()
    oai_tools = [mcp_tool_to_openai(t) for t in tools.tools]
    return oai_tools

# TODO 2: 主循环
async def run_agent(session, oai_tools, goal):
    messages = [{"role":"system", "content": SYSTEM},
                {"role":"user",   "content": goal}]
    for step in range(10):
        # 说明:这里用同步 client.chat.completions.create 为简化演示;
        # 它会短暂阻塞 event loop,demo 可接受。生产请改用 AsyncOpenAI:
        #   from openai import AsyncOpenAI
        #   client = AsyncOpenAI()
        #   resp = await client.chat.completions.create(...)
        resp = client.chat.completions.create(
            model="gpt-4.1", messages=messages, tools=oai_tools)
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content
        # TODO 3: 把 tool_calls 转发到 session.call_tool
        for call in msg.tool_calls:
            try:
                args = json.loads(call.function.arguments)
                result = await session.call_tool(call.function.name, args)
                content = "\n".join(c.text for c in result.content)
            except Exception as e:
                content = f"ERROR: {e}"
            messages.append({
                "role":"tool", "tool_call_id":call.id, "content":content
            })

# TODO 4: 把回复写到 report.md
async def main():
    params = StdioServerParameters(...)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            oai_tools = await setup(session)
            answer = await run_agent(session, oai_tools,
                "列出 owner/repo 最近 10 个 open issue,按 label 分组写一份 Markdown 简报")
            with open("report.md", "w", encoding="utf-8") as f:
                f.write(answer)
```

**互相替换 repo 名测试**,确保跑通一个真实 repo。

---

#### 5. 互验 + 答疑 + 测查(15 min)

**互验(5 min)**:同桌两两交换运行对方代码,验证能跑通"列 issue → 摘要"的端到端流程。

**答疑 + 标杆 review(5 min)**:讲师挑 1 份"非常工程化"的实现(有 retry、有 trace 打印、有错误恢复)公开 review,作为标杆。重点点评:①schema 双向转换是否清晰;② tool_calls 转发是否一一对应;③ 错误处理是否包了 stdio_client 上下文。

**测查 + 小结(5 min)**:
- 投影第八节 3 道选择题,**学员举手抢答**(20 秒思考),公布答案后讲师针对每题陷阱**点 1 句**——尤其第 3 题 "schema 双向转换 + 调用转发"是 Agent ↔ MCP 桥接的核心,务必让学员手指代码里对应那两段。

**M3 收官 — 今天必须带走的 3 句话**:

> 1. **schema 双向转换是 Agent ↔ MCP 桥接的核心**——MCP 工具 schema → OpenAI tool schema 喂 LLM;LLM 返回 tool_calls → 反向转发到 MCP session 的 `call_tool`。
> 2. **LLM 永远只负责决策与合成,工具执行在 MCP Server**——这就是 L13 讲的"N+M 解耦"在代码层的具体形态。
> 3. **本项目是 M3 的里程碑标杆**——M4 加持久化记忆 / M6 加 trace 与 eval 都将在这个项目上演进,**请把代码留好不要删**。

> 【讲师讲稿】"M3 到此结束。我们今天把 Agent 的'工具层'从 L9 的硬编码 function calling 升级到了 MCP 的'即插即用'。下节课 M4 进入 Agent 的'记忆层'——让 Agent 跨进程、跨会话记住用户。每周一次的 conversation 突然能续上,就是记忆带来的产品体验飞跃。"

### 六、板书设计
```
async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as s:
        await s.initialize()
        mcp_tools = await s.list_tools()
        oai_tools = [to_openai(t) for t in mcp_tools]
        
        for step in range(max_steps):
            msg = llm(messages, tools=oai_tools)
            messages.append(msg)
            if not msg.tool_calls: return msg.content
            for call in msg.tool_calls:
                result = await s.call_tool(call.function.name,
                                            json.loads(call.function.arguments))
                append(role=tool, tool_call_id=call.id,
                       content=text_of(result.content))
```

### 七、课堂练习(完整发放版)

> 讲师提示:L18 整节课都是**Agent-side 集成练习**——从 Python 里做 MCP client,把 MCP tools 转成 OpenAI 兼容 schema 喂 LLM,完成 issues_agent.py。总时长 60-90 分钟,学员机需 `pip install "mcp[cli]" openai python-dotenv`,`.env` 里配 `GITHUB_TOKEN`(fine-grained PAT 只读)。

#### 练习 1:从零实现 `issues_agent.py`(60 min,个人)

**任务**:实现一个命令行 Agent,用户输入自然语言问题,Agent 调用 GitHub MCP server 的 tools 完成回答。

**验收场景**(5 个测试 prompt):

| # | prompt | 期望行为 |
| - | ------ | -------- |
| 1 | `"列出 langchain-ai/langgraph 仓库最新 3 个 issue 标题"` | 1 步 tool → final |
| 2 | `"其中哪个 issue 最近有更新?"` | 结合上下文回答 |
| 3 | `"给这个 issue 加 comment 'hi'"` | **应被拒**(PAT 只读) |
| 4 | `"这个仓库的 README 前 200 字说了什么"` | 触发 get_file_contents tool |
| 5 | `"我 star 过哪些仓库?"` | 触发 list starred |

**骨架代码 `issues_agent.py`**:

```python
import asyncio, json, os, re
from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()
llm = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL") or None,
)
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

# ============ TODO 1:定义 GitHub MCP server 启动参数 ============
server_params = StdioServerParameters(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-github"],
    env={"GITHUB_PERSONAL_ACCESS_TOKEN": GITHUB_TOKEN},
)

# ============ TODO 2:schema 转换 ============
def sanitize_name(name: str) -> str:
    """MCP tool name 有时含 '.' 或 '/',OpenAI 要求 ^[a-zA-Z0-9_-]+$"""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)

def mcp_tool_to_openai(mcp_tool) -> dict:
    """把 MCP tool 转成 OpenAI function calling schema"""
    return {
        "type": "function",
        "function": {
            "name": sanitize_name(mcp_tool.name),
            "description": mcp_tool.description or f"MCP tool {mcp_tool.name}",
            "parameters": mcp_tool.inputSchema or {"type":"object","properties":{}},
        },
    }

async def run(user_input: str, max_steps: int = 8) -> str:
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_resp = await session.list_tools()
            # 建立 sanitized name → original name 映射(call 时要还原)
            name_map = {sanitize_name(t.name): t.name for t in tools_resp.tools}
            openai_tools = [mcp_tool_to_openai(t) for t in tools_resp.tools]

            messages = [
                {"role":"system", "content":
                    "You are a GitHub assistant. Use the provided MCP tools to answer. "
                    "If a request needs write access (comment/star/close) but tools are read-only, refuse politely."},
                {"role":"user", "content":user_input},
            ]

            for step in range(max_steps):
                resp = await llm.chat.completions.create(
                    model=MODEL, messages=messages, tools=openai_tools,
                )
                msg = resp.choices[0].message
                messages.append(msg)
                if not msg.tool_calls:
                    return msg.content

                # TODO 3:遍历 tool_calls,调 session.call_tool,回填
                for call in msg.tool_calls:
                    original_name = name_map[call.function.name]
                    try:
                        args = json.loads(call.function.arguments)
                        result = await session.call_tool(original_name, args)
                        # result.content 是 list[TextContent],取拼接
                        text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
                    except Exception as e:
                        text = f"[ERROR] {type(e).__name__}: {e}"
                    print(f"  step {step+1}: {original_name}({call.function.arguments[:80]}) → {text[:80]}")
                    messages.append({
                        "role":"tool",
                        "tool_call_id":call.id,
                        "content":text[:4000],       # 截断防止过长
                    })
            return "[max_steps exceeded]"

if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) or "列出 langchain-ai/langgraph 仓库最新 3 个 issue 标题"
    print(asyncio.run(run(query)))
```

**验收 checklist**:
- [ ] 5 个测试 prompt 依次跑,行为符合期望
- [ ] Prompt 3 被拒绝(不是编造成功)
- [ ] 每步打印 `(tool_name, args, result_preview)` 便于观察
- [ ] tool 抛异常时不整体崩,回填 `[ERROR]` 后继续
- [ ] name_map 正确处理"MCP 原名有 `.` 或 `/`"的场景

---

#### 练习 2:tool result 长度截断(10 min,个人)

**任务**:MCP tool(如 GitHub 的 get_file_contents)有时返回**几万字**内容(整个 README),直接塞进 messages 会:
1. 爆上下文
2. 成本飙升
3. 后续 LLM 决策被淹没

**要求**:在骨架代码基础上加入 **result 截断策略**:
- 超过 2000 字符自动截断,末尾加 `...[truncated, X chars total]`
- 提供参数让用户可调阈值

**参考答案**:
```python
MAX_TOOL_RESULT = int(os.getenv("MAX_TOOL_RESULT_CHARS", "2000"))

def truncate(text: str, max_chars: int = MAX_TOOL_RESULT) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...[truncated, {len(text)} chars total]"

# 在回填之前
messages.append({"role":"tool", "tool_call_id":call.id, "content": truncate(text)})
```

**验收**:
- [ ] Prompt 4 拉 langgraph README(通常上万字),观察消息长度被截断到 2000+
- [ ] 后续 LLM 仍能给合理摘要

**常见坑**:
- 直接不截 → 单次调用 tokens 爆 → 花钱慢且可能触发上下文上限
- 截太狠(500 字符)→ LLM 拿不到足够信息 → 编造
- 截断后忘加"...[truncated]" 标记 → LLM 以为是完整文本

**挑战延伸(选做)**:
- 加入 **摘要式截断**:超过 2000 字符时,不硬截,而是**再调一次 LLM** 把长内容摘要成 500 字
- 加入 tool 结果缓存(hashlib 计算 args hash),5 min 内同参数直接返缓存
- 让 Agent 支持 **多个 MCP server 同时接入**(GitHub + filesystem + demo-local),tool 汇总后一起喂 LLM

### 八、测查题与参考答案

1. 本项目(MCP + Agent 整合)里 LLM 的职责是?  A. 直接调 GitHub REST API  **B. 决定调用哪些 MCP 工具(list_issues / list_comments 等),并基于工具结果生成摘要**  C. 仅做翻译  D. 负责存储数据库 → **B**。LLM 永远只决策和合成;真正执行工具的是 MCP Server,Agent 是中间的"调度 + 转发"。
2. 把 GitHub 集成做成 MCP Server,相比直接在 Agent 里写 SDK 调用的最大价值?  **A. 解耦——同一 Server 可被任意 Agent / Cursor / Claude Desktop 复用,升级工具不动 Agent**  B. 性能更高  C. 不需要 GitHub Token  D. 可以离线工作 → **A**。这是 MCP 整个生态最核心的价值,可拉到 L13 "N+M vs N×M" 呼应。
3. Agent 调用 MCP Server 的关键代码步骤是?  **A. MCP 工具 schema → 转换成 OpenAI tool schema 喂给 LLM;LLM 返回 tool_calls 后 → 反向转发到 MCP session 的 `call_tool` 执行**  B. Agent 直接发 JSON-RPC  C. 把所有 MCP 工具拼成一个 prompt  D. 让 LLM 直接生成 JSON-RPC → **A**。schema 的两次转换 + 调用转发 是 Agent ↔ MCP 桥接代码的核心。
4. **简答**:为什么不直接在 Agent 里调 GitHub SDK?
   - **参考答案**:① MCP 复用,同一 server 任意 host 可用;② 统一鉴权/限流/日志;③ 工具升级不动 Agent;④ 跨团队协作友好;⑤ 工具开发者与 Agent 开发者可独立迭代。
5. **场景**:同事要在 Claude Desktop 复用这个 server,怎么做?
   - **参考答案**:① 共享 server 源码与启动命令(stdio 模式各自本地启);② 或部署成 Streamable HTTP + 鉴权,同事在 `claude_desktop_config.json` 添加配置即可;③ 文档化 env 需求(如 GitHub Token 怎么生成)。

### 九、教学反思要点
- async 编程是不少学员的"再启蒙"机会,可以多答疑 5 分钟。
- 把这个项目作为模块 3 的里程碑标杆,后续模块的 trace/eval 都拿它做底。

---

*模块 3 结束。下一模块给 Agent 装上记忆(M4)。*
