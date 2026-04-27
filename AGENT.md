# AGENT 行为

## 本仓角色

本仓库是**项目中枢仓**：任务看板、里程碑、多仓库注册表、决策记录以 Markdown 为唯一事实来源（SSOT）。不要在本仓引入仅用于 PM 流程的数据库。  
**通用性**：下列约定与具体产品线、电商平台、技术栈无关；业务差异只体现在 `docs/board.md` 的任务正文与 `repos.md` 的登记项，**不**改本节流程。

新对话或新任务时，**先读** [`repos.md`](repos.md)（与 [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md)），再查 [`docs/board.md`](docs/board.md) 与 [`docs/milestones.md`](docs/milestones.md)。

## 优先级

- **effort 仅三档**：`好做`｜`一般`｜`难`（禁用别词，除非你本条消息另行定义一档对照表）。  
- **主序**：`好做` → `一般` → `难`。同档只按依赖与 [`docs/board.md`](docs/board.md) **已出现**的 `blocked-by` / `阻塞：…` 排，**不**写业务价值、**不**猜阻塞。  
- **交互**：你发需求 → Agent 仅输出一张表：`编号`｜`建议effort`｜`理由`（每行≤一句）｜`阻塞`（仅照抄 board 已有，无则空）→ 你一条消息：`同意` 或 `编号=档位` 增量修改；未列出的编号=采纳建议档。**缺追问一次**。确认后 Agent **仅**输出最终顺序表（同列结构，effort 为定稿）。  
- **bizroi**：仅当你发送 `问bizroi` 或 `#<编号>必须先做` 时处理；`问bizroi` 时只问高/中/低；`必须先做` 将该编号置顶并允许与 effort 主序冲突。  
- **落盘**：[`docs/board.md`](docs/board.md) 可写 `effort:`、可选 `bizroi:`、[`repos.md`](repos.md) 的 `[短名]`；[`docs/roi_register.md`](docs/roi_register.md) 自选。改 board / milestones / repos 后运行文末生成脚本（见下节）。  
- **>15 条**：Agent 拆成多批编号（批名 A/B/…），每批一张表。

### 用户提示词（环境无关）

在任意支持长上下文的对话里，**附上本文件全文**或**首条写明「按本 AGENT 优先级流程」**，避免模型凭默认习惯排业务优先级。模板示例（`@文件名` 仅在某些 IDE 中等价于附文件，可替换为你的工具写法）：

```
按本 AGENT 优先级：<需求，每行一条>
```

```
按本 AGENT 优先级：#<n>必须先做
<需求，每行一条>
```

```
按本 AGENT：问bizroi
<需求，每行一条>
```

```
按本 AGENT：输出board任务行
<粘贴定稿顺序表，或编号+标题每行一条>
```

### Agent 输出

- 排期回合：仅「建议表」与（确认后）「定稿顺序表」。  
- `输出board任务行`：仅 [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) 合规的 `- [ ]` 行，含 `[短名]` 与 `effort:`。  
- **禁止**：开场白、收束语、复述本节规则、业务价值论述。

## 多仓库管理

### 仓库感知

- 任务标签 `[短名]` **必须**小写，且必须出现在 `repos.md` 表**第一列**中（短名可对应任意 Git 仓或产品线，由登记表定义）。  
- 跨仓库任务使用多个标签，例如 `[frontend][backend]`（仅为示例，以你仓 `repos.md` 为准）。

### 按仓库回答

1. 读 `docs/board.md`（必要时结合 `docs/milestones.md`）。  
2. 只保留带 `[该短名]` 的任务行。  
3. 按分栏/优先级向用户说明；缺省时优先「正在实现」「紧急」。

### 显式阻塞

不根据 Markdown 做自动推理依赖。若任務被阻擋，在**任务同一行**写明，例如 `blocked-by: <url或issue #>` 或 `阻塞：等待 backend PR #12`。未写明则只描述状态，不推断阻塞链。

### 业务仓中的指针

各业务仓可保留极短 `AGENT.md`（或链接），说明规划与看板在何处的**本中枢仓** URL；**不要**在业务仓复制 `docs/` 看板与规格全文。

## 格式约定

所有看板/里程碑/标签规则以 [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) 为准；变更时同步更新 `scripts/gen_dashboard.py` 与相关测试（若本仓包含该脚本）。

## 可视化（静态 HTML）

- **生成命令**（本仓若提供脚本则使用；否则以你方 CI 为准）：

```bash
python scripts/gen_dashboard.py
```

- **产物清单、是否含多页、CI 校验范围**：一律以 [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md)「自动产物」与仓库内工作流文件为准；**不在本文件列举具体 HTML 文件名**，避免与脚本演进脱节。  
- **源数据**：`repos.md`、`docs/board.md`、`docs/milestones.md`（只读）；**不要**手改生成出来的 HTML。

## 修改清单（自检）

- 更新看板/里程碑/注册表后：已按 `CONVENTIONS` 运行生成脚本，且将**该节所列全部**生成物与 Markdown 源一并提交（若需）。
