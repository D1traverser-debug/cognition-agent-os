# cognition-agent-os — 总体架构与候选决策（ADR）

> 状态：**DESIGN PROPOSAL / 未冻结** · 2026-10-20 · 对应 [00-PRODUCT-CONOPS.md](00-PRODUCT-CONOPS.md)。任何技术名称都是备选方案，不得误写成已经部署。

## A. 系统约束优先于框架

本系统的真实产品是**有目标约束、有证据、自主持续推进并能治理自身失效的完整控制系统**，不是一个聊天前端、不受控 LLM 循环，也不是多 Agent 角色集合。先定义权威与不变量，再评估模型编排、任务引擎和宿主。

不可绕过的不变量：

- I-01 目标与授权来自可信主责，不因 LLM 推理、工具描述或检索内容自行提升权限。
- I-02 每项可变事实有明确逻辑写权威；观察副本允许多个，不能各自认定最终真相。
- I-03 每次有副作用的动作在真正执行入口重新检查**当前**授权、目标版本、依赖知识、预算和操作身份；承认远端在途撤权仍有供应商特定风险。
- I-04 持久任务状态与模型对话会话、MCP 会话、HTTP 请求 ID 相互独立；崩溃后能恢复合法工作。
- I-05 UNKNOWN 不是 FAILED；不可重复提交未知结果的远端业务意图，除非有明确幂等/对账合同。
- I-06 任务自述或 CI 绿色不等于用户结果；独立证据源判定有真实效果。
- I-07 自主治理必须从发现走到系统性修复与复发检查；自生成的候选不得自我认证后晋升。
- I-08 授权的合法剩余工作不应因其他任务受阻而全部停滞；必须管理容量和费用。

## B. 候选逻辑架构

```text
外部可信输入 / 用户目标 / Host 事件
             │
    ┌────────▼────────────┐
    │ Control / Authority │ ←目标版本、授权引用、持久任务、预算、事件审计
    └──┬──────┬──────────┘
       │      │
       │      └─> Evidence/Knowledge Store ←版本化来源、依赖、争议与撤回
       ▼
 Decision Engine [LLM / code policy] —> 有限、结构化 Plan/Action Proposal
       │                                  （没有写入权）
       ▼
 Admission + Scheduler [可信代码：当前版本/预算/租约/资源]
       │
       ▼
 Execution Gateway [统一写入口、身份/作用域/参数指纹/操作日志]
       │
       ├── Local Isolated Workspace / Files
       └── Provider Adapter [未来沙箱或外部写入，契约明确才开放]
                     │
       Independent Read-back / Outcome Evaluator
                     │
           Task/Knowledge/Goal Feedback
                     │
  Diagnostics → Failure-class scope → Candidate → Independent eval
                          → Authorized promotion / Hold / Rollback
```

逻辑模块不等于独立微服务。P1 可以让多个模块共享进程与数据库，但必须有可替换接口和执行网关；外部执行和模型进程是否隔离留给实测。

## C. ADR 表：本轮拟议、适用条件、反证

| ADR | 候选默认 | 适用/验证条件 | 可以推翻它的证据 |
|---|---|---|---|
| 01 宿主触发 | 单机真实定时/事件 + 持久扫描作为可逆 P1 基线 | 独立真实唤醒，记录 missed tick，重启恢复 | 目标环境无法持续在线、需要托管触发或跨天等待 |
| 02 服务拓扑 | **对比**模块化单体 M 与核心权威+隔离执行器 H，不预先选 D 微服务 | 六类事实 owner 清楚，故障/性能/运维成本可测 | 故障隔离、租户安全、负载明确需 D 或托管方案 |
| 03 智能规划 | 先以单 Agent + 明确结构化 proposal 作为成本/正确性基线 | 与代码规则、模型版本、预算和负例对照 | 多 Agent 在同预算同目标中稳定提高独立验收成功率 |
| 04 工作流引擎 | 起点关系型任务台账+版本转换+outbox；与 Temporal/托管 workflow 对比 | crash/ACK loss/版本升级的同场景真实故障测试 | 自管任务引擎复杂性或长任务需求压倒其优势 |
| 05 授权入口 | 一切有副作用的适配器穿过可信执行网关 | SDK、handoff、hosted、shell、scheduled 等入口逐一审计 | 有任一绕过时禁止该写入通道，需重新封装/下沉权限 |
| 06 知识系统 | 证据与派生结论分层、维护来源/版本/依赖 | 修改证据能使受影响任务失效、无关任务保留 | 结构化成本过高、实际迁移无益则简化 |
| 07 远端效果 | 意图 ID + 参数指纹 + UNKNOWN 对账，不许盲目重试 | 首个 provider 的幂等时限、查询 API、撤权时点经核对 | provider 不具安全合同则只读/隔离，无资格进入真实写入 |
| 08 独立验收 | 业务 owner/外部真相 + 版本化 evaluator，轨迹只作辅助 | 开发集与隐藏集分开；版本、成本、纠错负担可审计 | oracle 被证明错误时结果 INVALID/UNKNOWN，不“自证通过” |
| 09 自主治理 | 现有工作流内闭环：发现、根因、范围、候选、独立证据、晋升 | 修复跨 sibling 入口及相邻合法动作的回归测试 | 自我评估可伪造或候选影响不可界定则不得晋升 |
| 10 资源调度 | 全局预算保留 + 资源计量 + 公平队列/背压 | 高优任务突发时普通任务仍有正当进展 | 任务成本与数量异质时需按真实资源权重重调 |
| 11 版本与退出 | 目标/知识/模型/执行器/数据 schema/评测分版本 | 旧任务兼容、回退和远端已发生事实对账 | 不能完成跨版本恢复时阻断部署而非假回滚 |

