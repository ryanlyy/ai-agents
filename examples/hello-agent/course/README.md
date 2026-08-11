# AI Agent 开发培训课程(36 课时)

本目录是**教师使用的完整课程包**,分四层:

| 子目录 | 面向 | 内容 |
|--------|------|------|
| [`outline/`](./outline/) | 学员 / 讲师速览 | `36-lessons-outline.md` —— 36 课大纲、目标、时长 |
| [`lesson-plans/`](./lesson-plans/) | 讲师上课 | M1 – M7 讲师讲稿(**照本宣科版**),包含板书文本、开场故事、练习骨架、参考答案、测查、教学准备 |
| [`lesson-plans/assets/`](./lesson-plans/assets/) | 学员发放 | 教案里引用的代码素材(如 `M1-L3-Practise2.py`) |
| [`tests/`](./tests/) | 讲师课前 | 11 个可执行脚本 T01 – T11,验证各模块关键代码示例仍能跑通,读 `../../examples/hello-agent/.env` 里的 LLM 配置 |

## 三层内容一图看清

```
    outline/           ← 骨架     每课 3-5 行(讲师速览 / 学员自学)
        │
        ▼
    lesson-plans/      ← 血肉     每课 400-1500 行:讲师逐字讲稿 + 板书 + 练习
        │
        ▼
    examples/hello-agent/  ← 肌肉  可运行的完整参考代码(位于仓库根 examples/)
```

## 教一门课的推荐工作流

1. 先看 [`outline/36-lessons-outline.md`](./outline/36-lessons-outline.md) 建立整体节奏感
2. 上课前 24h 打开对应模块的 [`lesson-plans/Mx-*.md`](./lesson-plans/) 通读一次
3. 按每课 **四、教学准备** 清单预检(环境 / 代码 / 素材 / 应急预案)
4. **课前 30 分钟**跑一次 [`tests/`](./tests/) 里覆盖当天内容的脚本,确认代码库仍绿
5. 上课就照 **五、教学过程** 逐段讲(每段都有大约的时长与"讲师说")
6. **七、课堂练习** 是完整发放版,直接投屏 / 打印发给学员
7. 下课前用 **六、测查** 4 题快速验收

## 关联的其他目录

- [`../docs/`](../docs/) —— 独立参考文档(`agent-development-guide.md`、`mcp-server-basics.md` 等),多处教案里引用其"第 N 节"
- [`../examples/hello-agent/`](../examples/hello-agent/) —— 完整可运行 Demo 项目,是 L12 / L18 / L22 综合实战的参考实现

详细教案清单见 [`lesson-plans/README.md`](./lesson-plans/README.md)。
