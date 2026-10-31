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

1. **当前直接使用已授权 ChatGPT/Codex 工具进行真正的认知任务**。每次必须保留原始要求与关键纠正，主动搜到足够一手资料并挑战候选因果解释，在同等成功条件下比较至少两个适用解法，实际选择可行路径，检查真实工具/文件/外部结果，失败继续纠正。简单任务适应性减轻流程，不固定七项表单或 Agent 调用。
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



## J. 2026-10-31 历史 Draft：UAOS 父级绑定迁移候选（2026-11-01 起不再是当前工作流）

**状态更正（2026-11-01）：** 本节保留的是一次历史迁移审计与候选方案，不再定义当前 owner-selected workstream，也不授权迁移四个子系统。当前目标是先证明 **cognition-agent-os 自身的认知/演化闭环**：完整目标恢复、竞争根因诊断、第一手研究、方案反证、授权执行、独立 owner outcome、程序性学习与跨任务迁移。UAOS 子域迁移仍是独立目标，只有 owner 重新明确选择时才启动。此更正优先于本节中“当前优先候选”的历史表述，并与 `AGENTS.md`、`docs/PRODUCT-READINESS-GATE.md` 一致。

**新用户目标（不是对方案正确性的证明）：** 在 cognition-agent-os 内，每次工程决策都必须执行恢复原目标与失败经验、定位问题与竞争根因、阅读适用的一手源码/测试、比较 reuse/adapt/replace/delete/build、提出可推翻选型的反例、合法执行、真实结果独立读回、沉淀有效方法与失效条件。简单已知事项可以缩小研究成本，但不能跳过目标、反证和验收。不得仅靠这段规则声称 ChatGPT 新会话已自动执行。

**观察（源代码与正式业务状态）：** 2026-10-31 四个子域的 manifest+adapter+capability 仍指向旧 UAOS，原审计仅扫描 `manifest.binding`，遗漏 `manifest.parent_control_plane` 顶层规范性引用（A 股子系统实际存在该字段）。本 Draft 修改 `domain_contract.py` 复用同一个只读合同审计入口，增加顶层扫描，并补反例：将 controller 字段改为新认知父级，但保留顶层旧 parent 字段时必须报告旧依赖且不能授予迁移权限。保留未知域与合法原路径，不写子系统数据。

**更强的反例（子域实际测试）：** `video-growth-agent/tests/test_uaos_current.py`、`financial-writing-agent/tests/test_uaos_cognition_evolution_inheritance.py`、`novel-writing-agent/tests/test_authority_behavior_contract.py`、`a-share-event-driven-agent/tests/test_common_behavior_binding.py` 都包含硬性旧父级假设。因此迁移时不仅需改变 JSON 引用，还必须以原业务验收替代这些旧架构字符串断言；否则新接口正确也会被旧测试拒绝。不能把调整测试为绿色当作业务验证。

**竞争方案与再质疑：**

| 候选 | 价值 | 反例及成本 | 处置 |
|---|---|---|---|
| 全盘复刻 UAOS 再一次性切换 | 旧接口表面兼容 | 继承旧错误、难以明确业务收益；隐藏绑定会造成假迁移 | 否决默认采用 |
| 旧 UAOS 与新系统长期双控制器共存 | 短期兼容 | 两个权威、额外维护、相互矛盾 | 否决作为长期终态 |
| 一次性重写四个子域并删除 UAOS | 清理速度表面最快 | 业务 ID、长期素材/正典、授权与回归难独立证实 | 暂不授权 |
| 逐能力迁移／必要时重构整个子域，真实验收后删除对应旧接口 | 可测试可回滚、能优先移除确认无用的能力 | 临时过渡层可能变成永久负担；需设置退出验收 | **当前优先候选，继续挑战** |

