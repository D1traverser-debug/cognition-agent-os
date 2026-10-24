# 工程认知工具链：AOCI-CODE + Graphify（候选实验，非产品权威）

## 来源、职责、证据等级

**原始需求权威**是用户最初的目标、被批准的边界、历史修订及真实结果，不是交接摘要、代码图或工具 README。总控目标仍是持续推进合法任务，主动发现风险、研究、规划、执行、独立核验、治理与学习。参考 `docs/00-PRODUCT-CONOPS.md`、原始知识库以及 `docs/PRODUCT-READINESS-GATE.md`。不能凭这一文件判定需求已经全部识别、批准。

**AOCI-CODE** 的上游权威资料：
- https://github.com/aoci-spec/aoci-code/blob/v0.1.0-rc21/README.md
- https://github.com/aoci-spec/aoci-code/blob/v0.1.0-rc21/docs/install.md
- https://github.com/aoci-spec/aoci-code/blob/v0.1.0-rc21/AGENTS.md

它提供 **由模型阅读源码后编写**、绑定源文件与 Git 版本、可增量维护的 FRAS 认知索引，正式文件有 `aoci.txt`、`aoci.meta.txt`、`aoci.code.txt`；MCP/CLI 使用厂家自身的 Gov/Guide、比对、CAS、Baseline 及 Recovery 约束。不要自行伪造这套正式索引或凭路径、AST、文件名生成语义，尤其不得把未经审阅的报告写成 `aoci.code.txt` 冒充来源理解。

**Graphify**（现有官方 CLI）的 `graph.json` 是程序结构与调用关系的另一种证据。它可支持识别调用链与影响范围，但 `EXTRACTED` 边也不能证明调用时序、授权、安全结果，更不能代替独立产品验收。CI 中 Graphify 的 `verify_graphify_control_paths.py` 检查的是当前 commit 与关键真实调用边。不能仅用成功生成报告就认定开发 Agent 在决策时真正消费过图。

二者互补：AOCI 用于系统级 FRAS 认知和跨会话持久演进；Graphify 用于具体调用链的可查询结构证据；Git+测试+SQLite 是实际代码及任务执行证据；外部源/真实运行结果才可能构成独立业务验收。

## 本 PR 实际实验

- 在公开、无用户账户凭据的 CI 临时目录，下载官方 `v0.1.0-rc21` Linux/amd64 包；依据预先固定的 `SHA256=4c0d97f48abb096c4cb9d6abe808d910dd0cff39b61bc7b0ea7be4740bb422f5` 复核，并防止 tar 路径穿越。执行官方可执行程序的真实 `--version`、`init`、`scan`、`verify --json`、`check --json`；保存原始机器证据，验证可解析性。
- **供应链证据：**预先固定发布包与 GitHub Sigstore 构建证明包的 SHA-256，再通过 `gh attestation verify --bundle` 校验原始 Release 工作流的证书身份、OIDC issuer、Tag 与源码提交 `cfa8e93ca9fe546a375f48b41b3d4766ed98b013`。这不是对全部 16 个 Release 资产、`SHA256SUMS.sigstore.json` 发布者签名、SBOM 与升级兼容性的 Full verification；高权限部署之前仍需完整供应链审计。
- CI 每次使用独立克隆，`init` 写出的主机绝对路径配置不提交公共仓库；真实项目工作区不被 `aoci init` 修改，不会在开发主机上悄悄安装 MCP。
- **只执行官方 bootstrap。** CI 不能由无模型脚本按文件名自动形成专业语义，不能完成 FRAS authoring、正式 Baseline 对齐、AOCI MCP Host 的全上下文读入或新会话独立理解。JSON 状态固定声明 `whole_index_authored=false`、`actual_mcp_host_connected=false`、`index_semantics_verified=false`。
- 增强 Graphify 必须识别的路径，使其覆盖 Host→本地目标控制器→合同审计以及 Conformance→独立结果审计。新增路径必须由**真实官方 graph.json 的 EXTRACTED calls** 实证；如果工具不能提取，审查调用源码/解析边界，不应随便将要求降为 INFERRED 来刷绿。

## 进入真正 AOCI 持续工作前必须验证

1. 固定目标 repo 与被审的 Git SHA；确认 scope 覆盖主要源码、规格、测试、CI、SQLite schema（数据库 schema 如需索引必须依实际官方支持验证，不得臆造支持 SQLite 连接）。
2. 审查上游 release 供应链，对发布者签名与构建来源进行验证（本试验只有单包构建证明，非 Full verification）。
3. 在有权操作该项目的**真正 MCP Host** 中，用原版 `aoci` 初始化并重启/重新加载；按厂商 Guide 让模型阅读完整源码、权威要求后，逐项编写 F/R/A/S，不用机器填充假语义。
4. 官方 `verify`、`check` 对齐后，再以含 **旧 PR 最新变更、跨会话冷启动、目标版本修订、撤权、未完成工作准确恢复** 的盲测验证“是否真正少犯错”。仅 token 节省不构成正确性证明。
5. 修改代码后必须回写 AOCI 受影响对象，基于 Git diff、Graphify 关系检查、独立 oracle 与实际 CI 结果完成验证。未能再对齐或没有完整 Overview 应 fail closed，不能宣称掌握全局。
6. 仍保留职责分离：开发 Agent、AOCI索引作者、语义复核者和独立业务验收应有清晰证据角色。一个模型换几种人设并不构成独立验证。

