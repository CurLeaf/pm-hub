# 仓库注册表

> 下表**第一列**为任务标签用短名（小写，见 [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md)）。

| 短名 | Git 地址 | 负责人 | 技术栈 | 状态 |
|------|----------|--------|--------|------|
| xlshangpin | <https://github.com/org/xlshangpin> | @CurLeaf | 兴链尚品（新项） | 待启动 |
| juminshang | <https://github.com/org/juminshang> | @嘉松 | 聚闽商（H5 等） | 活跃 |
| qunxing | <https://github.com/org/qunxing> | @CurLeaf、俊波 | 群兴项目（跨端） | 活跃 |
| frontend | <https://github.com/org/frontend> | @tbd | React + TypeScript | 活跃 |
| backend | <https://github.com/org/backend> | @tbd | Go | 活跃 |
| mobile | <https://github.com/org/mobile> | @tbd | Flutter | 维护 |
| infra | <https://github.com/org/infra> | @tbd | Terraform | 活跃 |

## 仓库间依赖

- `xlshangpin` 启动期任务多为规划与建仓；与 `frontend` / `backend` 的复用关系以任务行标签为准
- `qunxing` 任务常跨 `frontend` 与 `backend`，以任务行标签为准
- `frontend` 依赖 `backend`（API）
- `mobile` 依赖 `backend`（API）
- `backend` 依赖 `infra`（部署与运行环境）

## CI/CD 状态（手动维护，非权威）

> 需要自动化时，可用脚本或 Action 从各仓 API 更新本表，或改由仪表盘旁链到各仓 Actions 页面。

| 短名 | main 构建 | 最近发行 | 开放 PR |
|------|-----------|----------|--------|
| xlshangpin | 待接 | 待接 | 待接 |
| juminshang | 待接 | 待接 | 待接 |
| qunxing | 待接 | 待接 | 待接 |
| frontend | 待接 | 待接 | 待接 |
| backend | 待接 | 待接 | 待接 |
| mobile | 待接 | 待接 | 待接 |
| infra | 待接 | 待接 | 待接 |
