# 模块 2:动手搭建第一个 Agent(L7–L12)讲师讲稿版

> 本模块以"动手编码"为主线,每课 30 min+ 实操,务必每人现场跑通。
> 配套代码:工作区 `examples/hello-agent/main.py`、`examples/hello-agent/mcp_server.py`、`examples/hello-agent/issues_agent.py`。
> 蓝色引用块 `> 【讲师讲稿】` 内为建议口述内容,可直接念。

---

## L7 — 开发环境搭建

### 一、基本信息
- **课时编号**:L7
- **课时时长**:90 分钟
- **课型**:实操为主
- **前置**:L1–L6
- **教具**:Windows PowerShell / macOS Terminal、Python 3.11+ 安装包、`.env.example` 模板。

### 二、教学目标
**知识目标**
- 解释虚拟环境(venv)的作用与必要性。
- 列出 Agent 项目的核心依赖:`openai / anthropic / python-dotenv / pydantic / tiktoken`。
- 说明 `.env` + `python-dotenv` 安全管理 API Key 的标准做法。

**能力目标**
- 在本机从零搭好可运行 LLM 调用的 Python 项目。
- 写一个 `smoke.py` 验证 API Key 是否生效。
- 把 `.env` 加进 `.gitignore`,避免泄密。

### 三、教学重点与难点
- **重点**:虚拟环境、`.env`、依赖锁文件(`requirements.txt` 或 `pyproject.toml`)。
- **难点**:Windows 学员经常踩 PATH、PowerShell 执行策略、路径转义三个坑。

### 四、教学准备

**【环境 / 依赖】**
- **课前发放清单**(见五节板书,提前 1 天发),要求学员上课前**必须**装齐:
  - Python 3.10+(推荐 3.12,兼容性最好)
  - Git(用于 .gitignore 演示)
  - IDE:VS Code / Cursor / PyCharm 任选
- **网络验证**:课前跑 `curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"` 或对应兼容端点,确认能返 200。**内网学员**须提前拿到公司代理或 Ollama 内网端点。
- **PowerShell 执行策略**(Windows 特有):课前提示学员以管理员打开 PowerShell 跑 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`,否则 `.venv\Scripts\Activate.ps1` 会报"脚本执行策略"。

**【代码素材】**
- **`.env.example` 模板**(讲师课上现场创建,供学员复制):
  ```
  # LLM 服务(至少填 1 组)
  OPENAI_API_KEY=sk-xxx-或-ollama
  OPENAI_BASE_URL=                       # 官方留空;Ollama 填 http://<host>:11434/v1;国内兼容服务填对应
  OPENAI_MODEL=gpt-4.1                   # 或 gpt-oss:20b、deepseek-chat 等
  ANTHROPIC_API_KEY=                     # 可选,后续 M2/M3 备用
  ```
- **`requirements.txt` 基线版**(讲师提前 `pip freeze` 一次锁定,防学员装到不兼容组合):
  ```
  openai>=1.30
  anthropic>=0.30
  python-dotenv>=1.0
  pydantic>=2.5
  tiktoken>=0.7
  ```
- **hello world 验证脚本** `hello.py` 20 行,课末让每人自己跑一次拿到 `pong` 就算搭建成功。

**【教学材料】**
- **依赖地狱 vs 虚拟环境**故事化 2 分钟讲稿(五.1 导入用):讲一个"A 项目 openai 1.5、B 项目 openai 2.0 全局装崩"的真实痛点。
- **`.gitignore` 强制内容**清单:`.venv/`、`.env`、`__pycache__/`、`*.pyc`、`.DS_Store`(macOS)。

**【学员课前】**
- 已装 Python 3.10+ 并能在终端跑 `python --version` 返回版本号。
- 已开通至少 1 个 LLM API key(OpenAI 官方 $5 credit 即可,或走 Ollama 本地零成本)。
- (可选)已看 5 分钟 Cursor 官方"如何切换 python interpreter"视频。

**【备用方案】**
- **助教 1~2 人**协助 Windows 学员现场排错(90% 卡在 `.env` 隐藏后缀、PowerShell 策略、代理这 3 类)。
- **网络全挂**降级方案:直接改用 Ollama 本地端点,`.env` 换 `OPENAI_BASE_URL=http://<讲师机 IP>:11434/v1`。
- **有学员完全没装 Python**:提供**云端 Codespaces 或 GitPod** 一键环境(讲师课前建好一个 template repo,fork 即用)。

### 五、教学过程

#### 1. 导入:为什么不能直接 pip install(5 min)

> 【讲师讲稿】"我先问个问题:如果不用虚拟环境,直接在系统 Python 里 `pip install openai`,会发生什么?"

> "结果是——**所有项目共享一个解释器和依赖列表**。你 A 项目用 openai 1.5,B 项目要 openai 2.0,这俩 API 不兼容,你装哪个都会让另一个崩。这就是 Python 生态里臭名昭著的'依赖地狱'(dependency hell)。"

> "解决办法很简单:**每个项目一个虚拟环境**。venv 帮你在项目目录里建一个独立的小 Python,装的依赖只对这个项目可见。今天我们就把这套标准工作流敲一遍,以后每个 Agent 项目都按这个套路开局。"

---

#### 2. 全流程现场演示(20 min)

讲师在投影上一步步执行,边敲边讲:

```powershell
# 1. 新建项目目录
mkdir my-agent
cd my-agent

# 2. 建虚拟环境(Windows)
python -m venv .venv
.venv\Scripts\Activate.ps1
# (macOS/Linux 用 source .venv/bin/activate)

# 3. 升级 pip,装依赖
python -m pip install --upgrade pip
pip install openai anthropic python-dotenv pydantic tiktoken

# 4. 锁版本
pip freeze > requirements.txt

# 5. 准备 .env
echo "OPENAI_API_KEY=sk-..." > .env

# 6. .gitignore
echo ".venv/`n.env`n__pycache__/" > .gitignore
```

**逐步骤解释**:

- **第 1 步**:目录名建议小写 + 短横线,跨平台兼容。
- **第 2 步**:`python -m venv .venv` 在当前目录创建 `.venv/` 子目录,里面是隔离的 Python。
  - 激活成功的标志:命令行前缀变成 `(.venv) PS C:\...>`。
  - **Windows 常见坑**:PowerShell 默认禁止脚本执行。如果激活报错 "无法加载文件 Activate.ps1",运行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 一次性解决。
- **第 3 步**:依赖说明:
  - `openai`:OpenAI 官方 SDK,包含 chat completions、embeddings、tool calls。
  - `anthropic`:Claude SDK。
  - `python-dotenv`:读 `.env` 文件。
  - `pydantic`:结构化数据校验,后面 L32 强制 JSON 输出时用。
  - `tiktoken`:token 计数。
- **第 4 步**:`pip freeze > requirements.txt` 把"当前装了什么、什么版本"写到文件,**这是协作和复现的基础**。同事克隆项目后 `pip install -r requirements.txt` 一键还原。
- **第 5 步**:`.env` 是文本文件,每行 `KEY=VALUE` 格式,不要加引号。
- **第 6 步**:**`.env` 一定要进 `.gitignore`**——这是泄密红线。

> 【讲师讲稿】"我每年都能在 GitHub 上看到至少几百次有人把 OpenAI Key 提交到 public repo,然后被自动扫描的爬虫薅羊毛,几小时就烧光额度。请大家务必养成肌肉记忆:**新项目第一件事就是 `.gitignore` 加 `.env`**。"

---

#### 3. 验证脚本 + 学员跟练(35 min)

讲师写 `smoke.py`:

```python
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4.1",
    messages=[{"role": "user", "content": "ping"}],
)
print(resp.choices[0].message.content)
```

**逐行解释**:

- `load_dotenv()`:读取当前目录 `.env`,把里面的变量注入 `os.environ`。**注意顺序**——必须先 `load_dotenv`,再 import 用到环境变量的库。
- `client = OpenAI()`:SDK 会自动读 `os.environ["OPENAI_API_KEY"]`。**这是最简版本**,适合本课"先把环境跑通"。从 **L8 起我们会升级为 production 写法**:`api_key = os.getenv(...); assert api_key; client = OpenAI(api_key=api_key, base_url=base_url)`——错误信息对学员/同事更友好,且支持国内 OpenAI 兼容服务(DeepSeek / 智谱 / Qwen 等)。
- 这一段就是最简单的"一次 LLM 调用",成功跑通说明环境 OK。

**学员独立跟练 25 分钟**,助教逐桌验收。卡点统计(给讲师参考):
- 90% 的卡点是 `.env` 没生效——多半是文件名写成 `.env.txt`(Windows 资源管理器默认隐藏后缀)。
- 5% 是 PowerShell 执行策略。
- 5% 是网络问题(需配代理)。

---

#### 4. 常见坑总结(15 min)

讲师在白板列出"环境搭建 Top 10 坑",每个给一句话解决方案:

| # | 坑 | 解决 |
|---|---|---|
| 1 | `.env` 名字带 `.txt` 后缀 | 资源管理器 → 查看 → 文件扩展名 ☑ |
| 2 | PowerShell 不让激活 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 3 | `python` 命令不存在 | 装 Python 时勾选 "Add to PATH";或用 `py -3.11` |
| 4 | `pip` 装包慢 | 配镜像:`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple` |
| 5 | 中国大陆访问 OpenAI 慢/失败 | 配代理(http_proxy/https_proxy 环境变量),或用第三方网关 |
| 6 | Windows 路径里有空格 | 用引号包起来 `cd "C:\My Projects\agent"` |
| 7 | venv 激活后还是用系统 Python | 检查 `where python` 是否指向 `.venv\Scripts\python.exe` |
| 8 | `.env` 写了变量但 `os.getenv` 拿不到 | `load_dotenv()` 必须在 `import openai` 之前 |
| 9 | 多人协作时依赖版本不一致 | 必须用 `requirements.txt` 锁版本,或 `pyproject.toml` |
| 10 | Key 提交到 Git | 一旦发生立即 revoke 旧 Key,再用 BFG/`git filter-repo` 清历史 |

> 【讲师讲稿】"这 10 个坑我每个班至少能看到 7 个。今天大家踩到的请举手记下来,以后帮新同事 onboarding 时直接给他这个列表。"

---

#### 5. 测查 + 小结(10 min)

**测查(7 min)**:投影第八节 3 道选择题,**学员举手抢答**(30 秒思考),公布答案后讲师针对每题陷阱**点 1 句**。简答与场景题分两组讨论 2 分钟后口头作答,讲师对照标准答案补漏。

**小结(3 min)**:讲师投影 "今天必须带走的 3 句话":

> **今天必须带走的 3 句话**:
> 1. **每个项目独立 venv**——依赖隔离是最低工程素养,Python 项目跨版本冲突的代价大于 30 秒建虚拟环境的成本。
> 2. **`.env` 永远不进 Git**——密钥一旦推到公网仓库,几小时内必被爬虫扫到滥用,赔偿额从几十美元到上万美元都有真实案例。
> 3. **`api_key = os.getenv(...) + assert`** 而不是 `OpenAI()` 默认魔法读取——错误信息"人类可读"比"SDK 报错"对学员/同事友好 10 倍。

> 【讲师讲稿】"今天搭好的脚手架是后面 5 节课的工作平台——L8 开始我们就在这个项目上一点点加 function calling、加循环、加并发、加重试。环境没搭好就等于地基没打稳,后面所有课都会反复栽跟头。回家请务必把作业做完。"

#### 6. 作业(5 min)
- 把今天的项目结构推到自己的 GitHub(或本地仓库)。
- 验证 `.env` 没进版本控制(`git status` 看不到它即可)。

**参考答案(命令清单)**:

```bash
# 1. 初始化仓库(若已 init 可跳)
git init
git add .
git status                   # ← 关键:确认 .env 不在列表里(应被 .gitignore 挡掉)

# 2. 如果 .env 出现在 list 中,说明 .gitignore 漏了它,立刻补
echo ".env" >> .gitignore
echo ".venv/" >> .gitignore
git rm --cached .env 2>/dev/null   # 之前不小心 add 过的话,从暂存区移除(本地文件保留)

# 3. 再次确认
git status | grep -E "\.env|\.venv" && echo "❌ 还能看到 .env" || echo "✅ .env 已被忽略"

# 4. commit + push
git commit -m "Initial project scaffold"
git remote add origin https://github.com/<you>/my-agent.git
git branch -M main
git push -u origin main

# 5. 提交后再到 GitHub 网页搜 "OPENAI_API_KEY" / "sk-" 确认无泄露
```

**验收清单**:
1. `git status` 看不到 `.env` 和 `.venv/`;
2. `requirements.txt` 已提交;
3. `README.md` 有"如何 setup"段;
4. GitHub 网页打开仓库,**搜索 `sk-` 应无任何匹配**(若有立刻去 OpenAI 后台 revoke 该 key,泄露不可逆——key 一旦上 GitHub,1 分钟内会被爬虫扫到刷光)。

**常见错误**:
- `.env.example` 不能写真 key,只放占位符 `OPENAI_API_KEY=sk-xxx-PLACEHOLDER`;
- Windows 资源管理器默认隐藏后缀,容易把 `.env` 误存成 `.env.txt`,务必用 `dir /a` 或 `ls -la` 核实文件名。

### 六、板书设计
```
项目骨架
my-agent/
├── .venv/              ← 虚拟环境(.gitignore)
├── .env                ← 密钥(.gitignore,绝不提交!)
├── .env.example        ← 模板,告诉别人需要哪些 KEY
├── .gitignore          ← .env, .venv/, __pycache__/, *.pyc
├── requirements.txt    ← 锁版本
└── smoke.py            ← 验证脚本

激活:
  Windows: .venv\Scripts\Activate.ps1
  macOS:   source .venv/bin/activate
```

### 七、课堂练习(完整发放版)

> 讲师提示:本节练习是"从零到跑通 hello world"的完整清单,学员逐条打勾,不能跳步。总时长 30-40 分钟。**Windows / macOS / Linux 三平台都给命令**,学员按自己系统对号入座。

#### 练习 1:hello-agent 项目从零搭建(30 min,全员独立)

**任务**:按下面清单**逐条**完成,每完成一条打勾。**验收标准**:能跑 `python hello.py` 返回 `pong`。

**Step 1:目录 + venv(5 min)**

```powershell
# Windows PowerShell
mkdir hello-agent; cd hello-agent
python -m venv .venv
.venv\Scripts\Activate.ps1                  # 若报"策略"错,先跑 Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
```
```bash
# macOS / Linux
mkdir hello-agent && cd hello-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

**验收**:提示符前应有 `(.venv)`,`which python` (mac/linux) 或 `Get-Command python` (win) 指向 `.venv` 里的 python。

**Step 2:装依赖 + 锁版本(3 min)**

```bash
pip install openai anthropic python-dotenv pydantic tiktoken
pip freeze > requirements.txt
```

**验收**:`requirements.txt` 里至少 5 行,`openai>=1.30` 存在。

**Step 3:创建 `.env`(3 min)**

```bash
# .env  ← 用编辑器创建;Windows 别用 记事本(会加 .txt 后缀)
OPENAI_API_KEY=sk-xxx-或-ollama
OPENAI_BASE_URL=                            # 官方留空;Ollama 填 http://localhost:11434/v1
OPENAI_MODEL=gpt-4.1                        # 或 gpt-oss:20b、deepseek-chat
```

**验收**:文件名精确是 `.env`(不是 `.env.txt`),内容至少 1 行有值。

**Step 4:创建 `.gitignore`(2 min)**

```
.venv/
.env
__pycache__/
*.pyc
.DS_Store
```

**验收**:`git init` 后 `git status` 不显示 `.venv` 和 `.env`。

**Step 5:写 `hello.py`(10 min)**

```python
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL") or None
model = os.getenv("OPENAI_MODEL", "gpt-4.1")

assert api_key, "OPENAI_API_KEY 未配置,请检查 .env"

client = OpenAI(api_key=api_key, base_url=base_url)

resp = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "请只回复一个词:pong"}],
)