**ADR 状态**：I-01～I-08 是设计前的硬性候选不变量；ADR01～ADR11 均处于 `PROPOSED/CONDITIONAL`，无一项被实测认定为最终生产选择。不可将「有人准备了文档」当成「架构已批准」。

## D. 两个初版可实现的物理组合（非产品结论）

**方案 M（模块化单体）：** 一个项目代码库、单个运行进程内的分层逻辑、关系型数据库事务性任务日志、隔离文件目录。优点为追踪简单，缺点是进程共故障域；须明确 Worker 的异常与内存/进程隔离策略。

**方案 H（核心+执行器）：** 权威/任务台账与受限 Worker 分离，工作单元签入、领取租约、版本复核、事件/outbox、结果对账。优点是执行隔离、能力易封装；需要事件重发、队列过期和版本兼容测试。

两案使用**相同的业务验收情境**，不能给某案凭空打“更先进”或 99.9% SLA。Temporal 与托管 Agent 平台是可比较的工作流与模型执行选择，不等同于控制平面业务权威。

## E. 先实现的结构与故障演练

P1 代码层的候选边界（可调整文件夹名，不应随意改变职责）：`goal_registry`、`task_ledger`、`decision_adapter`、`scheduler`、`authorization`、`execution_gateway`、`source_adapter`、`artifact_store`、`outcome_verifier`、`evidence_graph`、`governance`、`telemetry`。初期可合并部署，但权限执行与独立结果核验**必须保持逻辑独立**。

采用下面的一条端到端业务路径检验：[03-FIRST-VERTICAL-SLICE.md](03-FIRST-VERTICAL-SLICE.md)。验收至少有：无变化真实负例、来源已变正例、来源不可用、进程崩溃/双 worker、授权撤销、模型错误结论、原始目标变更，以及预算耗尽。工作区写入最初使用临时目录；**不自动往 `main` 提交生成的结论**。

## F. 近期需要的决策输入（阻断对应步骤，不阻断草案）

| 输入 | 必须决定的阶段 | 暂行安全选择 |
|---|---|---|
| 初始部署宿主、是否全天候 | 正式持续触发前 | 本地可复现环境，不宣称生产自治 |
| 模型供应商/密钥/费用上限 | 调用付费模型前 | 抽象适配器与离线回放，不储存密钥 |
| 第一业务源与产物落点 | P1 真实运行前 | 公共 MCP 规范、隔离工作区候选 |
| 外部帐户、写动作/幂等/撤权 | P2 外部写入前 | 禁止真实远端写 |
| 用户敏感资料与生命周期 | 真实私有数据前 | P1 仅公共资料、合成任务数据 |
| 组织验证责任人/盲测任务 | 正式能力验收前 | 测试结构可先实现，未知不能填 PASS |

## G. 可核验的来源

