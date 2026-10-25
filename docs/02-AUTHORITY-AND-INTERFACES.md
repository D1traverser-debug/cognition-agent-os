# cognition-agent-os — 状态权威、接口契约与状态机

> **提案 / 非已实现 API** · 2026-10-20 · 上位：[00-PRODUCT-CONOPS.md](00-PRODUCT-CONOPS.md) · 选型：[01-ARCHITECTURE-DECISIONS.md](01-ARCHITECTURE-DECISIONS.md)

## 1. 六类事实的最终裁决权

| 事实与 owner | 权威记录 | 不得视为权威的信息 |
|---|---|---|
| 目标及约束：已获授权的用户/责任人 | `GoalRevision`：`goal_id, revision, source, effective_at, constraints, supersedes` | LLM 意图猜测、旧聊天摘要、外部网页声称 |
| 任务生命周期：持久任务台账 | `TaskRecord` + 串行化转换日志 + `state_version` | Agent“已完成”、worker 缓存、仪表盘 |
| 当前动作许可：宿主/可信身份与对应授权源 | `GrantRef`：主体、目标、作用域、过期和可核验撤销语义 | 工具声称可写、曾经允许的计划、模型指令 |
| 知识及适用性：可核验来源+依赖裁决机制 | `EvidenceRecord`/`DerivedClaim`，保留 source version/conflicts/dependents | 最后一份 summary、模型无来源判断 |
| 外部业务结果：受影响资源的真实提供方/文件存储 | `EffectObservation`：远端/文件系统独立读回、时间戳、资源 ref | HTTP timeout、本地 ACK、outbox delivered flag |
| 结果验收：独立 oracle/任务 owner | `EvaluationVerdict`，带任务/评测器/环境版本和证据 ref | 自编测试、流程日志、自产 PASS 字符串 |

数据库可以共用，但每类事实的最终**写权限与仲裁协议**必须明确。授权权威与业务结果权威往往属于第三方，不可能被本地数据库自封替代。

## 2. 候选核心数据契约

所有以下 JSON 都是**结构形状说明**，不是自动生成代码，也不承诺使用 JSON 作数据库格式。

```json
{
  "GoalRevision": {
    "goal_id": "goal-001", "revision": 3, "authority_ref": "trusted-intake:...",
    "scope": ["public_read", "local_draft_write"],
    "success_criteria_ref": "oracle:versioned:...", "effective_at": "UTC timestamp"
  },
  "TaskRecord": {
    "task_id": "task-001", "goal_id": "goal-001", "goal_revision": 3,
    "state": "PENDING", "state_version": 7, "due_at": "UTC timestamp",
    "lease_owner": null, "lease_expires_at": null, "budget_reservation_id": null
  },
  "EvidenceRecord": {
    "evidence_id": "e-001", "origin": "repo/ref/path", "commit_sha": "...",
    "blob_sha": "...", "retrieved_at": "UTC timestamp", "content_digest": "sha256:...",
    "depends_on": [], "validity_status": "CURRENT"
  },
  "ActionIntent": {
    "task_id": "task-001", "action_id": "a-001", "business_intent_id": "intent-001",
    "goal_revision": 3, "task_state_version": 7, "knowledge_fingerprint": "sha256:...",
    "requested_capability": "local_draft_write", "principal_ref": "...",
    "grant_ref": "...", "destination": "isolated/workspace/draft.md",
    "effect_class": "LOCAL_WRITE", "payload_fingerprint": "sha256:...",
    "idempotency_key": "goal-task-effect-v1", "reconcile_method": "read_file_sha256"
  },
  "EffectObservation": {
    "business_intent_id": "intent-001", "provider_effect_ref": "...",
    "state": "UNKNOWN", "observed_at": null, "evidence_ref": null
  },
  "EvaluationVerdict": {
    "task_id": "task-001", "oracle_version": "...", "evaluator_ref": "...",
    "result": "UNVERIFIED", "evidence_refs": [], "limits": []
  }
}
```

含义：`action_id`（逻辑动作）≠ 传输层 request ID；`business_intent_id`（业务意图）≠ retry attempt；`correlation_id`（日志关联）≠ 幂等键。相同意图不同参数必须拒绝或另立明确业务意图，不可重用旧幂等键偷换效果。

## 3. 关键接口：调用责任及可观察结果

| 接口 / 调用者 | 前置条件 | 写入/输出 | 失败或疑义处理 |
|---|---|---|---|
| `GoalIntake.revise(authenticated_input)` | 可信身份/修改权、目标语义一致 | 新 `GoalRevision`，标记受影响任务 | 未授权拒绝；不能删远端历史 |
| `TaskLedger.enqueue(goal_rev, due_at)` | 关联有效目标、范围、预算意向 | `TaskRecord(PENDING)` + 事件 | 重复 `task_id` 幂等，保存历史 |
| `Scheduler.claim(task_id, expected_version)` | 当前到期、未有效被租约占有 | CAS 领取/租约、版本递增 | stale/lease conflict 失败；不能双 owner |
| `Planner.propose(context, evidence_refs)` | 读得可信上下文、成本额度 | 结构化 `ActionIntent` 候选 | 超预算/缺信息 → `NEEDS_REVIEW`，不直接执行 |
| `Admission.decide(intent)` | 当前 goal/knowledge/grant/预算版本有效 | ALLOW/DENY/DEFER + reason + expiry | unknown 授权则拒写；无关只读仍可推进 |
| `ExecutionGateway.execute(intent, permit)` | 检查 ActionIntent 与 permit 的绑定一致，执行前重核 | 受控副作用 + 结果观察引用 | 远端不明 → UNKNOWN/RECONCILE，禁盲重试 |
| `ArtifactStore.read_back(ref)` | 指定正确 owner 与版本 | bytes/hash/mtime 等独立事实 | 不可读不等于未写；标 UNKNOWN |
| `OutcomeVerifier.judge(task, source_ref, artifact_ref)` | 只用独立事实和可审计规则 | VERIFIED/FAILED/UNKNOWN/NEEDS_REVIEW | 规则版本污染→INVALID，不自证成功 |
| `Knowledge.revise(evidence_delta)` | 原始来源版本与依赖可核 | 定向失效/派生 claim 新版本 | 与用户目标矛盾需冲突与来源审查 |
| `Governance.propose_and_stage(failure_evidence)` | 有实际异常或可验证的新失效假设 | 隔离候选、影响范围、回归计划 | 无全路径/邻接正例证据不得晋升 |
| `PromotionAuthority.promote(candidate, evidence, grant)` | 独立、来源真实且当前有效的批准 | 原子晋升候选版本；保留历史 | 缺评测/批准/旧版本→HOLD/REJECT |

