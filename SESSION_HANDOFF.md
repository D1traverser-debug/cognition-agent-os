# cognition-agent-os — 可核验工程交接（2026-10-27）

> **用途：恢复导航与工作台账，非最高权限、非用户原始对话、非产品运行时事实。** 唯一开发仓库为 `D1traverser-debug/cognition-agent-os`。继续工作先获取用户当前要求和可访问的原始纠正，再读取 GitHub 所有相关未关闭 PR 的真实继承关系、当前 HEAD、源代码与**同一 HEAD** CI。以下 SHA 和作业数据只是本次核验快照；**不得当作以后会话的实时状态。** 不得把私人对话全文复制到公开仓库。

## 1. 产品主线：哪些是用户要求，哪些不是

用户要求交付 ONE opt-in 认知父系统：保留完整原始目标和所有明确纠正，能自主拆解需求、发现遗漏、质疑人和模型的假设、寻找并学习专业资料/现成实现、比较复用/改造/替换/新增、选择合法方案、执行、独立核验**真实用户及子业务结果**、失败后主动换方法、长期维护并跨会话继承，面对陌生专业任务也能迁移，**减少用户补充工具和纠正错误的工作量**。角色/Skill/工具链是实现手段，不是目标本身。

用户明确纠正的优先级：ChatGPT/Codex 现有工具能力下的**真实认知—研究—执行—纠偏闭环优先**；可以关键词/项目上下文触发，普通 ChatGPT 请求不强制走父系统；本地/云部署、始终在线 Host、付费 API 和跨平台商用是**后续、需授权**的阶段，不应拿它们当作目前拒绝直接工作的借口。视频、金融写作、小说、A 股等子系统保有各自任务身份、业务状态、数据、效果验收及独立授权，父系统不得接管子系统私有权限。

**已废弃：** `universal-agent-os` 及 `uaos-controller-runtime` 不再是当前父系统入口；旧 UAOS 仅作为历史迁移依赖，不得让其自定义指令重新支配产品。已废弃“先另做一个独立 GPT 开发系统，再开发认知父系统”的两阶段说法。固定 CSV/JSON、模型提示词、绿色 CI、编写交接文件不等于完整业务目标完成。

## 2. 责任位置：什么放哪里，谁读取、何时更新