print(f"model={model}")
print(f"content={resp.choices[0].message.content}")
```

**Step 6:跑通(2 min)**

```bash
python hello.py
```

**期望输出**:
```
model=gpt-4.1
content=pong
```

**验收 checklist**(全部打勾才算过):
- [ ] `(.venv)` 提示符正确显示
- [ ] `pip list` 至少有 openai / dotenv / tiktoken
- [ ] `.env` 文件名正确(无 .txt 后缀)
- [ ] `hello.py` 跑起来打印 `pong`(或类似,不一定精确)
- [ ] `.gitignore` 里 `.env` 和 `.venv/` 都在

---

#### 练习 2:排 3 个常见坑(5 min,个人自查)

**任务**:下面 3 个错误信息是新手最常见的,分别原因和修法是什么?

**报错 A**:
```
.venv\Scripts\Activate.ps1 : 无法加载文件 ...,因为在此系统上禁止运行脚本。
```

**报错 B**:
```
openai.OpenAIError: The api_key client option must be set either by passing api_key to the client or by setting the OPENAI_API_KEY environment variable
```

**报错 C**:
```
ModuleNotFoundError: No module named 'openai'
```

**参考答案**:

| 报错 | 原因 | 修法 |
| ---- | ---- | ---- |
| A | PowerShell 执行策略禁止 | **管理员 PowerShell** 跑 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| B | `.env` 没被 load,或 key 拼错 | 检查:`.env` 文件在项目根目录、`load_dotenv()` 被调、变量名精确 `OPENAI_API_KEY` |
| C | 装 openai 时不在 venv 里 | 确认 `(.venv)` 前缀在;或 `pip show openai` 看 Location 是不是 `.venv` 路径 |

**常见坑合集(讲师板书)**:
- Windows `记事本` 创建 `.env` 会静默加 `.txt` 后缀 → 用 VS Code 或 `notepad ".env"` 显式加引号
- macOS/Linux `.env` 权限太开 → `chmod 600 .env`
- `.env` 里 key 前后有引号 → `OPENAI_API_KEY="sk-..."` 也可以,但值里不能有空格
- 换了 shell 但没 activate venv → 每开一个新终端都要 activate 一次

**挑战延伸(选做)**:
- 把 `.env` 里的 `OPENAI_BASE_URL` 切到本地 Ollama(`http://localhost:11434/v1`),用 `gpt-oss:20b` 或 `qwen3` 再跑 hello.py,能返回不同模型的 pong
- 加个 `--model gpt-4o-mini` 命令行参数,让 hello.py 支持切换模型

### 八、测查题与参考答案

1. 哪个文件**绝对不能**提交到 Git 仓库?  A. `requirements.txt`  **B. `.env`(含密钥)**  C. `.env.example`(只有 KEY 没有值)  D. `README.md` → **B**。`.env` 里通常含 `OPENAI_API_KEY` 等敏感信息,一旦推到公网仓库会立刻被爬虫扫到滥用。
2. `python -m venv .venv` 的作用是什么?  A. 安装 Python 解释器  **B. 在当前目录下创建一个隔离的 Python 虚拟环境**  C. 创建一个 Docker 容器  D. 删除已有依赖 → **B**。venv 让每个项目有独立 site-packages,依赖互不污染。
3. 在 Python 里读取 `.env` 的标准写法?  A. `open('.env').read()` 手动 split  **B. `from dotenv import load_dotenv; load_dotenv(); os.getenv('OPENAI_API_KEY')`**  C. `os.environ['.env']`  D. `json.load(open('.env'))` → **B**。`python-dotenv` 库会自动把 `.env` 注入到 `os.environ`,代码统一用 `os.getenv` 取值。
4. **简答**:为什么每个项目要独立虚拟环境?
   - **参考答案**:依赖版本隔离,避免不同项目互相冲突;便于复现和部署;避免污染系统 Python。
5. **场景**:同事克隆项目跑不起来,可能漏了什么?
   - **参考答案**:① 没 `pip install -r requirements.txt`;② 没建 `.env`(只有 `.env.example`);③ Python 版本不匹配;④ 没激活 venv;⑤ 缺系统级依赖(如 C 编译器、SQLite);⑥ 缺代理配置(国内访问 OpenAI)。

### 九、教学反思要点
- 全班最长的卡点是不是 Windows PowerShell?提前在邀请邮件里告知。
- 是否所有学员 `smoke.py` 都成功?未成功的需要课后单独解决,否则 L8 无法继续。

---

## L8 — 第一个 Function Calling 示例

### 一、基本信息
- **课时编号**:L8
- **课时时长**:90 分钟
- **课型**:实操
- **前置**:L3、L7
- **教具**:OpenAI SDK、L3 的 schema 示例、一段"故意有 3 个 bug"的对照代码。

### 二、教学目标
**知识目标**
- 写出一个完整的"单次工具调用 → 回填 → 二次调用"流程。
- 解释 `msg.tool_calls` 和 `call.function.arguments` 的数据结构。

**能力目标**
- 现场跑通 L3 的理论例子。
- 阅读 function calling 代码并指出常见 bug。

### 三、教学重点与难点
- **重点**:回填后**必须**再次调用 LLM 拿 final answer。
- **难点**:学员经常忘记 `arguments` 是 JSON 字符串需要 `json.loads`。

### 四、教学准备

**【环境 / 依赖】**
- 学员环境应已完成 L7 搭建(openai + python-dotenv + tiktoken,`.env` 已配好 key)。课前抽查 3 人跑 `hello.py` 应能返回 `pong`。
- **今日新增**:无需额外装包,直接用 L7 的 venv。

**【代码素材】**(讲师保存为独立 py 文件,课上分屏投影)
- **完整正确版** `L8_correct.py`(五.2 板书代码的完整可跑版):`from openai import OpenAI; ... 两步 chat.completions.create ...`,约 40 行,教学重心在"两次调用"。
- **3 段"几乎正确"的 bug 代码**(五.3 找茬,与 L3 类似但更长,更贴近生产):
  - **Bug 1**:`args = call.function.arguments`(漏 `json.loads`)—— 错误症状 `TypeError: get_weather() argument after ** must be a mapping`
  - **Bug 2**:回填 `{"role":"assistant","content":result}` 而非 `{"role":"tool","tool_call_id":...,"content":result}` —— 症状:模型认为工具没执行,重复请求
  - **Bug 3**:漏 `messages.append(msg)` —— 症状:第二次调用报 `Invalid parameter: 'tool' message without preceding 'assistant' with tool_calls`
- 上述 3 段 bug 建议**独立成文件** `L8_bug1.py` `L8_bug2.py` `L8_bug3.py`,便于逐个跑给学员看真实报错。

**【数据 / 样例】**
- **单工具 prompt** 3 条:`"北京天气"`(单次工具调用足)、`"1+1"`(不应调工具)、`"上海和北京谁热"`(应调工具 2 次)—— 5.4 单工具/多工具场景演示。
- **API 报错清单**:准备好 3 个常见报错的截图或文本,便于学员认出"这就是刚才那个 bug"。

**【教学材料】**
- **两次 chat.completions.create 流程图**(五.4 板书):`resp1 得 tool_calls → 本地跑 fn → 回填 → resp2 得 final`。
- **`messages` 生命周期示意**:user → assistant(with tool_calls) → tool → assistant(final);标注哪 4 条消息在同一次 loop 内产生。

**【学员课前】**
- 已在 L7 hello world 基础上跑通 1 次 LLM 调用。
- 想清楚"课上想加的第 2 个 tool"(比如 `now_time`、`add`),课后作业 L8 第 7 题会用。

**【备用方案】**
- 若 gpt-4.1 拒调工具(极少数情况) → 换 `gpt-4.1-mini` 或本地 `gpt-oss:20b`,后者对 function calling 支持稳定。
- 若学员找不到 bug → 讲师逐段 `print(...)` 打印中间变量,让 bug 自暴露(教学法:让 bug 说话,而非讲师直接指)。

### 五、教学过程

#### 1. 导入(5 min)

> 【讲师讲稿】"L3 我们讲了 function calling 的原理,L7 把环境搭好了。今天我们要把这两个串起来,让你的代码**真的跟模型完成一次工具调用 + 回填 + 拿最终回复**的完整循环。这是后面所有 Agent 课的基石——你能写到这里,再加上 max_steps,就是一个最小 Agent。"

---

#### 2. 完整示例从零写到通(20 min)

讲师从空文件开始,逐行写、逐行讲:

```python
from openai import OpenAI
from dotenv import load_dotenv
import json, os

load_dotenv()

# production 写法:显式取 key + fail-fast,L7 hello world 用过的简化版本(`OpenAI()`)
# 在错误信息上对学员/同事不够友好,从 L8 起统一升级
api_key  = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL") or None   # 用国内 OpenAI 兼容服务时填,留空走官方
assert api_key, "未读到 OPENAI_API_KEY——请检查 .env 文件名/位置/变量名"
client = OpenAI(api_key=api_key, base_url=base_url)
MODEL  = os.getenv("OPENAI_MODEL", "gpt-4.1")     # 兼容服务时改 .env,代码不动

# 1. 定义业务函数
def get_weather(city: str) -> str:
    """模拟天气查询,真实场景这里调气象 API"""
    return f"{city} 今天 25°C 晴"

# 2. 定义工具 schema
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a city. Use when user asks about today's weather.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}]

# 3. 第一次调用:模型决定调工具
messages = [{"role": "user", "content": "上海天气怎么样?"}]
resp1 = client.chat.completions.create(
    model=MODEL, messages=messages, tools=tools
)
msg = resp1.choices[0].message
messages.append(msg)   # ← 关键!先把 assistant 消息(含 tool_calls)入栈

# 4. 检查并执行 tool_calls
if msg.tool_calls:
    for call in msg.tool_calls:
        args = json.loads(call.function.arguments)   # ← 关键!arguments 是字符串
        result = get_weather(**args)
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": str(result),
        })

# 5. 第二次调用:模型基于工具结果生成最终回复
resp2 = client.chat.completions.create(
    model=MODEL, messages=messages, tools=tools
)
print(resp2.choices[0].message.content)
```

**逐段精讲**:

- **业务函数 vs schema**:`get_weather` 是普通 Python 函数,模型不会"看到"它的实现,只会看到 `tools` 数组里的描述。两者**通过 `name` 字符串关联**。
- **第一次调用**:`tools=tools` 参数告诉模型"你有这些工具可用"。模型决定是否调用,以 `tool_calls` 字段返回。
- **`messages.append(msg)`**:**最容易漏的一步**。assistant 消息本身要先入栈,然后才是每个 tool 结果。如果漏了,下一轮模型看不到自己当初的 tool_calls,会困惑。
- **`json.loads(call.function.arguments)`**:这是 OpenAI SDK 的设计——`arguments` 是 JSON 字符串,要解析才是 dict。
- **`role="tool"` + `tool_call_id`**:这两个字段缺一不可,否则模型不知道这段结果对应哪次调用。
- **第二次调用**:模型读到 `tool` 消息后,生成自然语言回复(也可能再调下一个工具,此时就要循环——这是 L9 的内容)。

> 【讲师讲稿】"请大家务必看清楚步骤 4 和 5 的顺序:**先把 assistant 消息 append,再 append 每个 tool 结果,再调下一次 LLM**。三个动作的顺序不能错。这是写 Agent 的'交规',违章了模型一定罚单。"

---

#### 3. Bug 寻找小游戏(20 min)

讲师投影 3 段"几乎正确"的代码,学员限时 8 分钟找 bug:

**Bug 1**:
```python
for call in msg.tool_calls:
    args = call.function.arguments        # ← 这里少了 json.loads
    result = get_weather(**args)
```
- **症状**:`TypeError: get_weather() argument after ** must be a mapping`。
- **修复**:`args = json.loads(call.function.arguments)`。

**Bug 2**:
```python
messages.append({
    "role": "assistant",                  # ← 错!应该是 tool
    "content": result,
})
```
- **症状**:不报错,但模型行为诡异——它不知道这段内容是它自己说的还是工具说的;而且 `tool_call_id` 不对齐,后续多轮会乱。
- **修复**:`role="tool"` + 加 `tool_call_id=call.id`。

**Bug 3**:
```python
resp1 = client.chat.completions.create(...)
msg = resp1.choices[0].message
# ← 漏了 messages.append(msg)
for call in msg.tool_calls:
    ...
    messages.append({"role":"tool", ...})
```
- **症状**:模型在第二次调用时,看不到自己曾经发出的 tool_calls,只看到一堆"凭空冒出来的 tool 结果",一头雾水,可能再调一遍同样的工具或直接报错。
- **修复**:`messages.append(msg)` 必须在 for 循环之前。

> 【讲师讲稿】"Bug 3 最阴险——代码不会抛异常,但模型会胡言乱语。我亲眼看过一个团队 debug 这种 bug 整整一天,最后发现就是少了一行 `messages.append(msg)`。请大家把'**先 append assistant,再 append 每个 tool 结果**'刻在脑子里。"

---

#### 4. 学员动手:写一个 now_time 工具(25 min)

任务:写一个新工具 `now_time()`,返回当前 UTC 时间;接入完整流程;输入"现在几点?"看 final answer 是否真的用了工具。

讲师提示:
- 工具实现可以用 `datetime.now(timezone.utc).isoformat()`。
- schema 的 description 要写清楚"当用户询问当前时间/日期时使用"。
- 看日志确认有真的进入 `if msg.tool_calls:` 分支。

助教逐桌验收。

---

#### 5. 测查 + 小结(15 min)

**测查(10 min)**:
1. 投影第八节 3 道选择题,**学员举手抢答**(30 秒思考),公布答案后讲师针对每题陷阱**点 1~2 句**——尤其第 2 题 "arguments 是 JSON 字符串" 是新手 90% 会忘的 `json.loads`,务必反复强调。
2. **简答 + 场景题**(第 4、5 题)分两组讨论 3 分钟,代表口头作答,讲师对照标准答案补漏。

**小结(5 min)**:讲师投影 "今天必须带走的 3 句话":

> **今天必须带走的 3 句话**:
> 1. **第一次响应里 `tool_calls` 是 `list[ToolCall] | None`,`arguments` 是 JSON 字符串**——`json.loads` 是新手忘记次数最多的一行代码。
> 2. **回填三件套**:`role="tool"` + `tool_call_id=call.id` + `content=str(result)`;且**先 `append(msg)` 后 `append(tool_result)`**,顺序反了 API 直接报错。
> 3. **必须两次 LLM 调用**——第一次决定调什么,第二次基于工具结果生成自然语言回复。少调一次,用户看到的就是 raw tool_calls,体感"工具没用"。

> 【讲师讲稿】"今天敲的代码是 L9 主循环的种子——L9 我们把这段'两次调用'扩展成'循环到没有 tool_calls 为止',就是真正的 Agent 主循环了。回家务必把作业里的 `now_time(timezone=...)` 写完,熟悉一下'扩参数 → 改 schema → 验 LLM 真的传新参数'这个完整链路。"

#### 6. 作业(5 min)
- 升级 `now_time` 接受可选参数 `timezone="UTC"`,支持 "Asia/Shanghai" 等;自测三种时区。

**参考答案**:

```python
from zoneinfo import ZoneInfo                 # Python 3.9+ 标准库
from datetime import datetime

def now_time(timezone: str = "UTC") -> str:
    """Return current time in the given IANA timezone (default UTC)."""
    try:
        tz = ZoneInfo(timezone)
    except Exception:                         # 关键:错误时返回字符串而非 raise
        return f"ERROR: unknown timezone '{timezone}', expected IANA name like 'Asia/Shanghai'"
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")

# schema 也要同步升级
NOW_TIME_SCHEMA = {
    "type": "function",
    "function": {
        "name": "now_time",
        "description": "Get current time in a given IANA timezone (default UTC). Use when user asks 'what time is it' or needs a timestamp.",
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone name, e.g. 'UTC', 'Asia/Shanghai', 'America/New_York'. Default 'UTC' if not specified.",
                    "default": "UTC",
                },
            },
            "required": [],                   # ← timezone 可选,不在 required 里
        },
    },
}

# 自测正常路径
for tz in ["UTC", "Asia/Shanghai", "America/New_York"]:
    print(f"{tz:20s} → {now_time(tz)}")
# 自测异常路径
print(now_time("Foo/Bar"))                    # 期望:ERROR: unknown timezone 'Foo/Bar', ...
```