关键责任：所有有副作用的执行路径都必须经过同一**可执行权限检查边界**。对 hosted tool、handoff、shell 与独立 worker，不能仅依赖 SDK 的普通 function-tool guardrails。参照 [官方 Agents SDK 说明](https://openai.github.io/openai-agents-python/guardrails/)。

## 4. 状态转换与并发合同

**任务候选状态机**（未冻结字段名）：

```text
PENDING --claim(CAS/lease)--> RUNNING
RUNNING --missing source/approval--> NEEDS_REVIEW
RUNNING --unknown side-effect--> UNKNOWN
RUNNING --observed output, evaluated--> VERIFIED
RUNNING --irrecoverable proven failure--> FAILED
RUNNING --legal retry with new lease--> PENDING
NEEDS_REVIEW --new applicable grant/goal--> PENDING
UNKNOWN --authoritative readback--> VERIFIED | FAILED | NEEDS_REVIEW
VERIFIED/FAILED --new independent task--> [new TaskRecord, not overwrite old history]
```

不变量：状态转换在事务内附 `event_id`，对 `task_id,state_version` 做 CAS；Lease 过期允许重新领取但不代表旧进程已终止，执行层需要 fencing token 或副作用适配器级幂等；事务中写本地状态与 outbox，外部事件消费者接受至少一次投递并去重。

**知识声明状态机：** `CURRENT → QUESTIONED/STALE → SUPERSEDED/RETRACTED`，撤回来源只影响依赖它的推断和计划，不能抹除已经在 GitHub 或外部系统发生的事实。

**远端效果状态机：** `INTENDED → RESERVED → DISPATCHED → CONFIRMED | UNKNOWN | PROVEN_FAILED`。`UNKNOWN` 需对账或受限人工决策，**不是无条件 RETRY**。本地授权检查与远端提交之间依然有竞态；如果供应商不能在其提交点强制权限条件，不能作出撤权后 0 在途效果的普适承诺。

**治理晋升状态机：** `DIAGNOSED → CANDIDATE_STAGED → COVERAGE_TESTED → INDEPENDENT_EVALUATED → AUTHORIZED → CANARY → PROMOTED / HOLD / REJECTED`；任一自证、缺证、过期目标、未经批准、群组指标劣化均不得自动晋升。

## 5. 版本、能力与故障语义

- 所有可重放任务绑定 `goal_revision`、知识依赖指纹、代码/模型/schema/评测器版本。版本切换后可能需重新计划，而非盲目继续旧动作。
- MCP `2026-07-28` 相比 `2025-11-25` 删除协议级会话并修改初始化/Tasks 扩展，说明模型工具连接状态绝不能承载总控自身的长期状态。两版实现不得混用报文格式；具体适配按连接协商。规范历史登记见原 Library 的 `SOURCE_EVIDENCE_MCP.json`。
- GitHub Actions `schedule` 可能丢 tick；`next_due_at` 是任务事实，不是宿主已唤醒的证明。见 [GitHub 官方说明](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)。
- LLM 产出的任何 `APPROVED`/`PASS`/`SAFE` 字符串都只算未可信文本；需经不可伪造的调用者身份、存储中的实际 grant/version 和外部审计构成证明链。

## 6. 接口验证清单

| 编号 | 失败注入 | 独立验收条件 |
|---|---|---|
| IC01 | 两执行者对同一任务 CAS | 只有一个合法状态版本转换；无双业务意图 |
| IC02 | Worker 在本地副作用后 ACK 前崩溃 | 通过独立读回认定结果，不重复产生业务效果 |
| IC03 | 请求发出后供应商响应丢失 | UNKNOWN 保留，读回不支持时不得假设失败 |
| IC04 | 入队后授权撤销 | 还未发送的写入被阻止；合法只读仍继续 |
| IC05 | 执行前目标或知识版本变化 | 旧 action 被拒绝；正确生成新任务或审查请求 |
| IC06 | 异常同时经直连、委托、定时路径进入 | 所有入口执行等效的权限裁决 |
| IC07 | 修复禁掉合法只读旁路 | 回归判失败，不以无越权数量单独认定成功 |
| IC08 | 审批证据仅为模型生成字符串 | 晋升拒绝，审计标出缺可信签发者 |
| IC09 | 同一个来源 SHA 再次检查 | 正确输出 NO_CHANGE，不制造变化 |
| IC10 | 来源 SHA 不同但相关论断没受影响 | 无需无关产物写入，保留负例证据 |

这些是**待实现和运行的未来验收**，不是当前 PR 文档已通过的功能测试。