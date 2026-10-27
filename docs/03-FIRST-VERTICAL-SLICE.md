# cognition-agent-os — P0/P1 首条端到端自治闭环合同

> 文档状态：**PROPOSED / NOT IMPLEMENTED** · 2026-10-20 · [运行目标](00-PRODUCT-CONOPS.md) / [架构候选](01-ARCHITECTURE-DECISIONS.md) / [接口契约](02-AUTHORITY-AND-INTERFACES.md)

## 1. 这条任务存在的原因

首个任务是**验证完整总控具备一条可独立启动、受控执行、独立核验并持久继续的真实能力链**，不是把最终产品缩减为“技术规范订阅助手”。任务选用公开版本化技术规范，因为数据确实存在、可以重复检查、许可读取、能构造真实正例和真实负例，而且结果会影响工具调用架构。

建议初始对象：`modelcontextprotocol/modelcontextprotocol` 的指定**稳定版本**规范文件，与仓库存档中另一指定版本比较。历史已实际观察 `2025-11-25` → `2026-07-28` 的规范变化。源仓库路径、commit 与 blob SHA 在 P0 时钉定；**不要**只把易漂移的 `main` 当成不可变历史真相。GitHub 属于来源事实 authority；模型只负责解释变化可能影响哪些候选 ADR。

## 2. 目标合同

**输入：** 经许可的目标修订、公开来源 `repo/ref/path/expected SHA`、之前来源快照、关联架构 claim ID、独立宿主触发事件、任务预算、获准工作区写入范围、当前 grant 版本。

**用户可观察结果：** 不是回复一段“已检查”，而是有可核对的记录：`NO_CHANGE` 或 `CHANGE_PROPOSED` 或 `UNRESOLVED`；真实 upstream SHA；变更范围；对应的 ADR/接口依赖；带时间和来源的受控产物；独立验证结论；下一次可被宿主触发的持久任务。

**初版允许：** 公开 GitHub 读取，向隔离的本地工作目录写版本化研究草稿，读回文件并保存任务/证据事件。**禁止：** 自动 push/merge `main`、公开发布内容、使用用户私有账户、自动变更正式安全策略、发起未经允许的收费调用或真实外部业务写入。

## 3. 一次正常执行的时序

1. 外部 scheduler 产生真实唤醒，独立记录 `trigger_id,observed_at,host_ref`。**没有真实唤醒时必须报告 `HOST_TRIGGER_UNAVAILABLE`，不得以手动调用冒充自治。**
2. 数据库扫描 `due_at`，用 CAS/lease 领取一项任务；记录目标版本、知识依赖和预算预留。
3. 读取当前允许的公开源与 GitHub immutable ref，保存内容 SHA、blob SHA、响应状态和来源定位。
4. 与经过批准的旧快照比较：同一 SHA 进入 `NO_CHANGE`；SHA 变化但不涉及关联 claim 则记录 `CHANGE_IRRELEVANT`；内容不可核验则 `UNRESOLVED`。
5. 如存在潜在影响，给 LLM **结构化、无写入权**的变更摘要输入，得到 `claim_id, evidence_refs, hypothesis, confidence/uncertainty, proposed_update`；不要因模型高置信度直接晋升。
6. Gateway 依据当前目标、授权、预算与路径白名单，允许写入隔离工作区；写入产物采用业务意图 ID/哈希和安全落盘方式。
7. 独立 checker 二次抓取/核对 immutable upstream SHA，重新读回产物 bytes/hash，检查是否捏造差异、是否越权写入，不能仅执行同一个模型的自评分器。
8. 任务进入 `VERIFIED/NEEDS_REVIEW/UNKNOWN/FAILED`；记录真实指标和被用户修正的次数；保存下次 `due_at`，**下次是否触发仍需 host 实证**。
9. 发现失败类别时生成隔离治理候选，走系统性范围/回归/证据/晋升链；不得在 P1 中直接自我改正式运行规则。

## 4. P0：先探明真实环境，不虚构运行能力

| P0 项目 | 可接受证据 | 无法完成时的准确记录 |
|---|---|---|
| 真实独立唤醒 | cron/systemd/GitHub Actions/托管 schedule 的外部日志与任务因果 ID；非聊天“继续”消息 | `HOST_TRIGGER_UNAVAILABLE` |
| 实际持久存储 | 重启前后的任务与 artifact 实际读回；主机路径与保存位置 | `DURABILITY_UNVERIFIED` |
| 单次最小预算 | 有效调用者批准的成本额度、运行配额、timeout | `MODEL_CALLS_DISABLED`，可先离线/确定性处理 |
| 公开源和输出 | 真实公共 ref，隔离工作区路径且不泄露账户数据 | `SOURCE_OR_WORKSPACE_UNAPPROVED` |
| 模型运行环境 | 本地或供应商模型版本、输出格式、调用费用和隐私用途 | `LLM_NOT_CONNECTED` |

在 P0 阶段可以实现宿主能力 spike 和离线模型接口；不因未配置付费密钥而把整项研究中止。