**一手方法证据：** [Martin Fowler《Strangler Fig》](https://martinfowler.com/bliki/StranglerFigApplication.html) 强调目标导向、按可替换业务边界逐步交付，而不是逐字照搬旧实现；[AWS Strangler Fig](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/strangler-fig.html) 说明转换、共存、删除旧功能与回滚风险；具体 Agent/记忆/工作流方案先沿已有 Agent-Learning-Hub 方法卡进入源码与反例，不引入额外控制器。

**最强反证：** 如果某子域新架构无法实现合法旧任务、不能独立观测效果、对最新资料的记忆继承失败或有旧 UAOS 隐含权限依赖，则不应以“新代码更少”宣告迁移成功。反之若某旧功能完全无调用者或被独立替代且可回退，应优先删除它，而非以“历史兼容”无限延期。

**实施与验收边界（历史决策）：** Draft 曾修复一处实际旧引用漏检，不意味着整域接管。后续若 owner 重新选择该迁移目标，仍须对一个业务场景进行旧路径与新候选的真实同任务对照，测量全目标完成、用户纠错次数、成本、原业务状态/权限、失败恢复与负迁移。

**工程合并权限更正（2026-11-01）：** owner 已将工程合并就绪判断委托给 assistant；assistant 可在独立检查完整 owner goal、相关独立 review、exact-head CI、未解决 P0/P1/P2、rollback 与 acceptance evidence 后自行决定合并 main，无需逐次申请合并批准。这是判断权限，不是必须合并，也不放宽产品验收。部署、付费 API、子系统生产正典写入、私有 transcript 发布及插件账号发布仍需各自明确授权。


## K. 2026-11-01 当前工作顺序：先证明认知/演化闭环，不以局部工程量替代

**当前 owner-selected objective：** 完成 cognition-agent-os 自身的 cognition/evolution loop，而不是 UAOS child migration、静态文档审计、额外 graph/controller 或 CI 数量。完整闭环是：恢复原始目标与纠正 → 定位竞争根因 → 研究一手来源 → 比较并反证方法/工具 → 在当前 grant 内执行 → 独立读回 owner-meaningful outcome → 形成带适用条件/失败条件/反例的 procedure → 在不同任务中重新验证、迁移或失效回滚。

**已修复的窄范围 P2（Draft PR #62，NOT product acceptance）：**
- auditor 与 sandbox effect 统一使用 128 KiB artifact bound；66,387-byte 有效 goal-case artifact 回归验证 exact audited bytes 被 stage。
- goal-case audit failure 绑定 exact observed artifact digest 到 research-reentry CAS；不同 corrupt byte revisions 不得复用旧 CAS；audit verdict 使用真实 status 分类。
- source/evidence failure 时只允许当前注册 root、当前 SQLite goal/grant/write authority 下的 scoped read-only investigation；披露后重查 grant、original goal 与 exact source digest；决策/动作 admission 仍关闭。

**下一项真正的产品缺口不是再加固定 grammar：** 当前 `intent_planner.py` 仍只注册有限 objective；`public_tool_discovery.py` 能发现 metadata，但不等于把新工具安装为可执行 Worker capability；`owner_postcondition.py` 只独立验证少数明确的本地结果。必须用一个真实、此前未为系统硬编码的 owner goal，观察 native model/tool 选择、实际合法执行和独立 owner outcome，再与 incumbent 在同等授权/输入/时间预算下 A/B。若没有真实 client/Host trace，标记 NOT_TESTED。

**程序性学习边界（2026-11-01 更新）：** `knowledge_candidates` 仍是 root-scoped、source-pinned、unverified candidate；`signed_outcome_feedback` 仍是受签名/holdout 约束的窄领域反馈，不是通用跨任务 method library。新增 `procedure_evidence.py` 是只读投影：从同一 SQLite ledger 中最多扫描 64 个当前 grant 下的其他 native roots，只把“原始完整 owner-local postcondition 现在仍可独立复验、且对应最后一个已登记 intent”的不同 goal 结果作为 prior procedure-family trial 提供给 native local planner。fingerprint 排除 task-specific resource paths；model 必须自行判断适用性。每次重新计算，source、artifact、goal/grant revision 或 lineage 失效会移除旧 trial；不同 objective 不会互相借用。它不写新表、不提升 memory、不创建可执行 capability、不授权行动，也不证明 general method transfer 或 cross-domain transfer。当前只验证“同一已注册本地 capability family 曾在另一个不同 goal 上通过完整 local owner oracle”，不是可迁移 procedure 已学会。

**当前状态：NOT_READY。** Draft PR、绿色测试、模型文字或方法卡均不能代替 first-turn fresh ChatGPT session activation、陌生 owner task 的独立结果与纠错负担测量。当前唯一活跃集成面为 PR #62；产品/交互验收仍 OPEN。
