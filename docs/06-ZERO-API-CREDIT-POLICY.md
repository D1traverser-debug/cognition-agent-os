# 零模型 API 计费的运行方案（2026-10-20）

**适用用户约束**：不得依赖按 token 计费的远程 LLM API、试用积分、有限免费积分或付费套餐维持服务；不自动下载云模型，不自动部署云实例或开启付费接口。此文档限定的是**计费方式**，不表示 LLM 推理不需要内部 token，亦不表示完全没有资源成本。

## 第一层：完全不调用模型

默认 `--planner-mode deterministic`。真实公开文件数据的版本 SHA/diff 由确定性代码比较；出现变化只产生 `CHANGE_REQUIRES_REVIEW`，不谎称语义分析或最终架构批准。适合免费 CI、真实来源读取、状态和授权验证。

## 第二层：用户本机开源模型（可选）

使用用户**已安装并下载在本地**的 Ollama 模型；本程序仅向 `http://127.0.0.1:11434` 发送 HTTP 请求，禁止调用远程模型 API，拒绝 cloud 字样的模型标识，先使用 `/api/tags` 检查模型是否本地已安装，**不会自动 pull**。Ollama 的实际 CPU/GPU/内存和电耗由本机承担；模型大小和许可应按实际模型选择。没有安装时不静默切回付费云服务，而是返回 `LOCAL_MODEL_UNAVAILABLE` 和 `UNKNOWN`。

### 本机命令示例（需要事先安装一个本地模型）

```bash
# 用户自行安装 Ollama 并拉取许可合适的本地模型（此项目不自动下载）。
ollama list
# 在项目已有任务与隔离数据库时：
PYTHONPATH=src python -m cognition_agent_os.cli \
  --db runtime/state.sqlite --workspace runtime/workspace \
  worker-once --planner-mode ollama-local --local-model "你本机ollama list显示的模型名"
```

注意：`/api/generate` 返回的只是建议，必须保留 `NEEDS_REVIEW` 和独立验收。真实模型权重、在用户硬件上的实际效果、提示注入鲁棒性均**未在本轮验证**。真实开源许可证和硬件需求由用户选择模型后核验。

## 第三层：GitHub 免费公共 CI（不是自主执行宿主）

仓库目前是 **PUBLIC**。GitHub 文档明确标准 GitHub-hosted runner 在公共仓库免费且无分钟总额；不是试用积分模式。已新增只用于 PR/分支验证的 `ci.yml`：固定 GitHub action SHA、最小 `contents: read`、不注入模型密钥、不上传 artifact、10 分钟超时，且仅在公开仓库运行。仓库改私有时**该 job 跳过**，以避免使用私有仓库免费分钟额度。

CI 作业 ≠ 本机常驻服务；CI 不是用户不发消息时持续自主执行，也不承诺 `schedule` 的每次触发。GitHub 未认证 REST API 仍有 60 次/小时/IP 限速，这是公共 API 的速率限制，**不是付费 Token 积分**。下轮如选择定时执行，应另行设计可持久状态和 missed tick 补偿，禁止把 job 临时磁盘当长时状态权威。

## 当前证据分级

- 标准库及真实本地假 Ollama HTTP Server 的契约测试：已执行；不是 LLM 权重测试。
- GitHub connector 已独立读取真正不可变 upstream commits 与 blob：已观察；本地无外网，尚未完成从独立 Worker 真实 HTTP 请求的网络运行。
- GitHub Actions CI：代码已提交 PR 后可能由平台执行；在未收到 GitHub job 真实回执前记为 `NOT_OBSERVED`。
- 用户 PC 上的模型、OS 定时唤醒、远端业务写入、陌生任务独立语义评分：未执行。

官方来源：
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- https://docs.ollama.com/api/generate
- https://docs.ollama.com/quickstart

## 可核对的真实公开来源样本

`examples/public_mcp_immutable_pair.json` 包含实际通过 GitHub 读取的同一路径的两个 commit/ref 与文件 Blob SHA，供未来联网 Worker 用 `seed-github` 测试。它的意义是**规范文件真实内容有变化**，而不是自动给出“影响哪些 ADR”的独立语义结论。用于 `NO_CHANGE` 控制组时把新旧 ref 都设为同一个 commit。

```bash
PYTHONPATH=src python -m cognition_agent_os.cli \
  --db runtime/test.sqlite --workspace runtime/workspace \
  seed-github \
  --repo modelcontextprotocol/modelcontextprotocol \
  --path docs/specification/2026-07-28/changelog.mdx \
  --old-ref b488c16623e5202a3961e551886044577ae0f096 \
  --new-ref db4bfcff3d60f5df01a21bdf6b78f7012cac4634
PYTHONPATH=src python -m cognition_agent_os.cli \
  --db runtime/test.sqlite --workspace runtime/workspace worker-once
```

命令在具备公网访问的实际电脑上才可执行真实 GitHub HTTP 读取。本轮受限容器没有网络 DNS，已通过另一个 GitHub 连接核对原始 SHA；不把它包装成 Worker 真实 HTTP 测试。