**评分要点**:
1. schema 里 `timezone` 在 `properties` 但**不在** `required`(可选参数);
2. description 里明确"default UTC if not specified"(让 LLM 知道默认值);
3. 错误时回 `ERROR: ...` 字符串而非 raise(保留 Agent 自愈,见 L8 第 4 题简答);
4. 用 `zoneinfo`(stdlib)而非 `pytz`(后者 2020 后已不推荐)。

### 六、板书设计
```
完整四步:
  1) resp1 = create(messages, tools=tools)
  2) msg = resp1.choices[0].message
     messages.append(msg)                       ← 不要漏
  3) for call in msg.tool_calls:
        args = json.loads(call.function.arguments)   ← 字符串!
        result = TOOL[call.function.name](**args)
        messages.append({
          "role": "tool",                       ← 不是 assistant
          "tool_call_id": call.id,              ← 必须带
          "content": str(result)
        })
  4) resp2 = create(messages, tools=tools)     ← 必须再调一次!
     print(resp2.choices[0].message.content)
```

### 七、课堂练习(完整发放版)

> 讲师提示:本节 2 题,总时长 35-40 分钟。练习 1 找 bug(15 min)+ 练习 2 实现 `now_time`(20 min)。学员需要 hello-agent 环境(继承 L7)。

#### 练习 1:找 3 个 bug(15 min,个人)

**任务**:下面代码是一段"看起来能跑"的 function calling 完整代码,但有 **3 个 bug**。找出并说明:
1. 具体在哪一行
2. 症状是什么(会报什么错 or 产生什么错误行为)
3. 怎么修

```python
 1  import json
 2  from openai import OpenAI
 3  from dotenv import load_dotenv
 4  load_dotenv()
 5  client = OpenAI()
 6
 7  def get_weather(city):
 8      return {"city": city, "temp": 25, "condition": "sunny"}
 9
 10 TOOLS = [{
 11     "type": "function",
 12     "function": {
 13         "name": "get_weather",
 14         "description": "Get current weather for a city.",
 15         "parameters": {
 16             "type": "object",
 17             "properties": {"city": {"type": "string"}},
 18             "required": ["city"]
 19         }
 20     }
 21 }]
 22
 23 messages = [{"role": "user", "content": "上海天气怎么样?"}]
 24
 25 resp = client.chat.completions.create(model="gpt-4.1", messages=messages, tools=TOOLS)
 26 msg = resp.choices[0].message
 27
 28 for call in msg.tool_calls:
 29     args = call.function.arguments                     # ← 思考点 A
 30     result = get_weather(**args)
 31     messages.append({                                    # ← 思考点 B
 32         "role": "assistant",
 33         "content": str(result)
 34     })
 35
 36 resp2 = client.chat.completions.create(model="gpt-4.1", messages=messages, tools=TOOLS)
 37 print(resp2.choices[0].message.content)
```

**思考点提示**(讲师逐个揭示):
- A(行 29):`arguments` 是什么类型?
- B(行 31-34):`role` 应该填什么?`tool_call_id` 在哪?
- C(潜在):`resp` 拿到之后 `msg` 有没有先入 `messages`?

**参考答案**:

| # | 位置 | 症状 | 修法 |
| - | ---- | ---- | ---- |
| **Bug 1** | 行 29 | `TypeError: get_weather() argument after ** must be a mapping, not str` | 改为 `args = json.loads(call.function.arguments)` |
| **Bug 2** | 行 31-34 | 报错 `Invalid parameter: messages with role 'tool' must be a response to a preceding message with 'tool_calls'`,或者第二次 chat 认为工具没执行,又去调 | 改为 `{"role":"tool", "tool_call_id":call.id, "content":str(result)}` |
| **Bug 3** | 缺行(应在 27 后加) | 报错 `messages with role 'tool' must be a response to a preceding message with 'tool_calls'` | 在 for 循环前加 `messages.append(msg)`(把 assistant 的 tool_calls 消息入栈) |

**修复后的完整正确代码**:
```python
# ...(header 同上,略)
resp = client.chat.completions.create(model="gpt-4.1", messages=messages, tools=TOOLS)
msg = resp.choices[0].message
messages.append(msg)                                              # ← 修 Bug 3

for call in msg.tool_calls:
    args = json.loads(call.function.arguments)                    # ← 修 Bug 1
    result = get_weather(**args)
    messages.append({
        "role": "tool",                                           # ← 修 Bug 2
        "tool_call_id": call.id,
        "content": str(result)
    })

resp2 = client.chat.completions.create(model="gpt-4.1", messages=messages, tools=TOOLS)
print(resp2.choices[0].message.content)
```

**验收 checklist**:
- [ ] 3 个 bug 都找到
- [ ] 每个 bug 都能说出**具体报错信息**(不是"就是错了")
- [ ] 修复代码能真跑通(可在 hello-agent 里验证)

---

#### 练习 2:实现 `now_time` 工具(20 min,个人)

**任务**:基于练习 1 修好的代码,新增一个工具 `now_time(timezone: str = "UTC") -> str`,支持:
- 输入时区名(如 `"Asia/Shanghai"`、`"UTC"`、`"America/New_York"`)
- 返回 ISO 格式字符串(如 `"2026-07-03T09:00:00+08:00"`)
- 时区错误时优雅返回错误信息(不 raise)

然后跑 3 个测试 prompt,验证 LLM **会选对工具、传对参数**:
1. `"上海现在几点?"` → 应调 `now_time(timezone="Asia/Shanghai")`
2. `"纽约当前时间"` → 应调 `now_time(timezone="America/New_York")`
3. `"北京天气怎么样"` → 应调 `get_weather(city="北京")`(不调 now_time)

**骨架代码**:
```python
from datetime import datetime
from zoneinfo import ZoneInfo                    # Python 3.9+ 标准库

def now_time(timezone: str = "UTC") -> str:
    """
    TODO: 实现:根据 timezone 返回 ISO 格式当前时间
    时区错误(如 'Asia/InvalidCity')时返回 "[ERROR] unknown timezone: ..."
    """
    ...

# TODO: 添加 tool schema
NOW_TIME_SCHEMA = {
    "type": "function",
    "function": {
        "name": "now_time",
        "description": "TODO: 写 what/when to use/when NOT/params/returns",
        "parameters": {
            "type": "object",
            "properties": {
                # TODO
            },
            "required": []
        }
    }
}

TOOLS = [WEATHER_SCHEMA, NOW_TIME_SCHEMA]
REGISTRY = {"get_weather": get_weather, "now_time": now_time}
# 主循环...
```

**验收 checklist**:
- [ ] `now_time("Asia/Shanghai")` 返回类似 `"2026-07-03T15:00:00+08:00"`
- [ ] `now_time("Asia/InvalidCity")` 返回 `"[ERROR] unknown timezone: Asia/InvalidCity"`(不 raise)
- [ ] 3 个测试 prompt LLM 都选**对**工具、传**对**参数
- [ ] schema description 至少覆盖 what + when to use(**不能**是 `"a tool"` 这种敷衍描述)

**参考答案**:
```python
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

def now_time(timezone: str = "UTC") -> str:
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        return f"[ERROR] unknown timezone: {timezone}"
    return datetime.now(tz).isoformat(timespec="seconds")

NOW_TIME_SCHEMA = {
    "type": "function",
    "function": {
        "name": "now_time",
        "description": (
            "Get the current time in ISO 8601 format for the specified timezone. "
            "Use this whenever the user asks 'what time is it', 'now', 'current time', "
            "or mentions timing that requires wall clock. "
            "Do NOT use for scheduling or date arithmetic — that needs a calendar tool. "
            "Params: timezone (IANA name like 'Asia/Shanghai', default 'UTC'). "
            "Returns: ISO string like '2026-07-03T15:00:00+08:00'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone name (e.g. 'Asia/Shanghai', 'UTC', 'America/New_York'). Default 'UTC'."
                }
            },
            "required": []
        }
    }
}
```

**常见坑**:
- 用 `datetime.utcnow()` 返回 naive datetime,没有时区信息 → 用 `datetime.now(tz)`
- schema description 只写 "get time",LLM 有时该调不调 → 明写 "use whenever user mentions time"
- tool 直接 raise 时区错误 → **必须**捕获并返回字符串,让 LLM 看到再决定要不要重试

**挑战延伸(选做)**:
- 加一个 `add(a: int, b: int) -> int` 工具,跑 `"1+2+3=?"` 看 LLM 是否会**连续调 3 次**(应会)
- 让 3 个工具(get_weather、now_time、add)**同时**注册,喂 `"北京现在几点、天气怎么样"`,看 LLM 是否**一次返 2 个 tool_calls**

### 八、测查题与参考答案

1. OpenAI API 第一次响应里 `msg.tool_calls` 的类型是?  A. `str`(模型直接写的代码)  **B. `list[ToolCall] | None`(SDK 已解析的结构化对象列表)**  C. `dict[str, str]`  D. 总是 `None`(必须自己解析) → **B**。模型若决定调工具就返回 list,否则 None;用 `if msg.tool_calls:` 判断。
2. `call.function.arguments` 字段的实际类型是?  A. `dict`(Python 原生字典)  **B. JSON 字符串,使用前需 `json.loads(...)`**  C. `list[tuple]`  D. `bytes` → **B**。所有 OpenAI 兼容 API 都以 string 传 arguments(便于跨语言),不调 `json.loads` 会得到 `'a'` 而不是 `'a' 字段的值`。
3. 回填工具结果后,**还要**再调一次 `chat.completions.create` 吗?  A. 不用,首次响应里就有最终回复  **B. 要,LLM 拿到工具结果后才会生成自然语言回复**  C. 看模型版本,GPT-4 不用  D. 看是否流式 → **B**。第一次 LLM 只给"调用意向";拿到 obs 后第二次才生成"给用户看的话"。所以**至少两次** API call。
4. **简答**:工具抛异常怎么写回 messages?
   - **参考答案**:不要让异常冒泡,捕获后以 `role=tool` 写回错误信息,例如 `content=f"ERROR: {type(e).__name__}: {e}"`,让 LLM 看见错误并自我修正。
5. **编程**:把单次 function calling 代码改成"持续循环直到模型不再返回 tool_calls"(即:支持多步 ReAct,如先 `get_weather` 再 `get_news`)。
   - **参考答案**:
     ```python
     from openai import OpenAI
     from dotenv import load_dotenv
     import json, os
     load_dotenv()

     api_key  = os.getenv("OPENAI_API_KEY")
     base_url = os.getenv("OPENAI_BASE_URL") or None
     assert api_key, "未读到 OPENAI_API_KEY"
     client = OpenAI(api_key=api_key, base_url=base_url)
     MODEL  = os.getenv("OPENAI_MODEL", "gpt-4.1")

     # 工具注册表:name → callable
     def get_weather(city: str) -> str:
         return f"{city} 今天 25°C 晴"
     def get_news(topic: str) -> str:
         return f"今日 {topic} 头条:xxx"

     TOOL_REGISTRY = {"get_weather": get_weather, "get_news": get_news}

     TOOL_SCHEMAS = [
         {"type": "function", "function": {
             "name": "get_weather",
             "description": "Get today's weather for a city. Use when user asks weather.",
             "parameters": {"type":"object",
                            "properties":{"city":{"type":"string"}},
                            "required":["city"]}}},
         {"type": "function", "function": {
             "name": "get_news",
             "description": "Get today's top news for a given topic.",
             "parameters": {"type":"object",
                            "properties":{"topic":{"type":"string"}},
                            "required":["topic"]}}},
     ]

     def run_agent(user_input: str, max_steps: int = 10) -> str:
         """ReAct 主循环——持续调用直到模型不再返回 tool_calls 或触发 max_steps."""
         messages = [{"role": "user", "content": user_input}]
         for step in range(max_steps):
             resp = client.chat.completions.create(
                 model=MODEL, messages=messages, tools=TOOL_SCHEMAS,
             )
             msg = resp.choices[0].message
             messages.append(msg)                            # 关键:assistant 消息先入栈

             if not msg.tool_calls:                          # 正常退出条件:没工具要调
                 return msg.content

             for call in msg.tool_calls:
                 fn   = TOOL_REGISTRY.get(call.function.name)
                 try:
                     args   = json.loads(call.function.arguments)
                     result = fn(**args) if fn else f"unknown tool: {call.function.name}"
                 except Exception as e:                      # 关键:异常写回不 raise
                     result = f"ERROR: {type(e).__name__}: {e}"
                 messages.append({
                     "role": "tool",
                     "tool_call_id": call.id,
                     "content": str(result),
                 })

         return "max_steps exceeded, no final answer"        # guardrail 兜底

     print(run_agent("帮我看下上海今天天气,顺便告诉我科技领域的头条"))
     ```
   - **评分要点**:① 用 `for step in range(max_steps)` 而非 `while True`,防死循环;② 正常退出条件是 `not msg.tool_calls`(模型给 final answer);③ 异常**写回** messages(`role=tool` + ERROR 文本),不 raise;④ 至少要有 `TOOL_REGISTRY` 这层映射,加新工具只改 registry;⑤ `max_steps` 触底也要返回兜底字符串而不是 `None`。

### 九、教学反思要点
- 找茬环节学员通常一片惊呼,务必保留。
- 学员是否真的看到了"两次 create 调用"的必要性?可以加一道反问:"如果不调第二次,用户看到的是什么?"(答:看到一段含 tool_calls 的 raw 数据,没有自然语言回复)。

---

## L9 — 实现完整的 ReAct 循环

### 一、基本信息
- **课时编号**:L9
- **课时时长**:90 分钟
- **课型**:实操(写出可复用的小框架)
- **前置**:L4、L5、L8
- **教具**:`examples/hello-agent/main.py` 风格的项目骨架。

### 二、教学目标
**知识目标**
- 用 `@tool` 装饰器实现工具注册表。
- 完整理解 `max_steps`、`for step in range(...)` 的循环结构。
- 解释为何工具异常要捕获后回填而不是 raise。

**能力目标**
- 把 L8 的"单次调用"扩展成多轮 ReAct 循环。
- 在每步打印 trace,形成最简可观测性。

### 三、教学重点与难点
- **重点**:工具注册表 + 主循环结构。
- **难点**:让代码"既能演示又能复用",避免一锅粥。

### 四、教学准备

**【环境 / 依赖】**
- 继承 L7/L8 venv,无需新装包。
- 讲师本地已完整跑通"3 工具 + 主循环"参考实现 `examples/hello-agent/agent.py`(项目里已有),作为学员卡壳时的对照。

**【代码素材】**
- **半成品 `agent.py`**(学员逐步补全),留 4 处 `TODO`:
  ```
  TODO 1: 定义 TOOL_REGISTRY = {"name": fn, ...} 映射
  TODO 2: 定义 TOOL_SCHEMAS = [ {...}, ... ] JSON schema 列表
  TODO 3: for step in range(max_steps): 主循环
          - client.chat.completions.create
          - if not msg.tool_calls: return msg.content
          - else: 遍历 tool_calls 逐个执行 + 回填
  TODO 4: main() 入口 + argparse 拿 user_input
  ```
- **参考完整版 `agent_complete.py`**(讲师保底,不发给学员,仅在学员卡关或课末对照)。
- **3 个业务函数**(供学员挑用):`get_weather(city)`、`add(a, b)`、`now_time(timezone='UTC')`;都是无副作用的确定性 mock,便于学员现场验证。

**【数据 / 样例】**
- **测试 prompt 分难度 3 档**:
  - 简单(1 步):`"上海现在几点?"` → 应调 `now_time`
  - 中等(2 步):`"上海现在天气 + 时间"` → 应调 2 个 tool
  - 挑战(3 步):`"1+2+3+4 是多少,加上现在的小时数"` → 应调 `add` × 3 + `now_time` + `add`
- **异常 prompt**:`"帮我订张机票"` → 期望模型说"我没有这个工具",而不是编造。