- 历史研究：`ARCHITECTURE_DECISION_RECORDS.json`、`AUTHORITY_CONTRACT_CANDIDATES.json`、`QUALITY_SCENARIOS_AND_ARCHITECTURE_OPTIONS.json`、`DESIGN_ENTRY_READINESS.json`，现均存 ChatGPT Library。仓库只提交收敛设计，避免把未审查的历史报告复制为产品代码。
- [OpenAI Agents SDK — Guardrails](https://openai.github.io/openai-agents-python/guardrails/)：工具 guardrail 的真实覆盖限度，尤其不自动覆盖 handoff 和托管工具。
- [Temporal Tasks](https://docs.temporal.io/tasks) 与 [Temporal Workflow Definition](https://docs.temporal.io/workflow-definition)：Worker、工作流事件历史及版本兼容原则。
- [GitHub Actions troubleshooting](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)：schedule 可能延迟/丢失，不是可靠 wake 的单一真相源。

后续接口详见 [02-AUTHORITY-AND-INTERFACES.md](02-AUTHORITY-AND-INTERFACES.md)，操作限制详见 [04-SECURITY-OPERATIONS.md](04-SECURITY-OPERATIONS.md)。

## H. 2026-10-24 实际代码基线与架构重构决策（Draft PR #36，待独立验收）

**原始目标**：用户只输入目标、约束及必要授权；总控主动识别遗漏、针对未知研究原始证据、选择合适方法、在现有可信边界下推进任务，独立从真实目标效果验收，并在重启或新对话中恢复上下文。**这不是把43个 Python 模块等同于43个服务，也不是把测试数量当成完成度。** 原始用户纠正及先前否决的“只做局部补丁、复制多套总控、让用户一再提供精准提示词、生产写入未经授权”始终优先于本文草案。

### H1. 候选目标架构与目前代码的对应

| 逻辑职责 | 当前真实接口/组件 | 已知边界、剩余问题 |
|---|---|---|
| 目标契约及跨运行恢复 | `continuity.py`、`intent_planner.py`、`intent_runtime.py` | `resume_goal` 只读恢复**已登记**的 owner 目标；尚不能自动从陌生自然语言完成全部目标解析。ChatGPT 新会话不能被假设自动读取运行宿主上的 SQLite。 |
| 任务权威、权限、租约及执行生命周期 | `ledger.py`、`runner.py`、`host.py`、`control_kernel.py` | 原有单一 SQLite 保留；架构重构对全层级任务祖先约束进行 fail-closed 审查。Host 仍是被真实操作系统唤醒的有界 tick，不是已安装全天在线的后台服务。 |
| 受限领域能力（adapter） | `capability_dispatch.py` 的静态注册表，调用现有 `knowledge_routing`、`investigation`、`research_*`、`repo_repair`、`goal_loop`、`reconciliation` 等 | 只是可信代码认可的本地/隔离能力；外部写入、任意 Skill 自动安装及自授予工具仍禁止。尚未证明开放世界方法发现。 |
| 来源检索、证据版本与候选推理 | `source.py`、`investigation.py`、`knowledge_routing.py`、`research_gap.py`、`research_assessment.py` | 来源 SHA 证明一致性而非真实性；模型检索不能自证语义正确，撤回/争议和新来源获取尚需真实效果研究。 |
| 行动与不可变产物 | `isolated_filesystem.py`、`sandbox_effect.py`、现有 repo/fixture 执行器 | 本地 sandbox 与生产远端不同；不能由工具成功自动提升为 owner 业务成功。 |
| 独立反馈和闭环治理 | `evaluation.py`、`goal_audit.py`、`conformance.py`、`outcome_feedback.py`、`local_retry.py`、`diagnostics.py` | 存在部分机械验收与重试；真实 owner 目标完成、陌生任务正确性、失败类别全范围修复及合法邻接行为还需独立证据。 |

### H2. 架构取舍

- **采用**：保留一个账本和 Host/Worker，先划定 owner goal/authority → bounded orchestration → explicit capability adapter → independent evidence/outcome 的责任线，迁移现有处理器并通过正负场景验证。
- **不采用**：将43模块重命名为微服务/新增多个自治总控/重写一套任务数据库/直接套大型 Agent 框架。除非经过对照测试发现不能满足边界要求。
- **不采用“一次性替换全部代码”**：此前的完整 blob 遍历只是源身份与结构审查，**不是每项行为都有独立语义证明**。在此信息条件下大爆炸重写会丢失未识别的合法行为。采用有端到端对照证据的递进迁移，更符合风险约束。
- **实施中的兼容层**：`runner.py` 的既有来源读/方案提议接口仍由 compare adapter 使用，以保留旧有失效注入和撤权检测。它是明确的迁移过渡边界，不是第二套控制器；正式能力集合在静态映射中可审查。

### H3. 端到端验收义务和跨会话继承

1. 目标登记及新进程恢复：先验证 `continuity.resume_goal` 的同一目标 ID、授权版本、下一任务身份和已知 `UNKNOWN`，**不**以交接文件/助手记忆伪造授权。出现两个有效目标不能臆测优先级。
2. 研究到行动：必须从用户目标发现真实信息缺口，读取适当的原始来源，明确来源可信与适用条件，提出备选方案并拒绝幻觉来源；该能力**尚未以通用未知任务证明**。
3. 任务传递：不同能力、多层后代在祖先阻止、目标修订、撤权、循环父链及租约竞争时必须拒绝执行；其他合规工作不应被无关失败挡住。
4. 执行与验证：对真实授权动作，观察实际外部效果、未知 ACK、重试幂等、合法相邻动作和失败类修复；没有可独立复核的真实业务结果不得报 READY。
5. 开发对话继承：每次先查**最新用户原始目标/明确纠正**、GitHub PR 实际 HEAD 和确切版本测试，再看根目录 `AGENTS.md` 与单一 `SESSION_HANDOFF.md`。归档交接、旧 CURRENT 与旧 ConOps 只能做历史证据；不可把 ChatGPT 记忆、GitHub 元数据、目标账本当成同一个权限系统。
6. 重构完成判据：与旧版合法路径对照、失效注入、全部当前相关回归、Graphify/AST 可追溯结构、真实陌生任务的独立结果及 owner 纠错负担；任一关键义务未验证，明确保留 OPEN 与 NOT_READY。

**状态：架构契约已梳理，运行时能力分发和完整祖先检查作为改造候选进入 Draft；并没有完成整个自主 Agent OS，也没有任何生产部署或新授权。**