| 责任/唯一来源 | 现有入口或文件 | 操作和更新规则 | 已验证程度 / 不得冒充 |
| --- | --- | --- | --- |
| **用户真实目标、修改与取舍** | 私人当前/历史对话、Project 与合法可见源 | 用户直接话语高于任何摘要；保留原始完整条件，纠正废弃旧假设；在新任务/继承时重新检索，不把私人原文发布到公共 GitHub | 公开仓库只能存去敏概述，无法证明历史私聊全文可恢复 |
| **ChatGPT 按需认知入口** | `integrations/chatgpt/cognition-agent-os-chatgpt/skills/cognition-parent-chatgpt-intake/SKILL.md` 与 `plugin.json`（源码版本 `0.1.3`） | 明确 `cognition-agent-os` / `继续` / `继承` 时，先恢复目标、阅读本交接指针，再验 GitHub 实况，继续实际工作；正常聊天不能被劫持 | GitHub 源码不等于已装入账户；当前账户实际 Skill 字节/首次自动触发/错误触发，**未在本快照独立证明** |
| **Codex 工程规则** | 根目录 `AGENTS.md` | 作用于本仓库工程工作；需求→候选方案→比较→改动→独立结果→删并冗余；日常小改用轻流程 | 文件存在和 CI 检查不等于每个 Codex 会话实际遵从 |
| **Codex 专项深度研究** | `.agents/skills/goal-grounded-semantic-review/SKILL.md` | 重大/反复失败时读取真实源码、材料、失败轨迹、替代方案；不是第二层控制器 | 真实加载和改变决策的成功率尚未对照测量 |
| **Codex 会话重建** | `.codex/hooks.json` → `scripts/codex_session_context.py` | 被受信任的客户端实际触发时优先读**既有** SQLite 原始任务；没有本地状态库时读取 `docs/PRODUCT-READINESS-GATE.md` 的现阶段优先级、要求重新验 GitHub；不产生授权与任务 | 已有 subprocess/真实命令测试；**未证实用户 Codex 应用实际启用 Hook**；Codex Hook 不是 ChatGPT Hook |
| **当前工程实现和提交历史** | GitHub 未关闭候选；当前工作候选 Draft PR #50 | 代码改在**原集成 Draft**，提交后读回；PR 说明保存简要候选结论；完整文件变更和每次提交以 GitHub Commit/Diff 为准 | Draft 未合并 main，分支与 PR 编号不可成为永久规则 |
| **主线与整体验收** | `docs/PRODUCT-READINESS-GATE.md` | 保存长期全产品义务及用户确认的当前 opt-in 优先级；不得用本交接的下一步建议覆盖原用户要求 | 六项终极产品门槛目前仍 OPEN/NOT_READY |
| **产品持久任务/授权/执行** | `src/cognition_agent_os/ledger.py`、`host.py`、`runner.py`、`control_kernel.py`、`capability_dispatch.py` | 仅**真正已初始化的本地 SQLite/Host**能持有对应运行时任务、授权和结果；Worker 负责受限执行；反查原始事实、拒绝越权 | 测试 Host/SQLite 可以运行，不等于此 ChatGPT 对话已连接用户机器的常驻 Host |
| **工具与客户端接口** | `native_mcp_bridge.py`、`cli.py`、`scripts/verify_native_mcp_transport.py` | 只在已授权、本地配置真实存在时暴露相应工具；外部效果需要独立权限和读回 | Linux/Windows MCP stdio 已测试，**未证明账户级 ChatGPT ↔ Host 连通** |
| **子业务任务真实身份和验收** | 子系统各自仓库及其 live 接口；父级 `domain_contract.py` 仅检视 | 子系统拥有私有任务 ID、数据、业务验收与许可；父级只能依合法接口治理与协同 | 读取/校验子系统契约不等于完成任何视频、文章、小说或 A 股业务结果 |

**更新时机而不是新建一套账：** (a) 每次 ChatGPT/Codex 新会话按需恢复用户目标→核实 PR/HEAD/CI/实效；(b) 重要设计决定先比较候选并明确反证，再合法修改原 Draft；(c) 失败必须检查真实日志、修补共同责任边界并复测；(d) 每个阶段验收后只更新本文件的事实快照、PR 简短检查记录和涉及的单一权威源码，旧 SHA 自动降为历史；(e) 新需求或用户纠正，先修正产品门槛/废弃旧优先级，不通过追加新控制器代替决策；(f) 未验证的激活或外部结果明确标记 UNKNOWN。

## 3. 实际做过的工作——按行为和源码分组，不用口头“已经实现”代替证据