**【教学材料】**
- **4 不变量口诀**(五.3 讲):工具注册、max_steps 兜底、异常写回、final 出口。
- **主循环"12 行代码"板书**(与 M1 L4 对齐),让学员看到:今天补的 `agent.py` 里的循环体,就是 L4 那 12 行伪代码的产物。

**【学员课前】**
- 已跑通 L8 单工具 function calling(一次两 create 调用)。
- 熟悉自己 IDE 的 debugger 或 `print` 大法,今天多步循环出 bug 时快速定位。

**【备用方案】**
- 若学员 IDE 环境卡壳没法本地跑 → 讲师提供 online Colab notebook 或 Codespaces 环境,同 `agent.py` 骨架。
- 若模型总是不肯"多步调工具"(gpt-oss:20b 有时懒惰) → 讲师在 system prompt 里加一行 `"必要时可反复调用工具直到得出最终答案,不要一次性猜结果"`,通常能解决。

### 五、教学过程

#### 1. 导入(5 min)

> 【讲师讲稿】"L8 我们做的是'调一次工具就结束'。但真实任务里,模型可能要调 3 个、5 个工具,顺序不固定,有时候第二个工具的参数还依赖第一个的结果。这意味着我们必须把 L8 的代码升级成**循环**——这就是 ReAct 的本体。今天我们要把这个循环写得**足够通用**,以至于后面所有的 Agent 都可以复用这套骨架。"

---

#### 2. 工具注册表:为什么不能 if/elif(20 min)

**反面写法**(讲师故意写出来再否定):

```python
for call in msg.tool_calls:
    if call.function.name == "get_weather":
        result = get_weather(**args)
    elif call.function.name == "add":
        result = add(**args)
    elif call.function.name == "now_time":
        result = now_time(**args)
    else:
        result = "unknown tool"
```

> 【讲师讲稿】"这种写法在 demo 里能跑,但每加一个工具就要改 if/elif,代码越来越丑,容易漏。我们用一个标准模式:**工具注册表 + 装饰器**,让加工具变成'加一个函数就完了'。"

**正面写法**:

```python
import inspect
from typing import get_type_hints

TOOL_REGISTRY = {}     # name → callable
TOOL_SCHEMAS = []      # OpenAI tools 数组

_TYPE_MAP = {int: "integer", float: "number", str: "string",
             bool: "boolean", list: "array", dict: "object"}

def _build_params(fn):
    """用 inspect 自动把函数签名转成最小 JSON Schema。
    生产可直接用 pydantic 的 TypeAdapter,这里给最小版便于教学理解。
    """
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)
    props, required = {}, []
    for name, p in sig.parameters.items():
        t = hints.get(name, str)
        props[name] = {"type": _TYPE_MAP.get(t, "string")}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}

def tool(description):
    """装饰器:把函数注册成工具"""
    def decorator(fn):
        TOOL_REGISTRY[fn.__name__] = fn
        schema = {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": description,
                "parameters": _build_params(fn),   # 由 inspect 自动推断
            },
        }
        TOOL_SCHEMAS.append(schema)
        return fn
    return decorator

@tool("Get current weather for a city.")
def get_weather(city: str) -> str:
    return f"{city} 25°C 晴"

@tool("Add two numbers and return the sum.")
def add(a: float, b: float) -> float:
    return a + b
```

**讲解**:
- `TOOL_REGISTRY` 把"工具名"映射到"Python 函数",dispatch 阶段一查就知道调谁。
- `TOOL_SCHEMAS` 是给 LLM 看的工具列表,跟着注册表自动维护。
- `@tool("...")` 这种带参数装饰器是 Python 标准模式,可以同时拿到 description 和函数对象。
- `_build_params` 用 `inspect.signature` + `typing.get_type_hints` 读函数签名,把 Python 类型映射到 JSON Schema 类型。**这是最小教学版**:只覆盖 6 个基本类型、不处理 Optional / Union / 嵌套结构;生产里推荐用 pydantic 的 `TypeAdapter(fn).json_schema()` 或 L16 要讲的 FastMCP 自动生成。

> 【讲师讲稿】"这个模式的核心好处:**加工具 = 加一个带装饰器的函数**,不用动主循环代码,不用动 schema 数组。这就是工程上的'开闭原则'——对扩展开放,对修改关闭。"

---

#### 3. 主循环骨架:逐行教学(30 min)

讲师在白板写完整循环:

```python
def run_agent(user_input: str, max_steps: int = 10) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]
    
    for step in range(max_steps):
        # 1) 让模型决策
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=messages,
            tools=TOOL_SCHEMAS,
        )
        msg = resp.choices[0].message
        messages.append(msg)                # 先入栈 assistant 消息

        # 2) 简易 trace
        print(f"[step {step}] "
              f"tool_calls={[c.function.name for c in (msg.tool_calls or [])]} "
              f"content={(msg.content or '')[:80]}")

        # 3) 没有 tool_calls → final answer
        if not msg.tool_calls:
            return msg.content

        # 4) 执行每个 tool_call,捕获异常
        for call in msg.tool_calls:
            fn = TOOL_REGISTRY.get(call.function.name)
            if fn is None:
                result = f"ERROR: unknown tool {call.function.name}"
            else:
                try:
                    args = json.loads(call.function.arguments)
                    result = fn(**args)
                except Exception as e:
                    result = f"ERROR: {type(e).__name__}: {e}"
            
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": str(result),
            })
    
    return "[max steps reached without final answer]"
```

**逐行讲三件最重要的事**:

**(1) `max_steps` 的位置**:`for step in range(max_steps)` 是 Agent 的保险丝。任何情况下,循环最多跑 `max_steps` 次。`max_steps = 10` 是经验值——大多数任务 3~5 步就够,10 步给点缓冲。

**(2) 异常捕获后回填**:`try/except` 不是为了"让程序不崩",而是为了**让模型看到错误**。比如 `add("abc", 1)` 会抛 `ValueError`,我们把它转成 `"ERROR: ValueError: ..."` 回填,模型读到后会自我修正——可能再调一次 `add(1, 2)`,或者直接告诉用户"参数格式错误"。

> 【讲师讲稿】"这就是 Agent 的'自愈'魔法——**只要错误信息能回到 LLM 眼里,它就有机会自己改正**。如果你直接 raise,整个 Agent 就死了,白白浪费前面 N 步的工作。所以请大家牢记:**工具内部异常,一律捕获回填,不要让它冒泡**。**LLM 层异常**(API 不可达等)才可以根据策略 retry 或 raise,这是 L11 的内容。"

**(3) 简易 trace**:每步打印一行,包含 step_idx、tool_calls 名字、content 前 80 字。**这是 0 成本的可观测性**,比啥都没有强 100 倍。L30 我们会接 Langfuse,但即使没接,这一行 print 也能救命。

---

#### 4. 学员跟练 + 加新工具(20 min)

任务:基于讲师给的骨架,加入 3 个工具:`add`、`mul`、`now_time`。

测试输入:`"(12 + 8) * 3 是多少?现在几点?"`

期望:模型分多步调用 add → mul → now_time,最终给出"60,现在 UTC 时间是 ..."。

助教验收点:
- 每步 trace 打出来了。
- 工具异常时(故意输入 `add("a", 1)`)能回填错误并自愈。
- max_steps 设置成 5 时,故意构造一个永远不结束的任务,验证返回兜底字符串。

---

#### 5. 测查 + 小结(15 min)

**测查(10 min)**:
1. 投影第八节 3 道选择题,**学员举手抢答**(30 秒思考),公布答案后讲师针对每题陷阱**点 1~2 句**——特别第 2 题 "max_steps 过大风险" 是新手最容易忽视的"死循环烧钱"陷阱。
2. **简答 + 场景题**(第 4、5 题)分两组讨论 3 分钟,代表口头作答。**编程题(第 5 题)**讲师把 system prompt 模板投影出来,让学员复制粘贴尝试。

**小结(5 min)**:讲师投影 "今天必须带走的 3 句话":

> **今天必须带走的 3 句话**:
> 1. **工具注册表 = `dict[name, callable]`**——加新工具只改字典不改主循环,避免长串 `if name == "x": elif ...`,这是 Agent 可扩展性的基础。
> 2. **`max_steps` 是兜底,模型不再返回 `tool_calls` 是正常出口**——两个退出条件必须**同时存在**,缺一个就出大事(无 final = 死循环;无 max_steps = 烧钱)。
> 3. **工具异常一律写回 messages 而不是 `raise`**——让 LLM 看到错误并自我修正,这是 Agent "自愈能力"的本质;`raise` 等于杀死 Agent,前面 N 步白做。

> 【讲师讲稿】"今天敲的 100 行主循环就是后面所有模块的'本体'——M3 上 MCP 在它外面加工具源,M4 加持久化记忆,M5 把循环升级为状态图,M6 加 guardrail / HITL / trace。这个循环的 4 个不变量(工具注册、max_steps 兜底、异常写回、final 出口)请记到肌肉里,以后看任何 Agent 代码先找这 4 段。"

#### 6. 作业(5 min)
- 给主循环加上 system prompt,要求"调用工具前先简短解释意图、不确定时宁可调工具也不要编"。

**参考答案(sample system prompt)**:

```python
SYSTEM = """You are a helpful assistant with access to tools.

Tool-use policy:
1. **Before calling any tool, briefly state your intent in 1 sentence**, e.g.
   "I'll call get_weather to check Shanghai's weather."
2. **When uncertain, prefer calling a tool over guessing.** Never fabricate facts
   (timestamps, weather, prices, names) you can verify with a tool.
3. If no tool fits, say so explicitly and ask the user for more info — **do not
   make up an answer**.
4. After tool results return, **read them before next action**. If a tool returned
   an ERROR, decide whether to retry with different args, try a different tool,
   or give up and tell the user.
5. Keep final answers concise and grounded in tool outputs.
"""

def run_agent(user_input: str, max_steps: int = 10) -> str:
    messages = [
        {"role": "system", "content": SYSTEM},            # ← 关键:加在 user 之前
        {"role": "user",   "content": user_input},
    ]
    # ... 主循环逻辑不变(参考 L9 完整代码)
```

**评分要点**:
1. 显式要求"调工具前先说意图"(让 trace 可读,debug 时大量受益);
2. 显式禁止 "fabricate"(直接降低幻觉率 30%+,这是 OpenAI cookbook 推荐做法);
3. 显式说明对 ERROR observation 的处理策略(让模型自愈而非无脑重试);
4. 用英文写 system 通常比中文 token 少 30%~50%,**但**要 keep concise——过长 system prompt 会"稀释"注意力。

### 六、板书设计
```
工具注册表
  @tool("desc") def fn(...) →  TOOL_REGISTRY[fn.__name__] = fn
                                TOOL_SCHEMAS.append(schema)

主循环
  for step in range(max_steps):
      msg = llm(messages, tools=TOOL_SCHEMAS)
      messages.append(msg)              ← 先 append
      print(trace)
      if not msg.tool_calls: return msg.content
      for call in msg.tool_calls:
          try: result = TOOL_REGISTRY[name](**json.loads(args))
          except Exception as e: result = f"ERROR: {e}"
          messages.append({role=tool, tool_call_id, content})
  return "[max steps]"
```

### 七、课堂练习(完整发放版)

> 讲师提示:本节练习重点在"把 L8 的一次两 call 升级成完整 ReAct 主循环"。学员基于 L7-L8 hello-agent 环境,补全 4 处 TODO,通过 3 个 prompt 验收。总时长 30-40 分钟。

#### 练习 1:补全 `agent.py` 4 处 TODO(30 min,个人)

**任务**:下面骨架代码留了 4 处 `# TODO`。补全后跑 3 个 prompt 全部通过验收。

**骨架代码 `agent.py`**:
```python
import json, os
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

load_dotenv()
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL") or None,
)
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")

# ============ 工具实现 ============
def get_weather(city: str) -> str:
    return f"{city} 今天晴,25°C"

def add(a: int, b: int) -> int:
    return a + b

def now_time(timezone: str = "UTC") -> str:
    try:
        return datetime.now(ZoneInfo(timezone)).isoformat(timespec="seconds")
    except ZoneInfoNotFoundError:
        return f"[ERROR] unknown timezone: {timezone}"

# ============ TODO 1:注册表 ============
# 建立 name → callable 的映射
REGISTRY = {
    # TODO
}

# ============ TODO 2:tool schemas ============
TOOLS = [
    # TODO:为 get_weather / add / now_time 各写一份 schema(schema 完整,description 完整)
]

# ============ TODO 3:主循环 ============
def run(user_input: str, max_steps: int = 6) -> str:
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Use tools when needed."},
        {"role": "user", "content": user_input},
    ]
    for step in range(max_steps):
        # TODO 3a:调 LLM,取 msg
        # TODO 3b:if 无 tool_calls → return msg.content
        # TODO 3c:messages.append(msg) 然后遍历每个 tool_call,执行,回填 role=tool 消息
        pass
    return "[max_steps exceeded]"

# ============ TODO 4:main ============
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("query", nargs="?", default="上海现在几点?")
    args = p.parse_args()
    print(run(args.query))
```

**3 个验收 prompt**:

| # | prompt | 期望行为 |
| - | ------ | -------- |
| 1 | `"上海现在几点?"` | 1 步:调 `now_time("Asia/Shanghai")` → final |
| 2 | `"1+2+3+4 是多少"` | 3-4 步:多次调 add 累加 → final |
| 3 | `"北京天气怎么样,现在几点"` | 1-2 步:一次返 2 个 tool_call,或分 2 步各调 1 次 |

**运行命令**:
```bash
python agent.py "上海现在几点?"
python agent.py "1+2+3+4 是多少"
python agent.py "北京天气怎么样,现在几点"
```

**验收 checklist**:
- [ ] 3 个 prompt 都能给出**看起来合理**的 final 回答
- [ ] `messages` 里 tool 结果都用 `role="tool"` + `tool_call_id` 回填
- [ ] `max_steps=6` 兜底生效(可以故意问一个绕的问题验证)
- [ ] tool 抛 error 时不整体崩(比如问"上海时区拼错"),会**继续把 error 回填给 LLM**
- [ ] 打印每步的 `(step, tool_name, args)` 便于观察循环

**参考答案(核心循环)**:
```python
REGISTRY = {"get_weather": get_weather, "add": add, "now_time": now_time}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city. Use when the user asks about weather/temperature/conditions. Params: city (str).",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add",
            "description": "Add two integers. Use for any arithmetic addition — do NOT compute in your head. Params: a, b (int).",
            "parameters": {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "now_time",
            "description": "Current time in ISO 8601 for a timezone. Use when user asks 'now/current time'. Params: timezone (IANA str, default 'UTC').",
            "parameters": {
                "type": "object",
                "properties": {"timezone": {"type": "string"}},
                "required": [],
            },
        },
    },
]

def run(user_input: str, max_steps: int = 6) -> str:
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Use tools when needed. Never guess time or math — call the tools."},
        {"role": "user", "content": user_input},
    ]
    for step in range(max_steps):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content
        for call in msg.tool_calls:
            fn = REGISTRY.get(call.function.name)
            if fn is None:
                result = f"[ERROR] unknown tool: {call.function.name}"
            else:
                try:
                    args = json.loads(call.function.arguments)
                    result = fn(**args)
                except Exception as e:
                    result = f"[ERROR] {type(e).__name__}: {e}"
            print(f"  step {step+1}: {call.function.name}({call.function.arguments}) → {str(result)[:60]}")
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": str(result),
            })
    return "[max_steps exceeded]"
```

**常见坑**:
- 忘了 `messages.append(msg)` 就跑 tool → 报 `'tool' message without preceding 'assistant' with tool_calls`
- tool 抛异常直接 raise → 整个 run 崩;应捕获再当 result 回填,让 LLM 自己判断怎么办
- 3 个工具都注册但没在 TOOLS 数组里 → LLM 看不到 schema,永远不会选
- system prompt 里没提示 "别口算" → 简单加减 LLM 常常自己算(错)不调工具

**挑战延伸(选做)**:
- 加一个 `convert_currency(amount, from_ccy, to_ccy)` 工具(mock 数据即可),测 `"100 美元换人民币"` 是否正确调用
- 增强 prompt:让 Agent 每次给 final 之前先说一句 "已完成 X 步" 便于观察循环深度
- 支持交互模式:`python agent.py`(无 argv 时进入 REPL,可持续输入)

