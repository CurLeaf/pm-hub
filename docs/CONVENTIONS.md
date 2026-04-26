# pm-hub 格式约定（冻结）

与 [`repos.md`](../repos.md) 和解析脚本共用；变更时请同步更新 `scripts/gen_dashboard.py` 与相关测试。

## 仓库标识（`repos.md`）

- **第一列**为仓库**短名（canonical id）**：仅小写 ASCII、`[a-z0-9-]`，与 GitHub 仓名可不同但团队内应固定。
- `board.md` 中的任务标签**必须**只使用表中已登记的短名：`[短名]`。

## 看板 `docs/board.md`

### 分栏（节标题）

- 节标题为 Markdown 二级标题：`## …`，推荐固定用语（与仪表盘统计一致）：
  - `## 🔴 紧急`
  - `## 🟡 进行中`
  - `## 🟢 待开始`
  - `## ✅ 已完成`（可仅用于近期归档；长期归档可移到 `docs/archive/`）
- 可增删分栏，但**每个分栏内**仅使用下方任务行格式，勿混用无列表语义的段落，以免自动解析漏行。

### 任务行

- 每行一条任务，列表语法：`- [ ]` 未完成，`- [x]` 或 `- [X]` 完成。
- 一行结构建议（顺序可微调，但标签与元数据应留在同一行）：

```markdown
- [ ] 任务标题 [frontend][backend] @owner 2026-01-20 (https://github.com/org/repo/pull/1)
```

- **仓库标签**：一个或多个 `[短名]`，短名**必须**来自 `repos.md` 表第一列。
- **@owner**：可选，GitHub handle 或中文称呼，不校验。
- **日期**：可选，格式 `YYYY-MM-DD`（`-` 分隔）。
- **链接**：可选，用圆括号；常用于 PR 或 design doc。

## 里程碑 `docs/milestones.md`

- 使用 **GFM 表格** 描述里程碑（便于机器解析、人类可改）：

| 列 | 说明 |
|----|------|
| 第一列 | 里程碑 id 或名称（如 `v0.1`） |
| 目标日期 | `YYYY-MM-DD` |
| 完成度 | 整数 0–100，表示百分比（不带 `%` 符号） |

表头行可为：

`| milestone | target | progress |`

解析器以表头为锚点，读取后续数据行；可在表格前后写自由说明文字。

## 自动产物（HTML）

- **`docs/dashboard.html`**：全量看板与里程碑等；**只读**来源：`repos.md`、`docs/board.md`、`docs/milestones.md`。
- **`docs/dashboard-qunxing.html`**：仅含带 `[qunxing]` 的任务，按 `effort:好做|一般|难` 分组展示。
- **不要**手改上述 HTML；均由 `python scripts/gen_dashboard.py` 生成后一并提交。
