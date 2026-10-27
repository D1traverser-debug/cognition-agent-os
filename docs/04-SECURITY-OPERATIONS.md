# cognition-agent-os — 安全、操作、故障、发布与成本约束

> **候选安全与运维合同，不代表现网已实施**。2026-10-20。仓库当前为 **PUBLIC**，`main` 暂只含初始 README；文档分支和 PR 不等于合并发布。

## 1. 资产与威胁边界

初始高价值资产：用户目标与授权、外部工具连接、API 密钥、第三方返回的未可信内容、任务台账、模型生成动作、可回放历史、评测 Gold 数据、研究产物。主要威胁：提示注入使模型改变目标或越权、旧批准重放、任意路径写入、重复远端效果、伪造独立评测、内容及日志泄露、供应链或模型版本变更导致漏门禁、预算耗尽以及长任务无人唤醒。

未可信区：网页与仓库文本、tool annotations、模型文本、公共 README、旧任务摘要、LLM 自生成 PASS/APPROVED。可信区不是“某个 agent 角色”，而是实证身份、执行适配器与最终 owner 的可审计状态。

## 2. 全入口安全中介（必须覆盖）

所有实际有副作用的入口必须到达相同等价的可信授权检查：本地 function tool、Agent handoff、hosted MCP/tool、shell/patch/computer 执行、独立 Worker、定时器、脚本和人工重放。**不能仅安装 Agents SDK 的 tool guardrail 后宣布全覆盖**：其标准 guardrail 范围不自动包括 handoffs 与一些托管/内置工具。[官方 Agents SDK 说明](https://openai.github.io/openai-agents-python/guardrails/)。

执行网关对每项动作至少核验：主体与真实调用身份、工具能力与目的范围、目标资源、授权有效期、任务/目标版本、知识依赖指纹、预算预留、参数指纹、幂等标识、目标 provider 的远端授权语义。高风险入口无法封装或核对时应**禁用该入口真实写入**，而非寄希望于 prompt。

授权撤销的精确含义：本地检查后、外部 provider 接受请求前，授权仍可能被撤销。除非 provider 自身承诺在提交点检查授权/支持撤销，否则不能保证在途请求绝对不生效。必须保留 `DISPATCHED/UNKNOWN` 并做可用范围内的读回。

## 3. 仓库、分支、CI 与密钥

- **公开仓库默认为公共内容场所**：不提交真实 token、cookie、密码、客户资料、私人对话、敏感原始审计数据、非公开 benchmark gold、包含个人隐私的运行 trace。
- 准备 `.gitignore` 忽略 `.env*`、运行时 sqlite/临时数据库、`__pycache__/`、`artifacts/`、`secrets/`、原始日志；需要保留无害样本时另放 `fixtures/` 并先审核。
- `main` 为稳定集成分支；重要设计与代码应通过审查 PR。未来建议使用分支保护或 ruleset、敏感信息扫描、默认最小权限的 `GITHUB_TOKEN`。本轮不改设置，不启用自动合并。
- GitHub Actions 若仅用于 CI，应设置相应 job 的最小 `permissions`，并避免在 pull_request 等低信任上下文暴露生产凭据。涉及外部写入时必须具体评估事件信任来源。
- 初版不部署 cron/Actions 长期任务，不开通付费云资源，不自动循环调用模型；部署必须先有已批准的运行范围和最高成本限制。

## 4. 日志、证据链与隐私

记录：`correlation_id,task_id,goal_revision,action_id,principal_ref,source_version,grant_ref,decision,reason,worker_version,model_version,oracle_version,effect_ref,observed_at`。不在公共日志中存放密钥、完整私有输入或不必要的模型上下文；用脱敏摘要/哈希表达可溯源性。

区分：**命令发出、供应商已受理、供应商状态读回、业务目标成功、独立验收通过**；不得用一个 success 布尔值混合。知识更改需反查依赖；作废旧推断但保留已发生外部事实及合法审计记录。明确数据保留/删除策略后再接入真实私人资料。

## 5. 失败处理与停止条件

| 情境 | 合法响应 | 禁止行为 |
|---|---|---|
| 目标或 grant 过期 | 暂停新写入、记录原因，继续无关授权工作 | 旧 plan 重放并写入 |
| 外部响应未知 | 记 UNKNOWN，查询真实目标资源/幂等状态 | 直接把 timeout 当失败再扣一次 |
| Worker 崩溃或 lease 过期 | 新 worker 条件领取；必要时 fencing 与效果核对 | 双 worker 同时执行同一不可逆意图 |
| 供应商不可访问 | 降级为只读/待核对；可继续本地合法工作 | 假装远端状态等于本地 checkpoint |
| 模型指出自身有错误 | 收集证据、确定影响范围、隔离修复候选 | 自写自己测试、自给 PASS、自晋升 |
| 灰度指标不完整 | `INCONCLUSIVE/HOLD`，不促进候选 | 使用全量平均掩盖候选劣化 |
| 预算耗尽 | 拒绝超额新动作、保留任务与原因 | 拆分任务或重试绕过配额 |
| 缺真实宿主唤醒 | 输出 `HOST_TRIGGER_UNAVAILABLE` | 声称用户未提醒时仍在运行 |

## 6. 自主治理不是“再建一个监控 Agent”

**检测**包括主动寻找反例、观察真实业务效果、发现遗漏覆盖和过期架构假设；**诊断**比较根因解释和依赖范围；**治理**执行可逆、许可内的干预；**验证**须看不同入口的失败类覆盖、合法邻接动作不被误阻断、复发情况和真实用户结果；**晋升**须证据与候选资产 hash/当前目标版本及可信审批绑定。用户反馈只是补充证据，不是强制由用户发现系统失误。

晋升权限不得存在“模型同意自己就成功”的后门；初期采用隔离候选+人工许可，后续如果具备真正外部可验证、低风险、边界清楚的自动晋升能力再扩展。

## 7. 资源预算与自我限制

计算 token、模型次数、并发占用、供应商请求和真实费用必须分层记账；预留+结算、幂等请求去重、失败重试成本与未知费用单独处理。单次模型请求预算限额、项目总限额以及外部 provider rate-limit 由部署前批准。无真实账单时**不声明硬费用上限已落实**。确保任务持续到达超过处理能力时采用背压、降级或明确拒绝，不能虚构“永不饥饿”。

## 8. 发布、升级与回滚

每次候选发布固定 `code/workflow/schema/model/goal/knowledge/policy/oracle` 版本及受影响任务；旧工作流兼容情况必须实测。代码二进制回滚**不能**撤销 DB schema 变更、已外发的远端操作、记忆修订；需要扩展/兼容/收缩方案、外部效果对账以及有条件的停机或回滚标准。见 [Temporal Workflow Versioning](https://docs.temporal.io/workflow-definition)。

初始安全晋升测试必须覆盖伪造 APPROVED、源材料撤回、已修改目标、候选组指标低劣、结果不足、跨入口补丁未覆盖和误阻断合法动作；全部进入明确拒绝或 HOLD 分支。

## 9. 实际工程进度与下阶段输入

此文档本身无安全效果。安全门禁属于未来代码、可信运行宿主与供应商实际授权；目前只有设计和此前本地 SQLite 等受限实验。下一步需要实现并实测第一条完整工作链 [historical 03-FIRST-VERTICAL-SLICE.md](../archive/docs/03-FIRST-VERTICAL-SLICE.md)，对该版本报告每条测试的真实状态（`SPECIFIED/IMPLEMENTED/EXECUTED/INDEPENDENT_VERIFIED`）。不得把设计 PR 视作系统可持续自治或已通过外部验收。

参考：[GitHub Actions 计划运行异常](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)、[GitHub GITHUB_TOKEN 权限](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)、[Agents SDK Guardrails](https://openai.github.io/openai-agents-python/guardrails/)、NIST AI RMF、历史研究 `DEEP_STUDY_AUTHORITY_AND_ARCHITECTURE.md`、`DEEP_STUDY_GOAL_FIDELITY_AND_SAFE_EVOLUTION.md`。