### 八、测查题与参考答案

1. 工具注册表(tool registry)的目的是?  A. 缓存工具的执行结果  **B. 把"工具名 → 函数"解耦,便于动态分发与扩展**  C. 限制工具数量  D. 提升模型推理速度 → **B**。注册表本质是 `dict[name, callable]`,加新工具只改字典不改主循环,避免长串 `if/elif`。
2. `max_steps` 设得过大有什么风险?  A. 模型记忆变差  **B. 死循环烧钱(token 持续累积)+ 占用资源 + 噪音 trace**  C. 工具会被禁用  D. 模型上下文反而变小 → **B**。`max_steps` 是 Agent 的"安全带",通常 3~10 步;过大或不设会被模型卡死在某个工具上无限重试。
3. Agent 主循环正常退出条件是?  A. 模型 temperature 为 0  **B. 模型返回不再包含 tool_calls(给 final answer)或 已达 `max_steps`**  C. messages 长度超过 100  D. 用户主动中断 → **B**。这两个是"正常"出口,前者是模型"想完了",后者是 guardrail 兜底。
4. **简答**:为什么把工具异常写回 messages 而不是 raise?
   - **参考答案**:让 LLM 看见错误信息,它可以决定换工具/换参数/自我修正;raise 终止整个 Agent,丧失自愈能力,前面 N 步白做。
5. **编程**:加 system prompt "不确定时宁可调工具不要编"。
   - **参考答案**:
     ```python
     SYSTEM_PROMPT = (
         "你是严谨的助手。规则:"
         "1. 涉及事实(时间、天气、数据)必须调工具核实,禁止编造。"
         "2. 调用工具前用一句话说明意图。"
         "3. 工具失败时,先尝试换参数,如多次失败请告知用户。"
     )
     messages = [{"role":"system","content":SYSTEM_PROMPT},
                 {"role":"user","content":user_input}]
     ```

### 九、教学反思要点
- 学员能否独立写出 `@tool` 装饰器?可以让 1~2 人上台讲。
- 跟练时间够吗?如果不够,把"加新工具"留作课后。
- "异常捕获后回填"的 mindset 是 Agent 工程的核心之一,务必反复强调。

---

## L10 — 多工具组合调用与并行 tool_calls

### 一、基本信息
- **课时编号**:L10
- **课时时长**:90 分钟
- **课型**:实操 + 并发概念
- **前置**:L9
- **教具**:`asyncio` 演示脚本、一段"故意只取 tool_calls[0]"的反面代码。

### 二、教学目标
**知识目标**
- 解释一次响应可能返回多个 `tool_calls`(并行)的设计意图。
- 区分串行依赖 / 并行无依赖 / 条件分支 三类组合模式。

**能力目标**
- 写出"循环遍历所有 tool_calls + 全部回填"的代码。
- 用 `asyncio.gather` 或线程池把并行工具调用并发执行,带超时。

### 三、教学重点与难点
- **重点**:遍历**全部** tool_calls;并行执行模式。
- **难点**:让学员理解"并行不能有副作用依赖"。

### 四、教学准备

**【环境 / 依赖】**
- 继承 L9 环境。**新增**验证:`from openai import AsyncOpenAI` 能 import(openai ≥ 1.30 都有,课前 `pip show openai` 确认)。
- Python 版本需 ≥ 3.9 支持 `asyncio.to_thread`;3.10+ 语法糖更好。

**【代码素材】**
- **反面代码 `L10_only_first.py`**:故意在处理 tool_calls 时只取 `msg.tool_calls[0]`,导致模型请求 3 个 tool 却只跑 1 个 —— 症状:第二次 chat.completions.create 报 "tool_call_id X was not returned"。
- **同步串行版 `L10_sync.py`**:for 循环挨个跑 3 个 tool,每个 sleep 2s,总耗时 ~6s。
- **异步并发版 `L10_async.py`**:`asyncio.gather(*[run_tool(t) for t in tool_calls])`,同 3 个 tool 每个 2s,总耗时 ~2s。**课上并排跑,秒表可视化对比**。
- **`asyncio.gather` 最小示例**(教学第一次接触 asyncio 的学员用),10 行:定义 3 个 `async def sleep_n(n)`,用 `gather` 并发,对比串行。
- **同步 tool 混用示例**:用 `asyncio.to_thread(sync_fn, args)` 把 sync tool 包成 awaitable,防止阻塞 event loop。

**【数据 / 样例】**
- **多工具触发 prompt**:`"帮我同时查北京、上海、深圳三地天气"` —— 大概率一次返 3 个 tool_calls,是本课的黄金演示 prompt。
- **性能表**准备好格式,课上现场填写:
  | 版本 | 3 tool 耗时 | LLM 调用次数 | 说明 |
  | ---- | ---- | ---- | ---- |
  | 串行 | ~6s | 2 | for 逐个跑 |
  | 并发 | ~2s | 2 | gather 并发 |

**【教学材料】**
- **"并行 3 原则"板书**(五.3 讲):① 只并行 tool 不并行 LLM ② tool 必须无副作用依赖 ③ tool_calls 的 id 顺序必须严格对齐回填。
- **副作用依赖反例**:`create_file(A)` 和 `read_file(A)` 并发 —— 读操作可能在写之前完成,读到空。这类场景必须串行。

**【学员课前】**
- 已能一次 tool_calls 里返 2 个 tool 的 prompt 心里有底(L9 挑战版已练)。
- (可选)看 5 分钟 asyncio 官方教程 "Coroutines and Tasks" 前半段,建立协程直觉。

**【备用方案】**
- 若学员对 asyncio 完全零基础,现场跟不上 → 用**`concurrent.futures.ThreadPoolExecutor` + `map`** 版本替代作为过渡,同样能并发,语法更接近同步思维。
- 若 gpt-4.1 不肯一次返多个 tool_call(单调倾向) → 换 `gpt-4o` 或 Claude Sonnet,或在 prompt 里明写 "如需查多城市,请一次性返回多个 tool_call"。

### 五、教学过程

#### 1. 导入:让模型一次想调多个工具(5 min)

讲师现场跑一个 prompt:`"对比北京和上海今天的天气"`。

> 【讲师讲稿】"看见没?模型一次性返回了 2 个 tool_calls——一个查北京,一个查上海。它意识到这两件事**互不依赖**,所以一次就规划好了。这是 OpenAI 自 GPT-4 Turbo 起支持的特性,叫 **parallel tool calls**。今天我们要把代码改造成支持这种并行,并且学会**真的让它们并发跑**,而不是串行等。"

---

#### 2. 必须遍历**全部** tool_calls(20 min)

**反面代码**(讲师故意写):
```python
call = msg.tool_calls[0]     # ← 只取第一个!
result = TOOL[call.function.name](**json.loads(call.function.arguments))
messages.append({"role":"tool", "tool_call_id":call.id, "content":str(result)})
```

讲师跑这段反面代码,然后跑第二次 LLM。**会发生什么**?
- 第二次 LLM 看到 messages 里有 2 个 tool_calls 但只有 1 个 tool 结果。
- OpenAI API 直接报错:`messages with role 'tool' must respond to a preceeding message with 'tool_calls'`,或者模型行为混乱。

> 【讲师讲稿】"OpenAI 的硬规则是:**一个 tool_calls 列表里有 N 个 call,你就必须回填 N 个 tool 消息,一一对应,缺一不可**。少回一个就报错或者让模型疯掉。所以正确代码永远是 `for call in msg.tool_calls`,**没有捷径**。"

**正面代码**(L9 已经写过):
```python
for call in msg.tool_calls:
    ...
    messages.append({"role":"tool","tool_call_id":call.id,"content":str(result)})
```

---

#### 3. 串行 vs 并行 vs 条件分支(20 min)

**三种组合模式的本质区别**:

| 模式 | 例子 | 谁决定顺序 | 实现 |
|---|---|---|---|
| **并行无依赖** | 同时查北京、上海、广州天气 | LLM 在一次响应里同时给出多个 tool_calls | `asyncio.gather` 并发执行 |
| **串行依赖** | 先 `search("OpenAI 财报")` → 再 `fetch_url(第一条结果)` → 再 `summarize` | LLM **跨轮**决定:第一轮调 search,第二轮基于结果调 fetch_url,第三轮调 summarize | 一次循环只处理一轮 tool_calls,跨循环自然串行 |
| **条件分支** | 先 `get_user_role`,根据结果决定调 `admin_tool` 还是 `user_tool` | LLM 跨轮基于上一步结果决定 | 同串行依赖 |

> 【讲师讲稿】"请大家注意——**串行 vs 并行不是你在代码里硬选的,是 LLM 自己决定的**。LLM 觉得几件事互不依赖,就一次性返回多个 tool_calls(并行);它觉得有依赖,就分多轮(串行)。你的代码只要支持'一次循环里遍历多个 tool_calls'就够了,剩下的让模型自己规划。"

**反模式**:**并行执行有副作用依赖的工具**。
- 例如:并行调用 `write_file("a.txt", x)` 和 `read_file("a.txt")`——结果不可预期。
- 例如:并行调两次同样的"扣减库存"API——可能扣两次。
- **怎么办**:在 tool description 里明确告诉模型"这个工具有副作用,请不要与 X 同时调"。或者在代码层用锁串行化。

---

#### 4. 用 asyncio 让并行工具真的并发跑(25 min)

**问题**:即使 LLM 返回 5 个并行 tool_calls,如果你的代码是 `for call: result = fn(...)` 串行执行,总耗时 = 5 个工具耗时之和,没省时间。

**解决**:用 `asyncio.gather` 并发。

讲师写改造代码:

```python
import asyncio
from openai import AsyncOpenAI                  # 注意:async 版必须用 AsyncOpenAI,不能用同步 OpenAI
import os
from dotenv import load_dotenv
load_dotenv()

api_key  = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL") or None
assert api_key, "未读到 OPENAI_API_KEY"
client = AsyncOpenAI(api_key=api_key, base_url=base_url)
MODEL  = os.getenv("OPENAI_MODEL", "gpt-4.1")

async def run_one_call(call):
    fn = TOOL_REGISTRY.get(call.function.name)
    try:
        args = json.loads(call.function.arguments)
        if asyncio.iscoroutinefunction(fn):
            result = await asyncio.wait_for(fn(**args), timeout=10)
        else:
            result = await asyncio.to_thread(fn, **args)
    except asyncio.TimeoutError:
        result = "ERROR: tool timeout, try smaller scope"
    except Exception as e:
        result = f"ERROR: {type(e).__name__}: {e}"
    return {
        "role": "tool",
        "tool_call_id": call.id,
        "content": str(result),
    }

async def run_agent_async(user_input, max_steps=10):
    messages = [{"role": "user", "content": user_input}]
    for step in range(max_steps):
        resp = await client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOL_SCHEMAS
        )
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content
        results = await asyncio.gather(*[run_one_call(c) for c in msg.tool_calls])
        messages.extend(results)
    return "max_steps exceeded"

# 入口:asyncio.run(run_agent_async("同时查北京、上海、深圳天气并比较"))
```

**讲解**:
- `asyncio.gather`:把 N 个协程同时跑,等全部完成,顺序返回结果。
- `asyncio.wait_for(..., timeout=10)`:给每个工具 10 秒上限,防止某个慢工具拖垮全局。
- `asyncio.to_thread`:同步函数(如阻塞的 `requests.get`)放到线程池里跑,避免堵 event loop。
- 超时 / 异常都转成 `"ERROR: ..."` 文本回填,**保持 Agent 自愈**。

**学员实操**:把自己 L9 的代码改成 async 版,跑一个"同时查 3 个城市天气"的任务,记录改造前后耗时对比。

> 【讲师讲稿】"通常你能看到:改造前总耗时 3 秒(3 个工具各 1 秒),改造后总耗时 1 秒。**这就是并发的价值**。但请注意,如果你的工具都很快(<100ms),并发收益就不明显,反而引入异步复杂度。所以**先观察热点再优化**——这是 L35 的核心思想。"

---

#### 5. 测查 + 小结(15 min)

**测查(10 min)**:
1. 投影第八节 3 道选择题,**学员举手抢答**(30 秒思考),公布答案后讲师针对每题陷阱**点 1~2 句**——尤其第 3 题"串行依赖由 LLM 跨轮自决"是 90% 学员的盲点,他们以为"代码硬编码顺序",其实是模型看到 obs 后动态决策。
2. **简答 + 场景题**(第 4、5 题)分两组讨论 3 分钟。**场景题**讲师把"先 search → 拿 3 个 URL → 并行 fetch → 汇总"的混合实现在白板上手画一遍,巩固"一次循环并发 + 跨轮依赖"的双层模型。

**小结(5 min)**:讲师投影 "今天必须带走的 3 句话":

> **今天必须带走的 3 句话**:
> 1. **一次响应多个 `tool_calls` = 模型在并行规划**——用 `asyncio.gather` 一次并发跑,前提是**工具间无依赖**(B 不需要 A 的结果)。
> 2. **有依赖的工具让 LLM 跨轮自决调用顺序**——这是 Agent 与 Workflow 的本质区别,不是代码硬编码顺序。
> 3. **每个并发调用加 `asyncio.wait_for(call, timeout=N)`**——一个慢工具(10s)会拖死整体,超时转 `"ERROR: timeout"` 回填让 LLM 决定换路。

> 【讲师讲稿】"今天的并发改造,通常能把 Agent 总耗时从'工具时长 × N'降到'最慢工具时长'——这是上线后用户体验从'慢爆'到'流畅'的关键。L35 我们会讲整体成本与延迟优化,并发是其中最关键的一招。回家把作业的'3 城市天气'跑一遍,截图对比顺序 vs 并发的真实差异。"

#### 6. 作业(5 min)
- 写一个"同时查 3 个城市天气并比较"的任务,提交顺序版 vs 并发版的耗时对比截图。

**参考答案**:

```python
import asyncio, time
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os
load_dotenv()

api_key  = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL") or None
assert api_key, "未读到 OPENAI_API_KEY"
client = AsyncOpenAI(api_key=api_key, base_url=base_url)   # 注意:async 必须 AsyncOpenAI

# 模拟一个"网络慢"的天气工具,故意 sleep 1.5s 模拟真实 API
async def slow_get_weather(city: str) -> str:
    await asyncio.sleep(1.5)
    fake = {"北京":"22°C 多云", "上海":"26°C 雨", "深圳":"30°C 晴"}
    return f"{city} {fake.get(city, '未知')}"

async def seq_run(cities):
    """顺序版:一个一个查"""
    t0 = time.time()
    results = []
    for c in cities:
        results.append(await slow_get_weather(c))
    return results, time.time() - t0

async def par_run(cities):
    """并发版:asyncio.gather"""
    t0 = time.time()
    results = await asyncio.gather(*[slow_get_weather(c) for c in cities])
    return results, time.time() - t0

async def main():
    cities = ["北京", "上海", "深圳"]
    r_seq, t_seq = await seq_run(cities)
    r_par, t_par = await par_run(cities)
    print(f"顺序版结果: {r_seq}")
    print(f"并发版结果: {r_par}")
    print(f"顺序耗时: {t_seq:.2f}s")              # 期望 ~4.5s (1.5×3)
    print(f"并发耗时: {t_par:.2f}s")              # 期望 ~1.5s (max)
    print(f"加速比:   {t_seq/t_par:.1f}×")        # 期望 ~3×

asyncio.run(main())
```

**评分要点**:
1. 用 `asyncio.gather` 而非 `for c in cities: await ...`(后者依然串行!);
2. 加速比应接近 N=3(理想 3×,实际 2~3×,因为 event loop 自身有小开销);
3. 输出对比要可读(同时打印两版结果 + 耗时 + 加速比);
4. 真实场景再叠加 `asyncio.wait_for(call, timeout=10)` 防单工具拖死(本课主体代码 L10 五.4 已示范);
5. **常见错误**:用了同步 `OpenAI()` 客户端但调 `await client...`,运行报 `TypeError: object Response can't be used in 'await' expression`——`AsyncOpenAI` 不可省。

