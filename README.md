# pm-hub

多仓库产品/项目的中枢：任务看板、里程碑、仓库注册与决策记在以 Markdown 为唯一事实来源；`docs/dashboard.html` 为全量静态仪表盘，`docs/dashboard-qunxing.html` 为群兴任务专页（按 effort 分组）。

## 快速开始

- 阅读 [`AGENT.md`](AGENT.md) 与 [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md)。
- 登记仓库见 [`repos.md`](repos.md)；看板与标签见 [`docs/board.md`](docs/board.md)。

## 生成仪表盘

本地与 CI 使用**同一**命令。修改 `repos.md`、`docs/board.md` 或 `docs/milestones.md` 后执行：

```bash
python scripts/gen_dashboard.py
```

将 `docs/dashboard.html`、`docs/dashboard-qunxing.html` 与 Markdown 源一并提交。CI 会重新运行生成器并 `git diff` 检查，避免手改或遗漏再生成。

## 测试

```bash
python -m unittest discover -s scripts -p "test_*.py" -v
```

## 在业务仓库中

可在各业务仓保留极短说明，指向本仓 URL；勿复制整套 `docs/`。