## 预先列出的失败模式

陈旧索引被当作现状、遗漏管理范围、模型编造文件职责、AOCI 自身退化但 CI 未发现、图边缺失/错误推断、跨会话索引未读取、脚本仅检查存在而非实际使用、历史 OT 标识发生语义碰撞、修复破坏合法 sibling 操作、同库哈希被误当外部签名、外部数据中嵌入指令、工具更新的供应链漂移、CI 通过被错判成业务目标实现。

**当前产品状态：NOT_READY。** 本文件和实验没有宣称 AOCI 已正式在你的 Codex/本机上线。

## 2026-10-24 上游原始方法对照与架构纠偏（实验候选）

此前断言“不是五个 Agent”没有经过证据支持，予以撤回。**单一任务/授权账本不等于单模型或单角色**：规划、检索、工具执行、独立复核可以各用单个或多个 Agent；真正需要保持一个权威的是用户目标、授权、任务事务、外部效果和审计事件。多角色的独立性必须由真实来源/隔离输入/不同 oracle 体现，而不是同一模型切换人设。

原始材料及可复用边界：
- [AOCI-CODE 上游 README 与 AGENTS](https://github.com/aoci-spec/aoci-code)：实际产品是源码阅读后模型编写的版本化 F/R/A/S 全系统认知索引；原版 MCP `aoci_rules → aoci_overview` 支持整索引身份、分块/收据、挑战式认知校验与上下文压缩后重新加载。**采用其原版索引/维护协议，不自行重写“可供模型使用的完整认知”**。但检验索引语法与模型复述不等于原始用户需求正确，也不提供生产执行控制。
- [Graphify 官方项目](https://github.com/Graphify-Labs/graphify)：复用其真实 AST/tree-sitter 图、`EXTRACTED/INFERRED` 区别及 source-located 调用路径做变更影响分析；不以单个抽取边证明代码语义/调用时序。现有 CI 运行官方 Graphify 和跨模块调用证据，下一步应以真实改动的影响路径测漏检，而非仅出图。
- [Temporal Workflow 与 Activity](https://docs.temporal.io/workflows)：把 LLM/API 等非确定性操作放在 Activity 内，结果进 Event History；重放不会再运行已完成的 Activity。它解决 crash/replay/可追溯执行机制，但**不保证外部不可知 ACK 一定只产生一次效果**；还需要提供方幂等键和对账。是否整体采用 Temporal 必须与现有 SQLite Host/Worker 在同样崩溃/授权/补偿场景做 A/B，不能凭文档另造并行控制器。
- [LangGraph 结构化流程](https://docs.langchain.com/oss/javascript/langgraph/thinking-in-langgraph)：节点状态、有限分解、pause/resume、人类授权与异常分类可作复杂目标决策编排候选；并不自动给出某个目标的独立正确性 oracle。
- [OpenHands 隔离运行](https://github.com/OpenHands/docs/blob/main/openhands/usage/architecture/runtime.mdx)：工具和代码执行置于 Docker sandbox，作为危险候选执行隔离参考；不替代用户授权或实际用户效果验收。
- [Lost in the Middle（原论文）](https://arxiv.org/abs/2307.03172)：信息出现位置会影响长上下文检索表现，是针对性评测模型遗漏而非全称断言“模型必然不确定”的实证依据。

针对本项目的因果拆分：模型可能错误定位证据/遗失上文，但近期已经证实的跨入口后置写入漏洞主要是**程序员未复用共享许可路径且验收用例缺失**，不能归咎为随机采样。前者用原版 AOCI/Graphify + 位置调换/冷启动测识别率；后者用统一事务+原始状态事件+变异测试处理；长任务中断/未知 ACK 再与 Temporal 的实际 Activity 语义等价对照。

**可证伪实验而非产品承诺**：相同固定代码修复任务及隐藏跨模块反例，比较“源码全文检索”“仅 Graphify 图”“AOCI 原版完整模型索引 + Graphify”（在真正 MCP Host 上）；记录遗漏路径、模型认知挑战正确率、合法邻路被误阻止率、所需用户纠错次数和检索成本。当前只能运行**隔离 AOCI 官方 bootstrap**（无模型 authoring/no MCP host），所以不能把这些候选的名义能力登记为本产品已具备的能力。系统继续 NOT_READY。