## 5. P1：必须通过的正例、负例与故障测试

| 编号 | 实际输入/故障 | 期望行为 | 独立事实源 |
|---|---|---|---|
| VS01 | 指定两版规范确有变更 | 指出真实字段/语义差异和具体受影响 claim；不自动批准方案 | GitHub commit/blob SHA，原始文件对照 |
| VS02 | 同一 immutable commit 再检查 | `NO_CHANGE`，不创建新的“变化报告”，但记录检查事件 | 上游 SHA + 工作区文件列表 |
| VS03 | 来源变化但不影响某条 ADR | 该 ADR 不被随意废弃或改写 | 独立审核来源与 claim 依赖 |
| VS04 | GitHub 403/404/网络故障 | `UNRESOLVED`，不编造来源或变更 | 真实 HTTP/connector 结果 |
| VS05 | Worker 已写文件后被杀死 | 下次唤醒读回产物并继续，不重复业务效果 | 文件系统 hash + SQLite 历史 |
| VS06 | 领取任务后进程退出 | 租约过期后被新 worker 合法领取 | 两个独立 PID + 持久 ledger |
| VS07 | 两个 worker 同时竞态 | 单任务只有一个正确状态 owner；无未经授权重复写入 | CAS 状态版本 + artifact 事实 |
| VS08 | 写入许可被撤销 | 不再写；可执行的只读检查仍可继续 | 授权 owner 记录 + 文件时间戳 |
| VS09 | 上游目标/方法版本变化 | 旧计划失效或待审，不能按旧目标自动修改产物 | GoalRevision 与依赖指纹 |
| VS10 | LLM 捏造引用或错误结论 | checker 拒绝，原始错误保留为评测样本 | 独立 source fetch 与人工复核 |
| VS11 | 真正的 host missed tick | 下次到来通过 `due_at` 补扫未完成任务 | 外部 host 运行记录 + ledger |
| VS12 | 成本/调用数到达上限 | 停止超限开销，记录必要负例与合法余项 | 预算 ledger + 实际提供方账单 |
| VS13 | 产物在验收前被篡改 | hash 与读回不符，不能标 VERIFIED | 受控存储原始 bytes + checksum |
| VS14 | 仅自生成 grader 返回 PASS | 不能独立验收，进入 UNVERIFIED/NEEDS_REVIEW | 不同 owner 的读回与评分记录 |

**测试阶段标志：** `SPECIFIED` → `IMPLEMENTED` → `EXECUTED` → `INDEPENDENT_VERIFIED`；文档中的全部条目目前只是 `SPECIFIED`。

## 6. 交付物和观测字段

- `source_snapshot.json`: `repo,ref,commit_sha,path,blob_sha,content_digest,retrieved_at`；明确 Git SHA 与本地文件 hash 是不同证据类型。
- `impact_proposal.json`: `goal_rev,claim_ids,changed_sections,evidence_refs,decision,uncertainty,planner_model_rev`。此文件不是正式权威。
- `review.md`: 人可读差异、影响假设、未解决分歧；无变化时可以只保存紧凑的 `no_change.json`。
- `task_ledger`: `task_id,state_version,due_at,trigger_id,lease,goal_rev,grant_ref,action_intent_id,observed_effects`。
- `evaluation.json`: `verdict,oracle_version,artifact_hash,source_commit,verified_at,evaluator_ref,notes`。
- `resource.json`: `calls/tokens/runtime/retries/actual billed cost if available`。

以上文件名与字段仅是初始契约，源代码实现必须遵守等价语义；外部副作用待 P2 provider 沙箱时另立合同。

## 7. 建设与验收阶段，避免伪成功

- P0：实测可唤醒宿主、存储与权限；失败时保存事实，不编造技术能力。
- P1：交付完整 **宿主→合法目标→持久任务→规划→受控本地写→独立读回→新到期任务**；用户无需再发消息时才计入自治事件。
- P2：选一家具可用沙箱、幂等和读回接口的 provider；再验远端效果/ACK 丢失/撤权限制。
- P3：故障类别跨入口治理、邻接合法动作回归、可信候选晋升。
- P4：第三方陌生任务与真实用户效果、用户纠错负担、跨模型和架构成本对照。

**完成标准必须分离**：`CODE_WRITTEN` 不等于 `TEST_PASSED`，`TEST_PASSED` 不等于 `INDEPENDENT_OUTCOME_VALIDATED`，一轮用户触发不等于 `HOST_AUTONOMY_VALIDATED`。

## 8. 对首轮开发的最低要求

代码必须允许替换 source adapter、model adapter 和 host scheduler，保障同一验收场景横向比较；P1 可以先使用安全离线模式实现流程，但不得把离线计划器说成真实 Agent。真正决定框架前先测 P0/P1，允许由实证修改 [01-ARCHITECTURE-DECISIONS.md](01-ARCHITECTURE-DECISIONS.md)。所有 GitHub 发布、权限和成本约束遵循 [04-SECURITY-OPERATIONS.md](04-SECURITY-OPERATIONS.md)。