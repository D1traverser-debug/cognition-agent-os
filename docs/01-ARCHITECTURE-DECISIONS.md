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