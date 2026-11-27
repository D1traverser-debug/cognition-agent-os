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

采用下面的一条端到端业务路径检验：[historical 03-FIRST-VERTICAL-SLICE.md](03-FIRST-VERTICAL-SLICE.md)。验收至少有：无变化真实负例、来源已变正例、来源不可用、进程崩溃/双 worker、授权撤销、模型错误结论、原始目标变更，以及预算耗尽。工作区写入最初使用临时目录；**不自动往 `main` 提交生成的结论**。

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

## I. 2026-10-26 架构再判定：拆分“认知决策”与“可信执行”，停止用固定语法扩张冒充通用 Agent

**判定状态：对当前全系统架构的否定性评审；提出可证伪的替代组合，不是完成宣告。** 以前的 H2 中“保留原 Host 并渐进迁移”不能解释为什么原始 G1–G8 的核心能力持续没有出现。当前 Draft PR #50 核对点为 `94aea56cff10a598588cb23d2b648f45e05fba22`、对应 CI #40285610220。后续必须动态复查 HEAD/CI；本节的数字只代表这一核对点。

### 观测到的结构问题（不把诊断当作最终实测成功）

- 当前源码约 51 个 `src/` 文件、684 KB；`open_goal.py` 约 916 行，仍通过少量既有 objective / 局部自然语言模式选已注册子任务。近期要支持 `and then` 时，同时改动 parser、SQLite dependency、worker admission、parent audit、child lineage、Host progress 等多处；是**决策表示层耦合**的强信号，而不只是某条正则写错。
- `capability_dispatch.py` 明确只分派已注册工具，这是**执行安全的优势**，但若由它承担全部认知选择就天然无法在未知问题中自行比较/适配新方案。
- `host.py` 明确不把研究/候选产物晋升为语义或业务目标完成，这是对的；但没有与之相配套的通用自主规划器、竞争方案试验器、面向真实目标的独立结果验收。
- 731 项本地回归和七项 CI 作业成功能保护大量既有约束；模型实验、外部效果、真实 ChatGPT 认知执行、真实业务领域迁移并没有因此全部验收。两周持续补丁与 G1–G8 中目标驱动的陌生任务能力之间，仍存在显著偏差。
- 更早的 `PRODUCT-READINESS-GATE.md` 已于 2026-10-25 选定“目标级 planner/decision policy + on-demand 专家 + 独立 effect reviewer”；后续没有改变主要工程重心。这是**决策到执行的治理失效**，不得再写同一提案掩盖缺口。

### 各竞争方案的对照与明确处置

| 组合 | 直接解决的责任 | 障碍/反例 | 本期处置 |
| --- | --- | --- | --- |
| 原样扩张 `open_goal` 关键词、DSL、任务特例 | 窄场景可预测、可测试 | 每个陌生目标需要新增结构，修同一跨步骤契约常涉及多模块，非通用 Agent | **停止作为认知主路线**；仅修阻断安全/兼容性的缺陷 |
| 全盘重写 Host/SQLite 为 LangGraph/Temporal/托管引擎 | 持久图、事件回放、任务恢复 | 重建授权/独立效果检查，双权威、迁移和运维成本；仍未供给认知或语义验收 | **暂不整体替换**；以真实相同目标和失败注入 A/B 重新评估 |
| 在 ChatGPT/Codex 原生模型与现有工具上直接执行认知循环，以结构化协议调用受控内核 | 今天即可使用已连接的专业检索、真实 GitHub、文件及执行工具，无新增付费模型 API | 原生 ChatGPT 会话与宿主 SQLite 是不同权威面；跨会话自动调用及稳定结果须实测，不能假称 Host 已连通 | **本期主试验路径**：真实任务先证明认知→行动→独立外部读回的改善 |
| 保留单一授权账本、隔离执行、来源/证据/审计，引入模型无关的规划器接口，逐步替换固定自然语言编译器 | 旧有合法执行路径兼容；允许目标级动态比较和修正 | 需要可复用的工具能力描述、动作权限/效果契约和真实目标 oracle；不能凭一个 JSON schema 自证 | **目标实现形态**，但先用真实任务验证接口再迁移；不创建第二个总控 |
| 把 Claude Code Game Studios 的角色/Skill/Hook 直接全套复制 | 工种分离、代码检查、生产流程明确 | 49 专家角色+大量规则对单个父系统可能显著增大协调成本且仍缺可靠业务效果源 | 选择性借鉴职责分离、hook/质量门禁；不复制其数量 |
| AOCI + Graphify + 代码搜索 / Playwright / Caveman | AOCI 提供版本化“架构语义先验”；Graphify 提供结构关系；Playwright 提供页面操作；Caveman 提供可恢复压缩 | 这些都是**工具能力**而非决策总控；AOCI 描述需源证和更新治理，图不等于语义，压缩可能丢目标约束；Playwright 的UI操作不授予写权限 | 在相关任务按需组合接入，分别测试准确性/费用/合法性；不设为强制依赖 |
| UVM 式工程验收 | 将 vPlan/coverage、monitor、scoreboard、SVA 与正反故障注入理念用于 Agent 轨迹和结果 | UVM 是硬件验证方法，不负责开放式 Agent 推理；绿色测试也不能代替真实用户最终效果 | **采纳验收方法**，不复制 SystemVerilog 基础设施 |