下列是当前 PR 可见的**能力族工程工作盘点**，不是每项均满足全部用户目标。完整增删文件与逐笔提交在 [PR #50 Files changed](https://github.com/D1traverser-debug/cognition-agent-os/pull/50/files) 和 [PR #50 Commits](https://github.com/D1traverser-debug/cognition-agent-os/pull/50/commits)；不在交接中复制数百条旧流水账。

| 已执行工作 / 真实组件 | 做到什么（限定范围） | 有什么还没做到 |
| --- | --- | --- |
| 原始目标/更正保真及恢复 | `continuity.py`、`goal_fidelity.py`、`goal_drift.py`、`goal_audit.py`、`ledger.py`：登记原目标、运行中状态/漂移线索、冷恢复和既有事实审计 | 不能从已删除私聊自动恢复全文；尚无真实跨 ChatGPT 账户与持久 Host 的端到端恢复证据 |
| 一个授权与执行内核 | `ledger.py`、`host.py`、`runner.py`、`control_kernel.py`、`capability_dispatch.py`：既有 SQLite grant、任务/事件、Worker 执行，有限调度、权限及状态隔离 | 没有真实用户环境中授权部署的常驻执行证据；固定注册工具不足以独立执行任意陌生技能 |
| 执行效果安全与独立核验 | `sandbox_effect.py`、`conformance.py`、`reconciliation_oracle.py`、`owner_postcondition.py`、`outcome_attestation.py`、`signed_feedback.py` 等：局部源/文件/结果重读、不可自认证、回滚/拒绝和沙箱隔离测试 | 独立真实子业务效果及外部 provider 权限/回执未完整证明 |
| 本地目标/反馈/修复多条路线 | `goal_loop.py`、`open_goal.py`、`intent_planner.py`、`native_decision.py`、`native_local_planner.py`、`bounded_goal_control.py`、`outcome_feedback.py`、`repair_* / repo_repair.py` 等：预定义任务、候选选择、有限验证反馈纠正和错误诊断 | 多条历史控制/规划路径存在复杂度与责任重叠；**未证明已收敛成普适认知闭环，不能先按名字删除** |
| 主动调查与现有工具发现 | `investigation.py`、`knowledge_routing.py`、`research_gap.py`、`research_assessment.py`、`public_tool_discovery.py`：开展有界研究、部分公网 GitHub 元数据候选检索、原文证据审视与工具适配线索 | 搜到的工具还**不能自动成为 Worker 可合法执行的新能力**，不是通用网络研究/动态工具链证明 |
| 真实代码、研究评测与反例实验 | `scripts/verify_p19_unfamiliar_model.py`、`verify_p20_external_quixbugs.py`、`verify_p21_live_issue.py`、`verify_architecture_ab.py`、`measure_real_*.py` 和对应 tests：开展不同级别的公开代码/本地/实际模型实验；Graphify、AOCI、LangGraph、Agents SDK、Claude Code Game Studios 等曾被检索比较 | 工具“被研究过”不等于安装/复用成功；脚本/CI 不能证明大模型在任意专业任务能稳定完成 |
| 子系统接口与边界 | `domain_contract.py`、`scripts/verify_live_child_holdout.py` 等：读取/比对子系统契约，避免把父任务身份误当子任务、阻止未经授权的跨域写入 | 父→子合法执行→子业务独立验收→父失败纠偏的真实完整闭环仍未验收；没有授权改子仓 |
| ChatGPT 插件与选择入口 | `integrations/chatgpt/.../SKILL.md`、`plugin.json`、`scope-probes.md`：按需触发、动态项目识别、恢复/权属/输出优先；安装包曾制作并测试文本一致性 | 当前 GitHub Skill 更新不会自动更新账户插件；未实测所有新会话自动触发 |
| Codex SessionStart 恢复与入口 | `.codex/hooks.json`、`scripts/codex_session_context.py`、`tests/test_codex_session_context.py`：按已有本地 SQLite 恢复，缺失时退回现存产品优先级；真实子进程/命令复测 | 这是测试进程，不是用户 Codex 客户端实际加载证明 |
| 模型/程序责任对照 | [真实模型实验 #40383600804](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/40383600804)：可审的局部合成正例 deterministic **2/2**；未模拟的 Qwen coder 0.5B **0/2**、Qwen 1.5B **0/2**。 `native_decision.py` 增加 CSV/JSON 明确原目标准入保护；`native_local_planner.py` 可在准确合同下零模型调用计划。 | **没有测试 GPT-6/Codex 的开放式研究能力**；0.5B 安全拒绝不等于学会选择，程序正例不等于陌生任务自主完成 |
| 本地正例经真实 Host 双 Tick | [CI #40425970215](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/40425970215)：明确 CSV/JSON 的程序优先计划，通过同一 Host/Worker/SQLite 和独立本地读回；Linux/Windows 各 812（Windows 跳过 5） | 沙箱任务结果不能外推到外部生产或子业务结果 |
| 入口/历史记录减负与历史责任纠正 | 2026-10-27 `AGENTS.md` 由约 14,388→7,669 字符；PR 说明由约 58,899→约 6,597 字符（随后因新检查记录又增长），静态“绑定旧英文原句”测试改为迁移边界语义校验 | **运行时代码尚未完成证据驱动的删并**；文本缩短不能证明认知能力提升 |
| 无本地库的 Codex 恢复断点 | `scripts/codex_session_context.py` 增加读取已有产品验收文件的现阶段优先级；`docs/PRODUCT-READINESS-GATE.md` 把冲突的 10/25 旧优先级标历史，保留 10/26 用户确认的 opt-in 优先级；新增启动无库/有库对照 | 不能证明 Codex 实际用户会话中的 native Hook 已被受信任客户端加载 |
| 原生任务调度被新任务饿死 | `native_local_planner.py` 改写候选选择，最早未完成原目标优先；无本地模型的不可执行请求不得耗尽可执行容量，已独立验收的目标仍能回报已完成；测试 130 个后来的陌生目标和混合任务 | 这是调度公平性，不是陌生任务的认知决策能力 |

**最近实测纠偏证据（不要省略失败）：** 首次调整 Native 调度导致已完成目标被误报为需要模型，[红色运行 #40434899922](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/40434899922) 暴露，随后修复并在最后已核验 HEAD `552024137208d1a2ced271870ae523f1949239a5` 的 [CI #40435086831](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/40435086831) 通过：Linux **815/815 OK**、Windows **815 中 5 个平台跳过，其余 OK**；Docker、Linux/Windows MCP stdio、跨平台 CLI、Windows scheduler、Graphify 检查均 success。这是 HEAD 匹配的工程回归，**不是整个产品 DONE**。

截至上述快照，该 Draft 有 **359 commits、248 changed files、约 +53,452 / -1 行**，包含 54 个运行时 Python 模块；这些数字提示累加风险，不等于所有文件都应删除。每次继续必须重新获取真正实时的统计和分支关系。旧 UAOS/其他仓库的历史证据不得充当本项目产品进度。

## 4. 当前责任/完成状态：不能把不同层冒充彼此

- **已工程验证：** 某些本地明确目标从注册→合法计划→Worker→沙箱/文件独立验收；部分有限反馈纠错；真实代码/工具发现的局部实验；Host/SQLite/CLI/MCP **测试环境**；Linux/Windows CI；本地 Codex Hook 子进程测试。
- **未证实产品交付：** 未预置陌生专业任务中 GPT/Codex 自主寻找可用证据/工具、比较并实施**真正不同**的方法，完整原始结果独立验收及失败后闭环纠偏；真实 ChatGPT Skill 自动按需激活率与账号版本；真实账户↔持久 Host；真实子系统业务结果回执/独立治理；独立无人持续运行；显著减少用户纠正。**总产品状态 NOT_READY。**
- **未做/不许声称做了：** 没有合并 `main`、部署、付费 API、产品环境无人代理、取得新授权、改写子系统仓库或生产数据。未经验证的 Agent/Skill/第三方架构仅是候选。
- **没有必要继续的惯性：** 继续训练 0.5B 提示词以代替强认知、增加新的固定 CSV/JSON 词法模板、叠加新的调度器/控制账本、更多静态自评、在 PR 描述里滚动复制全部历史。

## 5. 交接后下一件必须真正做的事（不是新规划任务）

在**当前合法工具范围**，用现有 ChatGPT/Codex 高能力研究和已连接工具选择一项真实、此前未被上述局部任务编码的工程/子领域问题：保存全部用户要求→独立找真实专业规范与对照方案→选择可执行方法→取得实际授权范围内的最终效果→在源头独立读回；遇到失败换方法→比较既有框架与当前实现成本。以**用户目标完成度、未见任务迁移、用户纠正次数、方案变更有效性、执行时间/成本和冗余代码收敛**为验收，而非“搜到了”“做了文档”“815 绿”。优先走现有 ChatGPT/Codex 和 GitHub 连接；不需要为了开始就买 API、部署 Host 或强迫用户提供工具清单。涉及真实子系统授权/发布/付费/不可逆外部效果时严格停在授权边界。

下一位执行者进入时：先恢复**当下用户任务**、确认实际可调用的工具和权限→读本文件做索引→查最新 open PR/HEAD/源代码/CI（历史 PR #50 不是永久锚点）→挑一个真正推动原始目标的工作**直接实施并读回**。若没有权限，只能如实记录阻断点，不能把“新建下一步计划”算完成。

_2026-10-27 检查快照，编辑后的当前 HEAD 必然变化。GitHub 提交历史是不可变追溯来源；本文件是便于新会话快速理解的导航，不是单独的真相或授予权限的凭据。_