### 六、板书设计
```
msg.tool_calls = [c1, c2, ...]   ← 必须遍历全部,缺一报错

并行无依赖:asyncio.gather(*[run(c) for c in msg.tool_calls])
串行依赖:  多轮 ReAct 自然完成(每轮一次循环)
条件分支:  同串行依赖

并行禁忌:有副作用依赖(写同一文件、扣库存等)
超时保护:asyncio.wait_for(..., timeout=N)
同步工具:asyncio.to_thread(fn, **args)
```

### 七、课堂练习(完整发放版)

> 讲师提示:本节练习是把 L9 的串行版改成 async 并发版,量化对比耗时。总时长 30 分钟。学员机需装 openai ≥ 1.30(继承)。

#### 练习 1:async 改造 + 耗时基准测试(25 min,个人)

**任务**:
1. 复制 L9 的 `agent.py` 为 `agent_async.py`
2. 把 `client` 从 `OpenAI` 改成 `AsyncOpenAI`
3. tool 执行改成 `asyncio.gather(*[...])` 并发
4. 加入 3 个 mock 慢 tool,分别 sleep 2s,验证并发效果
5. 分别用 **串行版**(L9) 和 **并发版**(L10) 跑同一个 3-tool prompt,记录耗时

**mock 慢 tool 定义**:
```python
import asyncio, time

async def slow_get_weather(city: str) -> str:
    await asyncio.sleep(2)
    return f"{city} 今天晴,25°C"

async def slow_now_time(timezone: str = "UTC") -> str:
    await asyncio.sleep(2)
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(timezone)).isoformat()

async def slow_add(a: int, b: int) -> int:
    await asyncio.sleep(2)
    return a + b
```

**验收 prompt**(会触发多 tool):
```
"帮我同时查北京、上海、深圳三地天气"
```
LLM 一次应返 3 个 tool_calls。

**期望耗时**:
- 串行版:~ 6s(3 × 2s)
- 并发版:~ 2s(gather 并发)

**骨架代码 `agent_async.py`**:
```python
import asyncio, json, os, time
from dotenv import load_dotenv
from openai import AsyncOpenAI                              # ← 改为 Async

load_dotenv()
client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL") or None,
)
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")

# 上面 slow_* 工具定义 + TOOLS/REGISTRY 略(继承 L9,改成 async)

async def exec_tool_call(call) -> dict:
    fn = REGISTRY.get(call.function.name)
    try:
        args = json.loads(call.function.arguments)
        if asyncio.iscoroutinefunction(fn):
            result = await fn(**args)
        else:
            result = await asyncio.to_thread(fn, **args)     # 同步 tool 也不阻塞
    except Exception as e:
        result = f"[ERROR] {type(e).__name__}: {e}"
    return {"role": "tool", "tool_call_id": call.id, "content": str(result)}

async def run(user_input: str, max_steps: int = 6) -> str:
    messages = [
        {"role": "system", "content": "Use tools. Call multiple tools in parallel when possible."},
        {"role": "user", "content": user_input},
    ]
    for step in range(max_steps):
        resp = await client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content
        # TODO:用 asyncio.gather 并发执行所有 tool_calls,把结果 append 到 messages
        # (顺序必须与 msg.tool_calls 一致,tool_call_id 要对得上)
        pass
    return "[max_steps exceeded]"

if __name__ == "__main__":
    query = "帮我同时查北京、上海、深圳三地天气"
    t0 = time.perf_counter()
    answer = asyncio.run(run(query))
    print(f"耗时 {time.perf_counter()-t0:.2f}s")
    print(answer)
```

**验收 checklist**:
- [ ] `asyncio.gather(*[exec_tool_call(c) for c in msg.tool_calls])` 用了 gather
- [ ] 打印耗时接近 2s(不是 6s)
- [ ] 3 个 tool 结果都正确回填,`tool_call_id` 顺序对齐
- [ ] 用**同一 prompt** 跑串行版,记录耗时对比

**参考答案(核心并发段)**:
```python
tool_results = await asyncio.gather(*(exec_tool_call(c) for c in msg.tool_calls))
messages.extend(tool_results)
```

**性能对比表(填入你的实际结果)**:

| 版本 | 3 tool 耗时 | LLM 调用次数 | 说明 |
| ---- | ---- | ---- | ---- |
| 串行(L9) | ~ 6s | 2 | for 逐个 sleep |
| 并发(L10) | ~ 2s | 2 | gather |

---

#### 练习 2:反面代码找 bug(5 min,个人)

**任务**:下面代码用了 asyncio.gather 但**有隐蔽 bug**,找出并说明:

```python
async def run_buggy(user_input: str) -> str:
    messages = [{"role": "user", "content": user_input}]
    resp = await client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
    msg = resp.choices[0].message
    messages.append(msg)

    tasks = [exec_tool_call(c) for c in msg.tool_calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        messages.append(r)                                    # ← 思考点

    resp2 = await client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
    return resp2.choices[0].message.content
```

**参考答案**:
- Bug:`return_exceptions=True` 让 `gather` 遇到 tool 异常时**把异常对象作为结果返回**,不是 raise。这时 `r` 可能是 `Exception` 实例,直接 `messages.append(r)` 会把 exception 对象丢进 messages,API 会报格式错。
- 修法:
```python
for r in results:
    if isinstance(r, Exception):
        messages.append({"role":"tool","tool_call_id":???,"content":f"[ERROR] {r}"})
        # 但这里 tool_call_id 已经丢了!所以更好做法是让 exec_tool_call 内部就 catch
    else:
        messages.append(r)
```
**更好实践**:让 `exec_tool_call` 内部包 try/except,永远返 dict,`gather` 不用 return_exceptions。这样每个 tool_call_id 都能正确对齐。

**常见坑**:
- `asyncio.gather` 若某个 task 抛异常且没 `return_exceptions`,**其他 task 也会被 cancel**,数据丢失
- tool_call_id 顺序错乱 → 第二次 chat 报"某个 tool_call 没有对应结果"
- 忘了同步 tool 用 `asyncio.to_thread` 包 → 会阻塞 event loop,并发变串行

**挑战延伸(选做)**:
- 加入 timeout:`asyncio.wait_for(exec_tool_call(c), timeout=5)`,超时的 tool 返 `"[TIMEOUT]"`
- 对比:2 个快 tool(1s) + 1 个慢 tool(5s),用 timeout=3s,并发版应该是 5s(等最慢)还是 3s(卡 timeout)?写代码验证

### 八、测查题与参考答案

1. 一次模型响应里返回多个 `tool_calls` 说明什么?  A. 模型在重复选错工具,要在 prompt 里约束  **B. 模型在"并行规划"多个工具,认为它们可同时执行,我们可一次 asyncio.gather 并发跑**  C. 是 SDK 的 bug  D. 必须升级模型版本 → **B**。这是 OpenAI/Anthropic 现代模型主动的优化——能并行就一次给多条,等代码并发执行。
2. 一次并行触发多个工具调用的**前提条件**是?  **A. 这几个工具之间没有依赖(B 不需要 A 的结果作输入)**  B. 这几个工具来自同一个 server  C. 所有工具都 `async`  D. 工具参数都为空 → **A**。如果 B 依赖 A 的结果,模型应跨两轮先后调用,而不是一次性给两个 tool_calls。
3. 串行依赖(B 必须用 A 的输出)的调用顺序由谁决定?  A. 由 Python 代码硬编码  B. 由 MCP server 控制  **C. 由 LLM 跨轮自主决定:第 1 轮调 A,看到 obs 后第 2 轮才调 B**  D. 由用户手动指定 → **C**。这是 Agent 比 Workflow 强的地方——执行顺序是 LLM 看到中间结果后动态规划,不是预先写死。
4. **简答**:5 个工具有 1 个超慢(10s),如何避免阻塞?
   - **参考答案**:`asyncio.gather` + `asyncio.wait_for(call, timeout=N)`,超时转 "ERROR: timeout" 回填;让快工具不被慢的拖累。
5. **场景**:"先搜索 → 拿 3 个 URL → 并行 fetch → 汇总" 如何在代码里组织?
   - **参考答案**:**混合**。第 1 轮 LLM 返回单个 `search` tool_call(串行起步);第 2 轮 LLM 看到 search 结果后返回 3 个并行 `fetch_url` tool_calls(一次循环并发处理);第 3 轮 LLM 基于 3 个结果汇总。代码上一次循环处理多 tool_calls、跨轮处理依赖。

### 九、教学反思要点
- 学员对 async 的熟悉度参差,可以为不熟悉的学员准备 `concurrent.futures.ThreadPoolExecutor` 的 fallback。
- 并发耗时对比演示效果震撼,务必保留。
- 副作用依赖的反例需要现场演示一次(用一个"写文件"的工具)。

---

## L11 — 错误处理、重试与超时

### 一、基本信息
- **课时编号**:L11
- **课时时长**:90 分钟
- **课型**:实操 + 故障注入
- **前置**:L9、L10
- **教具**:可被 monkey-patch 注入异常的工具函数;`tenacity` 库(可选)。

### 二、教学目标
**知识目标**
- 区分可恢复错误(429 / 5xx / 网络抖动)与不可恢复错误(401 / 403 / 参数错)。
- 解释指数退避 + 抖动(jitter)的原理。

**能力目标**
- 给 LLM 调用加上重试函数。
- 给工具调用加上超时和异常回填。

### 三、教学重点与难点
- **重点**:错误分类 + "可恢复就 retry,不可恢复就 raise"的原则。
- **难点**:让学员养成"先 wrap 再调"的工程习惯。

### 四、教学准备

**【环境 / 依赖】**
- 继承 L10 环境。**新增装包**:`pip install tenacity`(重试库,课上教业界标准写法)。
- 讲师本地已跑通"3 fake tool + wrap_tool + retry + budget"完整参考实现。

**【代码素材】**
- **3 个 fake 工具**(讲师提供,课上供学员反复触发):
  - `sometimes_fail()`:随机 30% 抛 `TransientError`(可重试),70% 返 `"ok"`
  - `always_slow()`:`time.sleep(30)` 死等,用来演示 timeout 兜底
  - `unauthorized()`:抛 `PermissionError("api key expired")`(不可重试)
- **`wrap_tool` 装饰器版本 2 个**(五.3、5.4 用):
  - 版本 A:纯 `try/except` 手写,便于学员理解每一行做什么
  - 版本 B:用 `tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential(1,10), retry=retry_if_exception_type(TransientError))`,教业界写法
- **成本追踪 `CostTracker` 类**(五.5 讲 budget guardrail),约 20 行:in_tokens/out_tokens 累加 + `if total > MAX_TOTAL_COST: raise BudgetExceeded`。
- **timeout 示例**:用 `asyncio.wait_for(coro, timeout=5)` 包 `always_slow()`,预期 5s 后 TimeoutError。

**【数据 / 样例】**
- **触发场景 prompt**:
  - `"请多试几次调用 sometimes_fail 工具直到成功"` → 演示 retry 起作用
  - `"帮我调用 always_slow 工具"` → 演示 timeout 保护
  - `"请调用 unauthorized 工具 10 次"` → 演示"不可重试"直接失败并停下
- **budget 演示**:MAX_TOTAL_COST 设置 $0.01 小值,让循环几步就触发 `BudgetExceeded`。

**【教学材料】**
- **异常分类板书**(五.2 讲):TransientError(网络/429)→ 重试 / DomainError(参数/权限)→ 不重试直接告诉 LLM / SystemError(OOM/进程)→ 直接崩不掩盖。
- **retry 3 要素**:指数退避 + jitter + 上限。举反例"固定 1s 重试 100 次"会打垮下游。
- **"先 wrap 再调"口诀**:每个 tool 函数必须先经过 `wrap_tool(...)` 才能进 REGISTRY,禁止裸函数注册。

**【学员课前】**
- L9 的 hello-agent 已能跑主循环,今天要把 tool 逐个套 `wrap_tool`。
- 想清楚"如果自己的 Agent 一夜跑了 $100 账单,你想加什么护栏?" —— 5.5 讨论用。

**【备用方案】**
- 若 tenacity 装不上(内网 pip 挂) → 手写 20 行 exponential backoff + jitter 替代,反而更教学。
- 若学员看不出 retry 起作用(30% 抛错概率有时连续成功)→ 把 sometimes_fail 抛错率临时改到 80%,一定能触发。

### 五、教学过程

#### 1. 导入(5 min)

讲师故意把 L10 的 Agent 跑一遍,在某轮 monkey-patch LLM 客户端让它抛 `RateLimitError`。Agent 崩了。

> 【讲师讲稿】"看见没?平时跑得好好的 Agent,API 那边一抖,整个 Agent 直接死了。生产环境里这种 429、500、网络超时是家常便饭,不能让 Agent 这么脆弱。今天我们要把'**遇到错就死**'升级成'**遇到错就重试/降级/告警**'。"

---

#### 2. 错误分类(15 min)

**核心矩阵**:

| 错误类型 | 是否可恢复 | 处理 |
|---|---|---|
| **LLM API 端**:429 (RateLimit) | 是 | 指数退避重试 |
| **LLM API 端**:5xx | 是 | 指数退避重试 |
| **LLM API 端**:连接超时 | 是 | 重试 + 检查网络 |
| **LLM API 端**:401 / 403 | **否** | 立即中止 + 报警(密钥错/欠费) |
| **LLM API 端**:400(参数错) | **否** | 立即中止,代码 bug |
| **工具端**:网络抖动 | 是 | 工具内部重试(transparent),或回填错误让 LLM 重试 |
| **工具端**:参数不合法 | 是(由 LLM 修) | 回填错误让 LLM 改参数 |
| **工具端**:权限不足 | **否** | 回填错误并标记 "不可恢复",LLM 应放弃此路径 |
| **工具端**:超时 | 是 | 回填 "timeout" 让 LLM 改策略(如换更小范围) |
| **工具端**:死循环/资源耗尽 | 是 | 超时强杀 + 回填 |

> 【讲师讲稿】"分类原则很简单:**问题是临时的、有理由相信下次会成功 → 可恢复,重试**;**问题是结构性的、再试也不会变 → 不可恢复,中止**。401 是密钥错,你重试一万次也是错;429 是限流,等一会儿就好。这俩在 except 里要分开处理。"

---

#### 3. 重试函数:指数退避 + 抖动(20 min)

**手写版**:

```python
from openai import APIError, RateLimitError, APITimeoutError, AuthenticationError
import time, random

def llm_call_with_retry(messages, tools, max_retry=4):
    for i in range(max_retry):
        try:
            return client.chat.completions.create(
                model="gpt-4.1", messages=messages, tools=tools
            )
        except AuthenticationError:
            raise   # 不可恢复,直接中止
        except (RateLimitError, APITimeoutError, APIError) as e:
            if i == max_retry - 1:
                raise   # 最后一次仍失败,放弃
            wait = (2 ** i) + random.uniform(0, 1)
            print(f"[retry {i+1}/{max_retry}] {type(e).__name__}, sleep {wait:.1f}s")
            time.sleep(wait)
    raise RuntimeError("unreachable")
```

**逐部分讲**:

- **`except AuthenticationError: raise`**:不可恢复错误第一个 catch,立即向上抛。
- **`except (RateLimitError, APITimeoutError, APIError)`**:可恢复错误,进入重试逻辑。
- **`wait = 2 ** i + random.uniform(0, 1)`**:指数退避公式。第 1 次等 ~1s,第 2 次 ~2s,第 3 次 ~4s,第 4 次 ~8s。
- **抖动(jitter)`+ random.uniform(0, 1)`**:为什么要抖?

> 【讲师讲稿】"想象一下:10 个客户端同时被限流,它们都用相同的退避公式,**会同时在第 1s、第 2s、第 4s 重试**——这就是'惊群'。本来 1 秒能放行 5 个,结果 10 个同时来,继续限流。加抖动后,每个客户端等的时间略有不同,自然错开,系统更平稳。这是后端工程的基础技巧,不止 Agent,任何重试都要加。"

**库版**(更省力):
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIError)),
    reraise=True,
)
def llm_call(messages, tools):
    return client.chat.completions.create(model=..., messages=messages, tools=tools)