### 2026-10-29 来源生命周期与写入路径：失效不是删除

**复现的上层故障：** 私有 Library `/Continuity/General_Learning/cognition-agent-os_ACTIVE_BUILD_STATE.json` 保留了 2026-10-23 PR #26 的 `canonical_delivery` 和 `COMPLETED_SUCCESS_EXACT_HEAD`，但文件仍在当前导航根目录并叫 `ACTIVE`；彼时状态与最新 GitHub 候选 PR #53 冲突。这是来源的**角色/版本失效**，不等于旧内容错误或必须删除。已将该原始 JSON 完整迁入 `/Continuity/General_Learning/2026-10-23/HISTORICAL_PR26_BUILD_STATE_20261023.json`，旧 PR #26 delivery review 同期归档；现行根目录只保留跨项目导航 `INDEX.md` 和属于另一知识主题的 2026-10-19 `MANIFEST.json`。这是独立的私有 Library 效果，公共仓库只引用路径/机制，不复制私有文件。

**取舍与反例：** 参考 [OpenClaw knowledge lifecycle](https://github.com/openclaw/openclaw/blob/main/extensions/knowledge/src/lifecycle.ts)（已核源码，revision/hash 前提检查、superseded/withdrawn 生命周期）及 [supersede.ts](https://github.com/openclaw/openclaw/blob/main/extensions/knowledge/src/supersede.ts)（受作用域与依赖限制），[Letta Context Doctor](https://github.com/letta-ai/letta-code/blob/main/src/skills/builtin/context-doctor/references/auditing-memory.md)（索引发现和加载效果分开验证）。不另建第二个 SQLite 或全局新控制器；先修源头的状态写入/命名规则与现有精确检索路径。**任何新的工程快照**必须带采集时间、来源角色、对应 PR/commit/CI 和有效范围；只在有可靠当前提供方读回时才可称 current，其余存于日期归档，刷新需先以当前源为准再使旧结论及依赖失效。用户原话、实时 provider 与历史工程快照属于不同权威域，不可在搜索结果中互相顶替；隐私删除与版本过期分别处理。无需因旧 PR 已合并/旧快照过期就抹掉审计轨迹。

**三个对照测试：** (a) 新旧快照同名 `ACTIVE`：以 GitHub 实际 PR/head/CI 判角色，不按搜索得分排序；(b) 长索引有一次过期标题：保留历史原文但不得把它视为当前用户目标；(c) GitHub 不可访问：返回当前工程状态 UNKNOWN，旧数据仍可作注明日期的历史证据，不可声称现在有效。上述操作已经实测私人源位置和 GitHub HEAD；但新 ChatGPT 会话是否调用本规则、衍生语义结论是否全链失效，仍未实测，整个产品 **NOT_READY**。

### 当前任务边界修正（2026-10-29，优先于旧的宿主前提）

用户明确将“持续”定义为**由用户聊天唤醒后可靠接续与执行**，而非
7×24 小时自动运行：每次新会话通过当前可用的 ChatGPT、私人 Library、
GitHub 和已安装的 Skill 恢复原始需求、历史纠正、版本/任务现状，
自主质疑研究和执行，真实读回并保留未完成工作；任务过大可在下次
用户唤醒后接着完成。对话外无可证的持续运行不得冒称发生。
Codex Goal/Work、独立 SQLite Host、定时任务和 API 桥接现在均为
**可选后续演进**，不能作为交互式父系统 READY 的前置门槛。
选择新方法前必须实测当前交互式真实效果，并与现有连接工具方案比较，
不为“持续”再造额外自治控制器或第二个目标账本。用户已经允许在真正
完成并通过独立验收后合并运行，但这不是自动认定已通过的证明；
若涉及真实部署、付费、子系统/外部生产写入，仍以具体授权范围为准。

### 优先级反转（约束后续工程行为）

1. **优先完整用户结果，直接使用已授权 ChatGPT/Codex 工具进行真实认知任务**。先恢复用户原始目标及纠正，检查当前来源、权限、实际效果与未验收义务。系统性失败须轮询上层根因，挑战诊断与架构本身，遍历相关一手资料并深度学习实现、反例和替代方案，再比较复用、适配、替换、删除与自建；选择最小充分的整体方案，使用唯一统一候选、明确模块责任与可替换接口，避免重复控制器、固定流程和局部补丁堆积。具体建设依赖见本文件 J 节。合法执行后独立核验完整结果并从最早失真前提重开；有效方法须留出复验才可晋升。简单任务适应性减轻流程，不强制 Host、额外 Agent 或每次单独收据。
2. 对实际轨迹记录 **`Goal → Unknowns → Sources → Competing Plans → Decision & Grant → Executed Effect → Independent Outcome → Correction`**。决策、权限、实际提供方和 oracle 必须分别标注；每次相关任务的来源和最终用户条件都应可重算，不能只记“CI green”。
3. 用**同一批未经专门硬编码的真实任务**对照：(A) 现有固定 Host 模式；(B) 原生模型+真实工具+原有可信授权边界；(C) 经过有证据必要性检验的 SDK/图编排适配器。指标是完整原始目标的独立完成率、用户纠正次数、实际效果、非法/重复动作、从失败到纠正、耗时/调用成本、陌生领域迁移。不得把离线模拟模型通过记作模型能力成功。
4. 只有在 B 的能力边界和工具合同被真实验收后，才将目标级动态计划入口稳定映射到现有 Host/SQLite 的**唯一授权/效果写入权威**。不要让 ChatGPT 会话状态、GitHub 交接或模型生成计划成为新的效果授权真相。
5. 未出现真实目标端到端效果改进，不再以新造 `open_goal` 语法分支、微型状态机、更多检查器或文档数量来声称进展。旧路径必须继续通过安全/兼容回归，但新工作要么交付一个**可独立验收的真实认知→动作结果**，要么明确揭示架构方案不成立。
6. 部署、MCP 服务、付费 API、多租户、子域写迁移不属当前必须执行的动作。架构预留接口即可；真实需要时取得对应授权。普通无关 ChatGPT 会话不强制触发 cognition。

### 可推翻本期选择的证据

- 若真实同条件 A/B 表明某个成熟框架在独立成功率、授权约束、恢复与维护成本上稳定优于“原生模型 + 现有可信底座”，则迁移相应**职责层**，必要时整体换掉本地工作流内核。
- 若同一授权和来源在 Host 多处重复校验造成无法合理证明一致性，优先将共同检查折叠到唯一 Effect/Admission 边界；不能以更多并行检查器解决责任重叠。
- 若不同子域共享调用确实需要跨宿主 ABI/MCP/API，先形成受控适配器而非强迫所有子系统迁移内部状态。
- 若实测证明 Caveman/索引摘要引入目标关键约束丢失，默认退回原文和原始工具输出；压缩或索引不获得覆盖原始任务的权威。
- 需要下一次审核将对比结果填写为 PASS/FAIL/NOT_OBSERVED；本决策目前只获得源码分析与已执行局部回归证据，**尚无真实场景 A/B 通过**。

本轮参考原始官方材料：Anthropic [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)；OpenAI [Agents overview](https://developers.openai.com/api/docs/guides/agents)、[SDK](https://developers.openai.com/api/docs/guides/agents/sdk)、[Evals](https://developers.openai.com/api/docs/guides/agent-evals)；[Temporal](https://docs.temporal.io/workflows)、[LangGraph](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/persistence.mdx)、[AOCI-CODE](https://github.com/aoci-spec/aoci-code)、[Graphify](https://github.com/Graphify-Labs/graphify)、[Playwright MCP](https://playwright.dev/docs/next/getting-started-mcp)、[Caveman](https://github.com/caveman-app/caveman)、[Claude Code Game Studios](https://github.com/zerohours/claude-code-game-studios) 和 [IEEE UVM 1800.2](https://standards.ieee.org/ieee/62530-2/11429/)。所列均为研究来源，不代表已安装、兼容、授权或验收。

## J. 2026-11-27 — User-outcome-first architecture convergence (candidate)

**PROPOSED / NOT_READY.** Supersedes competing implementation roadmaps, not owner goals or historical evidence. Ordinary owner-triggered ChatGPT work is the primary interactive surface. Codex, local Host and MCP are optional adapters for tasks needing them.

- Goal and authority: recover original intent, corrections and live permission; each selected provider owns its objects, state and result.
- Cognition: dynamic decision/execution loops, competing root causes, primary-source research, comparison and counterevidence. Graph records dependencies; it does not prescribe a fixed workflow.
- Application commands: one current decision/effect admission boundary, independent of model/client. Eliminate duplicate semantic submissions only with equivalent authority and behavior tests.
- Effect runtime: reuse the existing ledger, Worker, grant/version checks, isolation and idempotency. External connectors retain native permission/readback boundaries.
- Independent result and learning: verify the complete owner outcome, retain scoped verified methods and counterexamples, invalidate stale dependencies. Graph/fixture success is not business truth.

Prefer a modular monolith for local execution where needed, explicit ports/adapters and a stable authority boundary; native interaction before compulsory orchestration. Reuse event/transaction semantics before adding a scheduler or event store. No new microservice, agent, vector store, plugin manager or fixed goal grammar without a demonstrated unmet obligation. Research reference mechanisms: [Ports and Adapters](https://alistair.cockburn.us/hexagonal-architecture), [Monolith First](https://martinfowler.com/bliki/MonolithFirst.html), [Strangler Fig](https://martinfowler.com/bliki/StranglerFigApplication.html), [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents), OpenAI Agents SDK runner (observed blob d97112c1e71573b6e8c67fcc5e00e0b165f3cc69), LangGraph StateGraph (c23c4c9006edd5c4c8d5e8f0b6b3e146a6da41a3), Temporal Python workflow instance (bcca2648a840ed69106b69c8bcaf78cd412e16ad). These are reference mechanisms, not installed dependencies or verified CAOS outcomes.

Construction order: original owner outcome and evidence; challenge upper architecture; compare source-backed alternatives; converge runtime and Skill governance; establish shared application boundaries; verify real entrypoints, negative cases, interruption and complete outcomes; retire superseded routes only after equivalence. Evidence may reopen an ancestor at any point. No merging, publishing or unique branch deletion based only on CI.

The compound experiment exposed a split between decision records and effect admission. Candidate: one typed compared proposal committed with evidence and action in the existing transaction, retaining operator contract and independent result validation. Preserve explicit graph clients with richer dependencies until equivalence is proven. Open-domain cognition, native fresh-chat selection and cross-task improvement remain unverified.

### Capability composition boundary — implementation candidate

Use a reviewed static method contract in `intent_planner.py` for native objective identity, task kind, source roles and affordances, compilation callback and mechanical acceptance. Catalog, source compatibility and typed compilation derive from the same contract. `capability_dispatch.registered_task_kinds` is the executor identity port; the actual Worker keeps its existing grant/lineage/effect checks. Preserve v1 plan digests and old task receipts. This removes duplicated method routing without creating a second registry authority or arbitrary import capability. The four native methods are not a claim of open-domain cognition or unrestricted third-party plugins.

Compared explicit registration, dependency injection, packaging entry-point discovery and Pluggy hook registration. [Pluggy manager](https://github.com/pytest-dev/pluggy/blob/main/src/pluggy/_manager.py) (blob 572e5b71597d84452217c28185bf82ada2adeb06) verifies hook signature compatibility but loads installed entry points by executing their import; [CPython EntryPoint.load](https://github.com/python/cpython/blob/main/Lib/importlib/metadata/__init__.py) (blob 3d6f9cdf6965bb752aa9b6b516e449036f33e9c9) imports a module. That does not establish a grant or isolate arbitrary plugin effects. Adopt separated interface/explicit composition, not auto-discovery, until a real owner task requires a separately authorized provider adapter. Reopen if this boundary loses prior plan identity, source scope, independent outcomes or creates more extension complexity than it removes.


## K. 2026-11-27 — 通用认知、动态工作流与任务系统构建（候选架构；NOT_READY）

**决策状态：PROPOSED / CONDITIONAL。** 本节落实用户对 CAOS 的直接澄清：父系统不仅要解决单个任务，还要能够在用户提出时，研究、设计、构建和治理其他任务系统、专业工作流与智能体。它不把每个普通任务都升级成系统建设，也不把用户变成需求分析师、工具目录或测试操作员。此决策补充产品目标与认知架构；不代表开放域能力、跨会话 Skill 选用或真实业务结果已经通过验收。

### K.1 完整目标与现有事实

用户要求的认知约束不是线性阶段表，而是防止模型惰性和过早收敛的控制机制：

- 先恢复完整原始目标、约束、偏好、禁止事项和历次纠正，拆分为可追溯义务；不能把摘要、局部子任务或实现建议冒充完整目标。
- 对重要判断轮询竞争解释、反证当前根因和诊断方法，逐层追查目标理解、入口、上下文、来源、工具、工作流、架构、执行和验收；不预设问题一定属于某一层。
- 沿真正会改变方案的相关依赖遍历学习，深读原始规范、现行项目实现、调用路径、测试、失败案例、兼容性和反例；区分“发现链接”“读取字节”“理解实现”“验证适用性”和“迁移成功”。
- 比较复用、适配、替换、删除、暂缓和自建；执行前再次挑战胜出方案及研究覆盖。没有新的区分性证据时不重复空转；仍有可行动反证时必须回到上游。
- 合法执行后独立读回完整用户结果；失败或反证可使最早受影响的祖先决策重新开放。沉淀的方法必须保留适用范围、来源、反例和失效条件，并经新任务验证后才扩大适用范围。
- 常规验证由 Agent 使用已授权工具、沙盒、回归和独立读回完成；用户只处理真实主观取舍、缺失事实和新增授权。不得要求用户反复开新会话、转发日志或补充专业操作清单。

**本轮直接源码证据：**

| 现有部件 | 已核验能力 | 明确边界 |
|---|---|---|
| `cognitive_session.py` | 版本化输入、obligation/hypothesis/source/option/decision/method 等节点、依赖失效与 reopen | 模块本身不运行模型、不拦截其他工具；语义真值和用户结果默认未验证 |
| `native_decision.py` | 竞争假设、先前决策审查、开放研究提案、来源指纹和 CAS | 开放研究提案明确不创建执行器、不排队、不授权、不证明业务成功 |
| `native_local_planner.py` | 模型读取完整目标、既有结果、来源与方法试验，允许追加新来源研究并提出备选 | 当前使用本地 Ollama；输出受当前可用方法目录、输入快照和本地来源范围约束 |
| `intent_planner.py` | 单一可信方法契约及确定性编译 | 当前只有四种 `NativeCapability`；`MAX_STEPS=5`；源码明确声明不支持开放式自然语言理解或不受约束的工具发现 |
| `ledger.py` / `dependency_gate.py` | 同一 SQLite 台账中的任务父子关系与证据释放 | `task_dependencies.task_id` 是主键，每个后继最多一个前驱；当前 gate 只允许少数本地任务类型，不是通用多前驱 DAG |
| `capability_dispatch.py` | 显式静态执行映射，拒绝模型任意导入模块 | 这是正确的执行安全边界，不应被误当成通用认知的全部能力 |
| `owner_postcondition.py` | 对受支持的本地任务产物进行独立、完整目标检查 | 目前不能证明任意外部业务或其他子系统的真实结果 |
| `method_learning.py` / `procedure_evidence.py` | 重新核验跨任务方法使用和原始结果 | 明确不证明方法的因果改善或跨领域泛化；后者仍需独立试验 |

因此，不能得出“CAOS 完全没有动态认知”，也不能得出“现有 Host 已能自主设计和运行任意领域工作流”。当前有认知证据图、受限方法编译器和可信执行注册表；三者的边界必须清晰。**把四种本地方法扩成更大的固定清单，不会解决开放领域的系统设计能力；允许模型任意导入或执行代码，则会破坏现有可信边界。**

### K.2 根因分层结论

| 假设 | 当前证据 | 结论 |
|---|---|---|
| 用户没有讲清楚希望 CAOS 做什么 | 私人原始合同已有递归质疑、深度学习、方法融合、执行前反证和低用户负担等明确要求；本轮进一步明确通用系统架构与构建用途 | **不成立为主要根因**；新澄清需要写入产品目标 |
| 只是缺少更多 Prompt / Skill 规则 | 当前 AGENTS、ChatGPT Skill 和研究 Skill 已有相同原则；本轮对话仍观察到助手先前偏向局部工程问题 | **不足以解释和修复**；不得再以堆提示词结案 |
| Skill 入口是否覆盖其他系统建设 | 原 ChatGPT Skill 描述主要覆盖 CAOS/父子项目续接，没有明确声明“为其他任务系统/工作流做架构与构建”这一目标类型；默认提示还把入口导向“继续 cognition-agent-os” | **源文件级入口缺口已确认**；候选包 v0.1.25 已加入窄触发条件、CAOS 仓库防误路由和概念问答/一次性任务负例。真实安装版本与新聊天首次调用仍 **UNKNOWN / NOT_TESTED** |
| 认知执行偏离 | 当前对话实际发生了把“通用父系统架构”收窄为“修复 GitHub 内部工程”的偏差 | **EXECUTION_LAPSE 已观察**；更深层模型/入口因果仍需真实轨迹区分 |
| 本地执行架构等同于开放域认知 | `intent_planner.py` 固定四类方法；开放研究记录与执行能力分离 | **已被源码反证**；受限 Host 不是完整认知系统 |
| 产品验收遗漏系统构建目标 | 原 ConOps 已写专业系统指导，但没有把“根据用户目标自主研究并构建其他任务系统/工作流”单独列为可验收结果 | **已发现规格覆盖缺口**；本节及 ConOps 补充 |
| 绿色 CI 证明完整能力 | PR #69 的 CI 只证明对应工程检查范围；产品 Gate 仍将原生交互、陌生任务、真实业务结果和迁移列为 OPEN | **不成立** |

**当前最有证据的上层治理对象**是：把“通用认知与系统构建”明确为父系统的一等用户结果；将开放式认知计划与有限可信执行器解耦；为真实系统构建和陌生任务补上独立验收。原生 Skill 选用原因、真实跨聊天行为和真实业务迁移不能用这次源码审计替代。

### K.3 竞争架构比较

| 方案 | 优点 | 关键反例/代价 | 决定 |
|---|---|---|---|
| 固定阶段流水线、不断扩展 DSL/关键词和任务特例 | 容易写静态测试，窄任务可预测 | 新领域需要继续加分支；把认知约束变成仪式；第一版错误仍可能穿过固定阶段 | **不作为通用认知主架构**；稳定子流程可作为局部方法 |
| 纯 Prompt / Skill 自律 | 成本低，适合指导模型 | 没有真实客户端选择轨迹、状态权威、动作边界和独立结果；本轮已有执行偏离 | **保留为指导层，不作为唯一保障** |
| 模型任意生成代码、任意导入工具或自动安装插件 | 表面上最灵活 | 工具发现不等于权限；恶意来源、错误导入、远端副作用和回滚不可控 | **拒绝** |
| 固定数量的多 Agent 专家组织 | 可以分工、并行审阅 | 增加协调、上下文和成本；角色自评仍不是真实结果 | **不设固定 Agent 数量**；只在独立子任务确实可并行时采用 |
| 全盘换成 LangGraph / Temporal / Agents SDK | 可复用图编排、会话、追踪或持久执行机制 | 这些框架不替代目标理解、领域研究、根因判断和业务 Oracle；重写还可能分裂现有授权/效果权威 | **暂不替换**；按具体失效不变量做同目标 A/B |
| **模型驱动的动态工作图 + 单一可信能力/效果边界 + 独立结果验收** | 保留开放式研究、方案比较和任务特定编排，同时约束真实动作 | 需要验证工作图契约能覆盖陌生任务，且不形成第二个任务/授权账本 | **本期目标架构**；先以真实任务验证接口，再决定实现范围 |

### K.4 目标架构：一个父系统、两类循环、一张可回溯依赖关系

**A. 目标契约（Goal / Outcome Contract）**

将用户原话和修订保留为原始权威，派生出可追溯的目标义务、验收条件、硬约束、偏好、禁止事项、假设和授权范围。每条义务关联原始来源和状态；未知、冲突、被撤销和已完成必须区分。用户没有明确给出的专业步骤由父系统研究，不得要求用户代替 AI 设计方案。

**B. 认知与证据图（Epistemic / Decision Graph）**

复用现有 `cognitive_session` 及来源/方法记录，表达目标义务、未知项、竞争根因、来源主张、候选方法、方案、决策、观察和派生结论。边表达支持、反驳、依赖、替代、来源和失效关系。来源版本或上游假设变化时，只使依赖结论失效；未受影响的分支继续。图是证据与推理关系，不是固定执行顺序，也不自动证明语义为真。

**C. 动态工作图（Work / Execution Graph）**

根据当前目标和证据动态生成可执行工作项；可分支、合并、并行、循环、暂停、切换方法和重新规划。每个准备执行的节点至少能说明：

- 目标义务与输入来源；
- 依赖、预期输出和可观察后置条件；
- 所需能力标识及版本；
- 权限范围、风险、预算、超时；
- 幂等/重试条件、失败语义和可行回滚/补偿；
- 独立验收方法及验收方。

工作图是**计划提案**，不是权限或业务事实。优先复用现有任务台账、依赖和事件语义；若现有结构无法表达真实任务的必要依赖，再扩展原有权威，不另建平行任务数据库。 当前 `cognitive_session.depends_on` 能表达多个认知依赖，但不执行任务；当前 `task_dependencies` 每个后继只有一个前驱，且仅覆盖少数本地任务类型。因此，现有系统**尚无可直接执行的通用多前驱工作 DAG**。如真实任务证明 fan-in/多依赖必需，应在原任务台账内把边改为可多行的规范关系，并对每条前驱独立验证、释放和失效；不得把多依赖静默压成线性链。每个工作计划版本的执行依赖应保持 DAG；迭代通过有预算/停止条件的控制器反馈生成新计划版本，不能依赖无界循环边。认知/证据图中的支持、反驳和失效关系则可形成更丰富的网络。

**D. 决策/研究循环（Decision & Research Loop）**

对重要判断持续执行：保留竞争解释 → 找到可区分证据 → 研究原始实现与反例 → 比较适用性 → 反证首选方法和研究覆盖 → 选择下一项有价值的行动。根因可上溯至目标解释、入口、上下文、来源、工具、决策策略、架构、执行或验收；没有证据时保留 UNKNOWN。调查深度按新颖性、不确定性、影响、风险、可逆性和资源成本自适应，不规定固定轮数、固定链接数或必须并行的专家数量。

**E. 执行/反馈循环（Execution & Feedback Loop）**

只执行通过现有可信入口、当前授权和版本复核的动作。读回真实文件、provider、子系统或业务状态，和原始完整目标比较。超时、ACK 丢失和外部未知结果不能盲目重试；区分瞬时失败、永久失败、负面业务结果和方法失效。发现反例时回到最早被推翻的认知/方法/工作流祖先，而不是只重试当前子任务。

**F. 跨任务学习与系统演进（Learning / Evolution）**

这是从真实决策和结果中形成的元层，不是每项任务都要启动的第三个固定流水线。保存方法的来源、版本、适用条件、成本、失败反例、回滚条件和独立结果。一次成功只证明该次结果；跨任务/跨领域迁移必须在新目标上重新验证。Skill/方法文档更新采用候选、留出验证、接受/拒绝和回退；模型自评、相似措辞或单次成功不得自动晋升。

### K.5 能力发现、执行与系统构建的边界

能力发现与能力执行必须分开：

1. **发现**：从当前实际可用的 ChatGPT/Codex 工具、连接器、Skill、官方文档、包/项目源码发现候选；记录来源、版本、真实接口和限制。搜索结果、README、工具描述或示例不等于已连接或已授权。
2. **评估**：检查 schema、数据范围、维护状态、许可证/安全、输入输出、错误语义、成本、幂等、回读与回滚能力。
3. **采用**：优先组合现有能力；需要新适配器/安装/权限/付费/生产写入时，按相应授权边界处理。模型不能自行把候选工具升级成可信执行器。
4. **执行**：工作图只能引用已注册且当前 grant 允许的能力；仍由现有单一 effect/admission 边界执行和记录。不得因为增加动态规划就开放任意 import/eval/shell。
5. **验证**：工具调用成功与系统/业务目标成功分开；使用不与候选生成者共享同一决策逻辑的独立 Oracle。无独立 Oracle 时明确保留 UNKNOWN/NOT_TESTED。

当目标是**构建/改造任务系统**时，父系统应把需求、领域研究、架构比较、组件与接口、状态/知识、动态工作流、权限/安全、失败恢复、评测、部署约束、迁移/回滚和运维作为需要检查的设计维度；实际交付范围仍由目标决定。最终结果应是可运行/可测试的系统产物或明确说明无法验证的部分，而不是只交付一张漂亮架构图。系统构建不得退化为固定模板：每个设计项都要有适用理由、依赖、反例和验收方式。

### K.6 现有架构与成熟实现的学习结论

| 原始实现/资料 | 实际学到的机制 | 适配边界 |
|---|---|---|
| Anthropic, [Building effective agents](https://www.anthropic.com/research/building-effective-agents) | 简单可组合的工作流与动态 Agent 应按问题混用；只在测量到收益时增加复杂度 | 不是要求每项任务都套同一流程 |
| OpenAI Agents SDK, [Runner](https://github.com/openai/openai-agents-python/blob/main/src/agents/run.py)、[Guardrails](https://openai.github.io/openai-agents-python/guardrails/)、[Tracing](https://openai.github.io/openai-agents-python/tracing/) | 真实实现包含多轮 tool loop、handoff、session、interrupt/resume 和 trace；工具级 guardrail 必须覆盖真实工具入口 | 解决运行编排/观测，不提供完整目标理解、根因真值或外部业务 Oracle |
| LangGraph, [StateGraph source](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/graph/state.py)、[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | 节点、条件边、reducer 可表达分支图；checkpointer 的线程状态与跨线程 store 是不同职责 | 图运行时不等于认知质量；不为“需要 Graph”而增加第二个状态权威 |
| Temporal, [Durable Execution](https://docs.temporal.io/durable-execution)、[Activities](https://docs.temporal.io/activities)、[Idempotency](https://docs.temporal.io/best-practices/error-handling) | 事件历史重放、Activity 重试、幂等键和补偿适合长任务/远端副作用 | 负责可靠执行，不负责发现真实根因或判断业务结果 |
| Letta Code, [memory-conflict-repair.ts](https://github.com/letta-ai/letta-code/blob/e43d5d3725c3b8b55da0ab2ec25a4e722353f44a/src/agent/memory-conflict-repair.ts)、对应测试 | 同一冲突签名不重复修复；token/CAS 阻止过期 worker 覆盖新尝试；状态变化才重新尝试 | 只移植失效身份与并发保护不变量，不替换整个父系统 |
| OpenHands, [stuck_detector.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/stuck_detector.py) 与测试 | 从实际事件识别重复 action/observation、错误循环和无进展模式 | 只能检测可观察的重复，不能证明语义根因或自动选出正确新方法 |
| Open Deep Research, [deep_researcher.py](https://github.com/langchain-ai/open_deep_research/blob/279dbffd9e49e07962fb4e1cfeff79e45adc43e9/src/open_deep_research/deep_researcher.py) | Supervisor/Researcher 图、并发研究和原始笔记可组织复杂调研 | 该固定 revision 的异常分支存在 `... or True`，会把任意捕获异常都导向结束；其 LLM evaluator 不是业务真值。不能照搬或仅凭图结构认定可靠 |
| Microsoft SkillOpt, [Training Loop](https://github.com/microsoft/SkillOpt/blob/main/docs/guide/training-loop.md) | rollout→反思→受限修改→留出验证门禁；current/best 分离能拒绝退化候选 | 适用于受控 Skill/方法候选演进，不是模型权重自训练，也不能让自产方法自我批准 |

Datawhale Agent-Learning-Hub 在已固定的来源地图中包含 96 个第一跳链接及递归扩展记录；这只是发现地图。本次深读了与决策循环、图编排、执行恢复、记忆冲突、无进展检测和方法演进直接相关的实现与测试，**不宣称 96 个链接或所有嵌套项目已全部深度学习**。后续研究应由真实未解义务驱动，沿调用链追到原始实现、测试和反例，不按星数或链接数量结案。

### K.7 对当前代码的决定与实施顺序

- 保留 `cognitive_session` 作为认知/证据图；保留原 SQLite task/grant/effect 账本作为任务与副作用权威。两者通过稳定 ID、revision、event/source 引用关联；不再建第二个总控、任务库或知识库。
- 将 `intent_planner.py` 明确视为**受限本地方法适配器**，而不是全局认知规划器。四类能力继续按现有合同安全运行；不得靠不断加自然语言关键词把它伪装成开放域 Agent。
- 保留 `capability_dispatch.py` 的显式执行映射。后续如确有动态工作流需要，先定义模型无关的 typed work-plan/ capability contract，让模型可以组合**当前已授权**能力；新工具注册、安装和任意代码执行仍须经过可信审查。
- ChatGPT 当前交互式工具面与仓库 Host 是同一产品的不同技术面，但目前不假定二者已连通。用户唤醒的 ChatGPT 工作继续使用当前真实可用工具；Host、Codex Goal、MCP/API、定时服务均非交互式阶段的前置条件。
- ChatGPT Skill 源包现有候选版本 **0.1.25**：明确覆盖用户要求架构/构建其他可复用系统的场景；默认提示以当前选定目标为准，禁止未获请求时改动 CAOS 仓库；增加新系统建设与概念问答/一次性任务负例。CI 只构建候选包，不安装/发布；真实客户端首次选择仍须第一方轨迹。
- 先建立系统构建/改造任务的独立验收案例，并用相同目标对比“原生模型+当前工具”与“新增工作图/编排适配器”；只有新增适配器改善完整用户结果、减少纠错且不破坏权限/成本/兼容性时才实现。
- 不为文档、角色、控制器或框架数量计进展。任何代码重构都要保持既有合法路径、授权和结果语义；当前 PR 仍是 Draft，不合并 main、不部署、不做生产写入。

### K.8 可推翻本决策的验收反例

1. **陌生系统构建任务**：用户只给目标、约束和必要授权，不提供专业步骤/工具清单；父系统自主发现权威资料与原始实现，比较至少两种实质不同方案，生成与该任务匹配的依赖图/接口/权限/验收设计，交付可运行产物并独立检查全部原始义务。
2. **普通一次性任务负例**：用户只要求一次简单结果；不得强行搭建系统、启动多 Agent 或进行与目标无关的深度研究。
3. **诱导性第一方案**：首个看似方便的方案被原始规范、真实源码或反例推翻；必须在执行前拒绝并回到研究/根因层，而不是为第一方案补丁。
4. **工具发现负例**：用户未点名一个当前可用且相关的工具；父系统能发现并检查其真实 schema。若该工具未连接/未授权/需要付费，则不能谎称已使用或越权安装。
5. **失败与恢复**：注入来源变化、工具失败、未知 ACK、撤权、重复调用和冷恢复；系统切换实质不同的方法、阻止重复/越权效果，并保持其他合法工作。
6. **知识迁移**：同一方法在未见任务/新领域重新试验；只有独立结果和反例覆盖支持时才扩大适用范围，负迁移必须使旧方法失效或收窄。
7. **入口与用户负担**：普通新 ChatGPT 会话的 Skill 选用必须有真实第一方轨迹；无轨迹标 NOT_TESTED。常规验证不要求用户额外开会话、贴日志或充当测试员。

可推翻条件：如果现有原生模型和已连接工具在相同真实任务上已经稳定完成完整系统构建，新增工作图/Host 编排不带来可测结果提升，则不实现额外规划器；如果成熟框架在相同任务、授权、独立验收、成本和维护指标上稳定胜出，只替换被证明不足的职责层，必要时重新比较整体架构。

**最终状态：架构方向候选已收敛，系统构建这一用户结果已补入产品目标；动态通用工作图、真实原生入口行为、陌生系统构建结果和跨领域迁移仍为 OPEN / NOT_TESTED。不得据本 ADR 宣布 CAOS 上层架构已完成或产品 READY。**