```

---

#### 4. 工具调用层的超时与异常回填(20 min)

L10 已经写过 `run_one_call`(每个 tool_call 的安全执行函数),讲师这里强调两点:

**(1) 超时**:用 `asyncio.wait_for` 或同步版的 `signal` / 线程池超时。

**(2) 异常类型映射**:
- `TimeoutError` → `"ERROR: tool timeout, try smaller scope"`
- `ValueError` / `TypeError` → `"ERROR: invalid args: ..."`(让 LLM 改参数重试)
- `PermissionError` → `"ERROR: unauthorized, do not retry this path"`(暗示 LLM 放弃)
- 其他 → `"ERROR: <type>: <msg>"`

> 【讲师讲稿】"我特别想强调权限错误这一类——你不希望 LLM 反复尝试一个它没权限的操作,**应该在错误信息里明确告诉它 'do not retry'**,模型读到后就会换思路。这是个小技巧,大幅减少无效重试。"

---

#### 5. 故障注入实操(20 min)

讲师给学员 3 个 fake 工具:`sometimes_fail`、`always_slow`、`unauthorized`。

学员要做的:
1. 把 L9 的 `run_agent` 加上 `llm_call_with_retry`(LLM 层重试),以及 L10 的 `run_one_call`(工具层超时 + 异常回填)。
2. 跑包含这 3 个工具的任务,观察日志:
   - `sometimes_fail` 第 1 次失败 → 重试成功。
   - `always_slow` → 触发超时,回填后 LLM 换工具。
   - `unauthorized` → 回填 "do not retry",LLM 放弃。
3. 跑预算超限版:加 `BudgetExceeded` 异常,演示主流程在超限时优雅退出。

---

#### 6. 测查 + 小结(10 min)

**测查(7 min)**:投影第八节 3 道选择题,**学员举手抢答**(30 秒思考),公布答案后讲师针对每题陷阱**点 1 句**——重点强调第 3 题 "401/403 不应重试",这是大量新手"无脑重试"账户被风控封禁的根因。简答与场景题作为课后练习。

**小结(3 min)**:讲师投影 "今天必须带走的 3 句话":

> **今天必须带走的 3 句话**:
> 1. **可恢复 vs 不可恢复 errors 要分类处理**:`429` / 网络抖动 / `5xx` → 指数退避 + jitter 重试;`401` / `403` / 参数错误 → 立刻 fail-fast 别重试。
> 2. **工具异常一律以 `role=tool` 写回 messages**——让 LLM 决定换工具 / 换参数 / 放弃,这是 Agent "自愈能力"的本质,不要用 `raise` 把 Agent 杀掉。
> 3. **预算守卫(`MAX_TOTAL_COST`)与 `max_steps` 一样必备**——没有它,Agent 死循环时账单 5 分钟能爆 $100,这是真实生产事故。

> 【讲师讲稿】"今天讲的重试、超时、预算守卫,加在 L9 主循环上,Agent 就从'demo 玩具'变成'能上生产的雏形'。M6 的 guardrail 会再加一层(prompt injection、HITL、access control),但今天这三层是地基。回家把作业的 `BudgetExceeded` 加上,trace 里看到每步累积成本——这就是 M6 Langfuse 想给你看的东西的最简版。"

#### 7. 作业(5 min)
- 给自己的 Agent 加一个 `MAX_TOTAL_COST = 0.10` 守卫,超额抛 `BudgetExceeded`。在 trace 里打印每步累积成本。

**参考答案**:

```python
MAX_TOTAL_COST   = 0.10   # USD,触底抛出
PRICE_PER_1M_IN  = 2.0    # gpt-4.1 input  $2 / 1M tok (2026-06,见 L2 价格表)
PRICE_PER_1M_OUT = 8.0    # gpt-4.1 output $8 / 1M tok

class BudgetExceeded(Exception):
    """超过本次任务预算上限,Agent 主动停止避免账单失控."""

def call_cost(usage) -> float:
    """SDK 返回的 usage 字段 → 这次调用花费 USD."""
    return (usage.prompt_tokens     / 1_000_000) * PRICE_PER_1M_IN \
         + (usage.completion_tokens / 1_000_000) * PRICE_PER_1M_OUT

def run_agent(user_input: str, max_steps: int = 10) -> str:
    messages   = [{"role":"user","content":user_input}]
    total_cost = 0.0
    for step in range(max_steps):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOL_SCHEMAS)
        c = call_cost(resp.usage)
        total_cost += c
        # trace 打印——每步可观察
        print(f"[step {step}] in={resp.usage.prompt_tokens:5d} out={resp.usage.completion_tokens:4d} "
              f"cost=${c:.4f}  total=${total_cost:.4f}")
        if total_cost > MAX_TOTAL_COST:
            raise BudgetExceeded(
                f"total ${total_cost:.4f} exceeded budget ${MAX_TOTAL_COST}, "
                f"messages={len(messages)}, step={step}"
            )
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content
        for call in msg.tool_calls:
            fn = TOOL_REGISTRY.get(call.function.name)
            try:
                args   = json.loads(call.function.arguments)
                result = fn(**args) if fn else f"unknown tool: {call.function.name}"
            except Exception as e:
                result = f"ERROR: {type(e).__name__}: {e}"
            messages.append({"role":"tool", "tool_call_id":call.id, "content":str(result)})
    return "max_steps exceeded"

# 触发预算守卫的示例:让 Agent 进入死循环工具调用
try:
    run_agent("请反复调 get_weather 50 次,然后告诉我结果")
except BudgetExceeded as e:
    print(f"💸 预算守卫触发: {e}")
```

**评分要点**:
1. `total_cost` 每 step 累加并打印(可观察,而不是只在最后报错);
2. **超额抛 `BudgetExceeded` 而不是 return None / `print` 后继续**(让上层调用方明确处理);
3. 价格表用变量管理(`PRICE_PER_1M_IN/OUT`),模型换价时只改 1 处;
4. 异常信息带上 `total_cost` / `messages 数` / `step`,便于事故复盘;
5. 真实生产再叠加**软上限告警**:80% 时 Slack 告警,100% 时 raise(单向硬阻止 +  早期感知)。

### 六、板书设计
```
分类
  可恢复:429/5xx/超时/参数错(LLM 自改)→ 指数退避或回填
  不可恢复:401/403/PermissionError → 中止或回填 "do not retry"

LLM 层:llm_call_with_retry(指数退避 + jitter)
工具层:try/except + timeout,错误以 role=tool 回填
公式:wait = base * 2^i + jitter   (jitter 防惊群)
```

### 七、课堂练习(完整发放版)

> 讲师提示:本节练习是给 Agent 加"错误处理三件套"——retry / timeout / budget。学员基于 L9 或 L10 版 hello-agent,总时长 30-35 分钟。

#### 练习 1:三类 fake 工具 + wrap_tool 装饰器(20 min,个人)

**任务**:实现下面 3 个 fake tool 触发不同类型的失败,写一个 `wrap_tool` 装饰器,让 Agent 遇到:
- **TransientError**(网络抖动):指数退避重试 3 次
- **TimeoutError**(超时):5 秒后中断,回填 `[TIMEOUT]` 给 LLM
- **PermissionError**(不可重试):立即回填 `[UNAUTHORIZED]`,不重试

**fake tool 定义**:
```python
import random, time

class TransientError(Exception): pass
class DomainError(Exception): pass

def sometimes_fail(x: int = 0) -> str:
    """30% 概率抛 TransientError(可重试),70% 返 ok"""
    if random.random() < 0.3:
        raise TransientError("network hiccup")
    return f"ok x={x}"

def always_slow() -> str:
    """总是 sleep 30 秒(用来触发 timeout)"""
    time.sleep(30)
    return "done"

def unauthorized() -> str:
    """总是抛 PermissionError(不可重试)"""
    raise PermissionError("api key expired")
```

**`wrap_tool` 装饰器要求**:
```python
def wrap_tool(fn, *, max_retries=3, timeout=5, base_delay=1.0):
    """
    - 若 fn 抛 TransientError → 指数退避重试(1s, 2s, 4s + jitter),最多 max_retries 次
    - 若 fn 执行时间 > timeout 秒 → 中断,返回 "[TIMEOUT] tool={name}"
    - 若 fn 抛 PermissionError / DomainError → 不重试,直接返回 "[UNAUTHORIZED] {msg}"
    - 任何情况下都返回字符串,不 raise(让 Agent 循环继续)
    """
    def wrapped(**kwargs):
        # TODO
        pass
    wrapped.__name__ = fn.__name__
    return wrapped
```

**测试 prompt**(用你的 Agent 主循环跑):
1. `"调用 sometimes_fail 5 次"` → 应能重试成功
2. `"调用 always_slow"` → 5s 后应回填 [TIMEOUT] 不阻塞
3. `"调用 unauthorized 3 次"` → 立即回填 [UNAUTHORIZED] 不重试

**验收 checklist**:
- [ ] 3 个 tool 都注册,LLM 能正确选中
- [ ] retry 只对 TransientError 生效(不对 PermissionError)
- [ ] timeout 生效(实测 5s 左右返回,不是 30s)
- [ ] 所有失败都回填字符串,Agent 循环不崩

**参考答案**:
```python
import random, time, signal
from functools import wraps

def wrap_tool(fn, *, max_retries=3, timeout=5, base_delay=1.0):
    @wraps(fn)
    def wrapped(**kwargs):
        for attempt in range(max_retries + 1):
            try:
                # 简单的信号 timeout(仅 Unix 有;Windows 需要用 threading 或 concurrent.futures)
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(fn, **kwargs)
                    try:
                        return str(future.result(timeout=timeout))
                    except concurrent.futures.TimeoutError:
                        return f"[TIMEOUT] tool={fn.__name__} after {timeout}s"
            except TransientError as e:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    time.sleep(delay)
                    continue
                return f"[TRANSIENT_FAILED after {max_retries+1} attempts] {e}"
            except (PermissionError, DomainError) as e:
                return f"[UNAUTHORIZED] {e}"
            except Exception as e:
                return f"[ERROR] {type(e).__name__}: {e}"
        return "[UNKNOWN]"
    return wrapped

# 注册时全部 wrap 一遍
REGISTRY = {
    "sometimes_fail": wrap_tool(sometimes_fail),
    "always_slow":   wrap_tool(always_slow, timeout=5),
    "unauthorized":  wrap_tool(unauthorized),
}
```

**常见坑**:
- 重试延迟固定 1s → 打垮下游;必须指数退避 + jitter
- timeout 用 `signal.SIGALRM` 只 Unix 有,Windows 无效 → 用 `ThreadPoolExecutor.submit + result(timeout=)`
- wrap 后 `fn.__name__` 变 `wrapped`,LLM schema 里 `name` 对不上 → 用 `@wraps(fn)`

---

#### 练习 2:BudgetExceeded 护栏(10 min,个人)

**任务**:在 Agent 主循环里加入 **`MAX_TOTAL_COST = 0.10`** 的预算护栏,累计成本超预算立即抛 `BudgetExceeded`,循环外 catch 后返回**已生成的部分结果 + 提示语**。

**骨架**:
```python
MAX_TOTAL_COST_USD = 0.10

PRICES = {                                                   # $/1M tokens
    "gpt-4.1": (2.5, 10),
    "gpt-oss:20b": (0, 0),
    "gpt-4o-mini": (0.15, 0.6),
}

class BudgetExceeded(Exception): pass

class CostTracker:
    def __init__(self):
        self.total = 0.0
    def add(self, model, in_tok, out_tok):
        in_p, out_p = PRICES.get(model, (0, 0))
        self.total += in_tok/1_000_000*in_p + out_tok/1_000_000*out_p
        return self.total

def run_with_budget(user_input: str, max_steps: int = 8):
    tracker = CostTracker()
    messages = [{"role":"user","content":user_input}]
    last_answer = None
    try:
        for step in range(max_steps):
            resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
            u = resp.usage
            cost = tracker.add(MODEL, u.prompt_tokens, u.completion_tokens)
            # TODO:if cost > MAX_TOTAL_COST_USD → raise BudgetExceeded(f"...")
            msg = resp.choices[0].message
            messages.append(msg)
            if msg.content:
                last_answer = msg.content
            if not msg.tool_calls:
                return {"answer": msg.content, "cost": cost, "step": step+1}
            # ... 执行 tool + 回填(略)
    except BudgetExceeded as e:
        return {"answer": f"[budget exceeded: {e}] partial: {last_answer or '(none)'}",
                "cost": tracker.total, "step": step+1}
    return {"answer": f"[max_steps exceeded]", "cost": tracker.total, "step": max_steps}
```

**验收 checklist**:
- [ ] 用一个绕的 prompt(如让 Agent 反复调 sometimes_fail 直到 5 次成功)触发预算
- [ ] 触发 BudgetExceeded 后**返回结构化 dict**(包含 cost + partial answer + step),而非 crash
- [ ] MAX_TOTAL_COST 数值可通过环境变量 `MAX_COST` 覆盖(方便测试)

**参考答案(核心)**:
```python
if cost > MAX_TOTAL_COST_USD:
    raise BudgetExceeded(f"cost ${cost:.4f} > cap ${MAX_TOTAL_COST_USD}")
```

**常见坑**:
- 预算判断放在 for **尾** → 这一步已经花了才发现;应放 for **头** cost check
- `resp.usage` 有些兼容端点返 None → 加防御 `u.prompt_tokens or 0`
- 忘了在 tool 循环里累加 tool 结果 tokens → 只算了 LLM 的 in/out,漏了 tool 结果的 in(下一步会被计入)

**挑战延伸(选做)**:
- 加 `MAX_TIME_SEC = 30` 护栏(总耗时超 30s 也退出)
- 加动态限速:每 min < 20 次 LLM 调用,超了 sleep 到下一分钟
- 打印每步的 `(cost_so_far, step)`,画出 cost 增长曲线

### 八、测查题与参考答案

1. LLM API 返回 429(Rate Limit)的标准应对方式?  A. 立即放弃,返回错误给用户  **B. 指数退避(1s/2s/4s/...)+ 随机抖动后重试 N 次**  C. 立刻切换到本地模型  D. 无限循环重试到成功 → **B**。`tenacity`、`backoff` 等库一行装饰器即可;jitter 防止惊群效应。
2. 工具调用超时(timeout)正确的处理?  A. 直接 raise,Agent 终止  **B. 捕获后以 `role=tool` 写回 messages(如 `"ERROR: timeout after 10s"`),让 LLM 决定换工具/换参数/放弃**  C. 静默重试到成功  D. 把 timeout 当作工具返回了 None → **B**。Agent 的"自愈"本质就是把 error 当 obs 让 LLM 看到,而不是让 error 杀掉循环。
3. 哪种错误**不应**让 LLM 自动重试?  A. 网络抖动 (`ConnectionError`)  B. 限流 (`429`)  **C. 权限 / 认证失败 (`401`/`403`)**  D. 服务端临时错误 (`5xx`) → **C**。`401`/`403` 是配置/凭据问题,重试 100 次也不会成功,反而触发风控;应直接 fail-fast 并告警。
4. **简答**:jitter 的作用?
   - **参考答案**:防止多个客户端同时退避后**同时再次重试**(惊群效应),让重试时间错开,降低服务端二次冲击。
5. **场景**:LLM 偶发 500,怎么改造?
   - **参考答案**:① 加 `llm_call_with_retry`(3~5 次指数退避);② 多次失败后降级到备用模型(如 GPT-4.1 → GPT-4o-mini);③ 失败 trace 写入 logs/告警;④ 监控失败率,超阈值切流量。

### 九、教学反思要点
- 学员能否分清"该不该让 LLM 重试"?这是高级课程基础。
- 故障注入演示让学员第一次感受到 Agent 的"自愈"魅力,务必现场跑一次让大家看日志变化。

---

## L12 — 实战:Hello-Agent 项目串讲

### 一、基本信息
- **课时编号**:L12
- **课时时长**:120 分钟(实战课加长)
- **课型**:综合项目
- **前置**:L7–L11
- **配套代码**:`examples/hello-agent/main.py`、`examples/hello-agent/tools.py`(可让学员重写)。

### 二、教学目标
**知识目标**
- 综合运用 L7–L11 的所有知识。

**能力目标**
- 独立交付一个最小可用 Agent:有工具、有循环、有错误处理、有 system prompt、有 trace。
- 通过 5 项验收任务。
- 输出可重现的运行日志与 README。

### 三、教学重点与难点
- **重点**:5 个验收任务全部通过。
- **难点**:把"零散知识"拼成"一个能跑、能交付的东西"。

### 四、教学准备

**【环境 / 依赖】**
- 学员应已完成 L7-L11 全部作业,`hello-agent` 目录里已能跑主循环 + 多工具 + 并发 + retry + budget。
- 讲师本地准备**一份完整参考解答**(不发,仅在测评环节 5.5 对照),标准结构如下:
  ```
  examples/hello-agent/
  ├── main.py             ← CLI 入口 + 主循环
  ├── agent.py            ← Agent 类:核心 run() 方法
  ├── tools.py            ← 工具实现 + TOOL_REGISTRY + TOOL_SCHEMAS
  ├── guardrails.py       ← wrap_tool / CostTracker / max_steps
  ├── system_prompt.txt   ← system prompt(可迭代)
  ├── .env.example
  ├── requirements.txt
  ├── README.md           ← 3 分钟能跑通的 quickstart
  └── tests/
      └── test_smoke.py   ← 至少 1 个冒烟测试
  ```

**【代码素材】**
- **验收测试脚本 `verify.py`**(讲师提供,课上跑给学员看):自动跑 5 个 prompt,检查:是否终止 / 是否 tool_call 生效 / 是否命中 budget / 输出格式是否符合 —— 学员看着自己 Agent 一条条 pass/fail,可视化验收。
- **示例 README 模板**(讲师提供参考版):必含 3 段:What(1 句话)/ How(3 步 quickstart)/ Limits(明写不支持什么、成本上限)。

**【数据 / 样例】**
- **5 个验收 prompt**(五.2 五验收任务对应):
  1. 天气查询(单 tool)
  2. 多城市对比(多 tool 并发)
  3. 数学连算(工具链)
  4. 未授权工具触发(rejected 是对的,不是 bug)
  5. 超长 loop(触发 max_steps 或 budget,应优雅退出)

**【教学材料】**
- **5 项验收清单**(五.2 板书):环境 / 结构 / 功能 / 稳定性 / 文档,每项 3 个子指标,共 15 个打分项。**打印 A4 双面**,一人一份,自评 + 互评。
- **常见"未过关"picture 库**:讲师收集 5-10 张真实学员半成品截图(去敏感信息),课上作为反面教材"这类你以为过了其实没过"。

**【学员课前】**
- **必须**已跑通 L11 结束时的版本,能跑至少 1 个 prompt 到 final answer 且不烧超预算。
- 写一份 3 段的 README 草稿(What/How/Limits),课上互评。
- 想好 1 分钟 demo 讲什么、演示哪个 prompt(课末 20 分钟展示环节用)。

**【备用方案】**
- 若课前学员完成度<50%(往往因为 L11 太重) → 讲师**降低验收标准**为"能跑通 3 个 prompt + README 3 行 quickstart",保底通过率,把重头留作作业延后交。
- 若时间不够展示 → 每人 30 秒极速轮讲,老师只挑 3 组做详细点评。

### 五、教学过程

#### 1. 项目目标讲解(10 min)

**5 个验收任务**(也是 L12 的"考试"):

1. **"现在几点?"** → 应调 `now_time`。
2. **"(123 + 456) * 7 等于几?"** → 应分步调 `add` + `mul`。
3. **"北京今天天气怎么样?"** → 应调 `get_weather`。
4. **"帮我订张去东京的机票"** → 应礼貌告知"不支持订机票",不能编。
5. **`add("abc", 1)`(手动模拟参数错)** → 应捕获异常回填,Agent 自我修正或告知用户。

> 【讲师讲稿】"前 3 个测的是'工具被正确选用',第 4 个测的是'**不在能力范围时如何拒绝**'(不要幻觉),第 5 个测的是'**错误恢复**'。这 5 个跑通,你就交付了一个最小可信赖的 Agent 雏形。"

---

#### 2. 学员独立实现(70 min)

讲师巡视,助教 1:1 答疑。

**关键 checkpoint**(讲师每 15 分钟全班同步一次):
- **15 min**:项目结构搭好,`smoke.py` 跑通。
- **30 min**:第一个工具 + 主循环跑通任务 1。
- **45 min**:三个工具 + 主循环跑通任务 1-3。
- **60 min**:加 system prompt,跑通任务 4。
- **75 min**:加异常捕获,跑通任务 5。
- **90 min**:写 README、整理 trace。

鼓励互相 review。

---

#### 3. 项目互评(25 min)

**【活动】** 4 人一组,互相运行彼此的 Agent,完成 5 项任务的打勾表:

| 任务 | 是否通过 | trace 是否清晰 | system prompt 是否合理 |
|---|---|---|---|
| 1. 现在几点? | | | |
| 2. (123+456)*7 | | | |
| 3. 北京天气 | | | |
| 4. 订机票(应拒绝) | | | |
| 5. add("abc",1) | | | |

讲师评出"最稳"(5 项全过)和"最人性化提示"(任务 4 的拒绝话术最得体)两个小奖。

---

#### 4. 讲师演示参考实现(10 min)

讲师把工作区 `examples/hello-agent/main.py` 走一遍,**重点指出哪些细节比学员实现更稳**:
- 把 system prompt 抽到外部文件(便于改不动代码)。
- trace 用 `logging` 而不是 `print`(可分级、可重定向)。
- max_steps 通过环境变量配置(部署灵活)。
- 工具 schema 用 `inspect` 自动生成(避免手写不一致)。

---

#### 5. 测查 + 总结(5 min)

**测查(3 min)**:投影第八节 3 道选择题,**学员举手抢答**(20 秒思考即公布答案),讲师针对每题陷阱**点 1 句**——本节作为综合实战的收尾,简答与场景题作为课后复盘,讲师下次课开场抽 2 人分享解决方案。

**小结(2 min)**:讲师投影 "今天必须带走的 3 句话",同时也是**整个 M2 的收官**:

> **M2 收官 — 今天必须带走的 3 句话**:
> 1. **Agent 项目最低交付物三件套**:完整 trace 日志 + README + `.env.example`,缺一个都不算"能交付"。
> 2. **任务设计要含 happy + sad path**——只测正向不算检验鲁棒性,故意输错参数和问无法回答的问题(任务 4、5)才是高级测试。
> 3. **工具与主循环分文件**(`tools.py` vs `agent.py`)——工具是纯函数易单测,主循环是流程控制,两者职责必须解耦。

> 【讲师讲稿】"M2 到此结束。从下节课 M3 开始,我们把'工具'这一层升级——不再每个 Agent 重写一遍工具集成,而是用 MCP 协议把工具变成'USB-C 接口',任意 Agent / Cursor / Claude Desktop 都能复用。今天你写的 100 行 Agent 是基础,下节课你写的 MCP Server 是'生产形态'。"

### 六、板书设计
```
验收清单(下课前打勾)
[ ] 1) 现在几点?     → now_time
[ ] 2) (123+456)*7?  → add + mul(可能分两步)
[ ] 3) 北京天气?     → get_weather
[ ] 4) "订机票"      → 礼貌拒绝(无工具,不要编)
[ ] 5) add("abc",1)  → 异常回填,Agent 自愈或告知

交付物
- 代码(main.py + tools.py + system_prompt.txt)
- README(如何运行 + .env.example)
- 一份完整 trace 日志(5 个任务各一遍)
```

### 七、课堂练习(完整发放版)

> 讲师提示:L12 整堂课是"项目验收 + 互评",所有活动都是练习。本节将 5 项验收任务 + 互评清单 + 演示 rubric **成套打包**供讲师直接发给学员,总时长 90-120 分钟。

#### 练习 1:5 个验收任务(现场跑,60 min,个人)

**任务**:每人在自己 hello-agent 上依次跑 5 个验收 prompt,按 checklist 打分。

**验收 prompt 集**(打印一人一份):

| # | prompt | 期望行为 | 通过判定 |
| - | ------ | -------- | -------- |
| 1 | `"上海现在天气怎么样"` | 1 步 tool → final | 返回含"上海"和天气描述,cost < $0.01 |
| 2 | `"帮我同时查北京、上海、深圳三地天气"` | 一次 3 tool_calls 并发 → final | 3 个城市都返回,耗时 < 3 秒(如是 async 版) |
| 3 | `"1+2+3+4+5+6+7 是多少"` | 多次调 add → final `"28"` | 最终答案精确 28,step ≤ 6 |
| 4 | `"帮我发一封邮件给客户"` | 无邮件 tool,LLM 应礼貌拒绝 | 返回类似"我目前没有发邮件的工具,无法完成" |
| 5 | `"反复调用 sometimes_fail 100 次直到全部成功"` | max_steps 或 budget 兜底触发 | 触发 `[max_steps exceeded]` 或 `[budget exceeded]`,不 crash |

**自评打分表**(每项 5 分,共 25):

| 项目 | 5 分 | 3 分 | 0 分 |
| ---- | ---- | ---- | ---- |
| Prompt 1 通过 | 全对 | 部分对 | 崩/无输出 |
| Prompt 2 通过 | 3 城市 + 并发耗时 < 3s | 3 城市但串行 | 只查了 1 个 |
| Prompt 3 通过 | 精确 28 | 数值近似或步数超 | 计算错误 |
| Prompt 4 通过 | 礼貌拒绝,不编造 | 编造了假邮件 | 直接 crash |
| Prompt 5 通过 | 优雅退出 + 返回 partial | 退出但无 partial | 死循环/crash |

**验收下限**:总分 ≥ 15/25 视为通过(M2 结课)。

---

#### 练习 2:代码结构互评(30 min,3 人一组)

**任务**:每组 3 人互相评 code review,按下面清单打勾。

**结构清单**(必须有):
- [ ] `examples/hello-agent/` 根目录含 `main.py` 或 `agent.py`
- [ ] `tools.py` 单独文件(工具函数 + REGISTRY + TOOLS schema)
- [ ] `guardrails.py` 单独文件(wrap_tool / CostTracker / BudgetExceeded)
- [ ] `system_prompt.txt` 或 system prompt 变量集中管理
- [ ] `.env.example` + `.gitignore`(`.env` 在忽略里)
- [ ] `requirements.txt`(锁版本)
- [ ] `README.md`(3 段:What / How / Limits)

**README 3 段模板**(讲师提供):
```markdown
# Hello Agent

## What
一个能查天气、算算术、报时的 AI Agent,基于 GPT-4.1(或 Ollama 本地模型)。

## How
1. `python -m venv .venv && .venv\Scripts\Activate.ps1`
2. `pip install -r requirements.txt`
3. cp `.env.example` `.env`,填 `OPENAI_API_KEY`
4. `python main.py "上海天气?"`

## Limits
- 只支持 3 个工具:get_weather / add / now_time
- 单次成本上限 $0.10(可改 `guardrails.py` 里的 MAX_TOTAL_COST_USD)
- 未接入 SQLite / RAG,重启后不记忆
```

**互评评分表**(每项 2 分,共 14):

| 项目 | 打分 |
| ---- | ---- |
| 目录结构清晰(拆文件) | /2 |
| tools/guardrails 分离 | /2 |
| .env + .gitignore 正确 | /2 |
| README 3 段齐 | /2 |
| 代码有基本注释/docstring | /2 |
| 能一次读懂主循环流程 | /2 |
| 至少 1 个简单冒烟测试 | /2 |

**下限**:互评 ≥ 8/14 视为结构合格。

---

#### 练习 3:1 分钟 demo 演示(30 min,轮流,每人 1 分钟)

**任务**:每人现场跑一个 prompt,同时讲清 3 件事(共 60 秒):
1. **What**(10 秒):这个 Agent 是干嘛的
2. **Show**(30 秒):现场跑一个 prompt,让大家看到 step 打印 + 最终答案
3. **Limits**(20 秒):目前不能做什么、下一步想做什么

**演示评分表**(每项 3 分,共 9):

| 项目 | 3 分 | 2 分 | 0 分 |
| ---- | ---- | ---- | ---- |
| What 说清 | 一句话精准 | 说清但绕 | 没说 |
| Show 跑通 | 现场无 bug + step 可见 | 跑通但无 step | crash/无网 |
| Limits 诚实 | 承认真实局限 | 泛泛而谈 | 吹牛/掩饰 |

**下限**:demo ≥ 6/9 视为演示合格。

---

#### 总分与结课判定

| 环节 | 满分 | 及格线 | 你的分 |
| ---- | ---- | ---- | ---- |
| 5 项验收 | 25 | 15 | / |
| 结构互评 | 14 | 8 | / |
| Demo 演示 | 9 | 6 | / |
| **合计** | **48** | **29** | / |

**≥ 29 分 = M2 结课通过**,可进入 M3。

**常见坑**:
- 只跑 prompt 1、2 就交(简单场景),没测 3-5(挑战场景) → 结构没受压 · 生产环境爆
- README 只写 "how to run" 没写 "limits" → 用户来投诉时你答不出边界
- Demo 时想解释"这里其实我还没做完" → 说 Limits 就好,别在 Show 时给自己找台阶

**挑战延伸(选做)**:
- 把演示视频录下来(3 分钟),课后交给其他组"盲评"(不告诉是谁),看结构好坏是否能被外行看懂
- 把 Agent 打包成 CLI 全局命令:`pip install -e .` 后可直接 `hello-agent "..."` 调用(setup.py / pyproject.toml)

### 八、测查题与参考答案

1. 综合作业中,最能检验 Agent 鲁棒性(robustness)的是哪几个任务?  A. 任务 1 + 任务 2(基础问答)  **B. 任务 4(故意提供错误参数)+ 任务 5(故意问无法回答的问题)**  C. 任务 3(简单工具调用)  D. 全部任务一视同仁 → **B**。鲁棒性 = "异常路径正确"的能力,正向路径全对说明不了什么。
2. 把工具函数与主循环分文件(`tools.py` vs `agent.py`)的核心好处?  A. 让代码运行更快  **B. 组织清晰、工具可被多 Agent 复用、可独立写单测**  C. 减少内存占用  D. 必须分,否则 Python 报错 → **B**。tools 是纯函数(in→out),很适合独立测试;主循环是流程控制,分开后改一边不影响另一边。
3. 综合实战的合理交付物**最低集合**包括?  A. 仅代码  **B. 完整 trace 日志 + README(运行步骤、设计取舍) + `.env.example`**  C. 仅 README  D. 仅一段录屏 → **B**。这三件套是"别人能在 10 分钟内跑起来"的最低标准,trace 证明 Agent 真跑过、README 解释决策、`.env.example` 防止别人猜密钥结构。
4. **简答**:写 system prompt 要求"中文、调用前简述意图、最多 5 步"。
   - **参考答案**:
     ```
     你是一个中文 AI 助手。规则:
     1. 全程使用中文回复。
     2. 每次调用工具前,先用一句话说明"我打算调 X 来做 Y"。
     3. 最多调 5 次工具,超过请直接给出当前最佳结论。
     4. 涉及时间/数学/天气等事实,必须通过工具核实,不得编造。
     5. 不在能力范围内的请求(如订机票),请礼貌告知"暂不支持"。
     ```
5. **场景**:Agent 不调 `now_time`,自己编时间。如何修?
   - **参考答案**:① system prompt 明确"询问当前时间必须调 now_time";② 强化 now_time 的 description("当用户询问当前时间/日期时**必须**调用,禁止凭印象编");③ temperature 调低到 0~0.2;④ 提供 1 条 few-shot 示例。

### 九、教学反思要点
- 是否所有学员 5 项全过?未过的需补练,否则 M3 跟不上。
- 互评 + 评奖是 M2 的高潮,氛围非常重要,务必预留时间。
- 把这个 hello-agent 作为 M3 重构的基础——下节课会把工具拆成 MCP Server,提前让学员心理准备。

---

*模块 2 结束。下一模块进入 MCP 协议与工具层(M3),把工具从 Agent 里拆出来。*
