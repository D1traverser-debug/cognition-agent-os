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
- **供应链保证只有 pinned BASIC SHA**，并未用 Sigstore/Cosign 验证 publisher 身份；没有达到官方推荐的身份认证级别，不能用于高权限部署。上游安装文档详述 Cosign 的 `verify-blob --bundle`、证书身份与 OIDC issuer，后续真正安装需补上该步骤。
- CI 每次使用独立克隆，`init` 写出的主机绝对路径配置不提交公共仓库；真实项目工作区不被 `aoci init` 修改，不会在开发主机上悄悄安装 MCP。
- **只执行官方 bootstrap。** CI 不能由无模型脚本按文件名自动形成专业语义，不能完成 FRAS authoring、正式 Baseline 对齐、AOCI MCP Host 的全上下文读入或新会话独立理解。JSON 状态固定声明 `whole_index_authored=false`、`actual_mcp_host_connected=false`、`index_semantics_verified=false`。
- 增强 Graphify 必须识别的路径，使其覆盖 Host→本地目标控制器→合同审计以及 Conformance→独立结果审计。新增路径必须由**真实官方 graph.json 的 EXTRACTED calls** 实证；如果工具不能提取，审查调用源码/解析边界，不应随便将要求降为 INFERRED 来刷绿。

## 进入真正 AOCI 持续工作前必须验证

1. 固定目标 repo 与被审的 Git SHA；确认 scope 覆盖主要源码、规格、测试、CI、SQLite schema（数据库 schema 如需索引必须依实际官方支持验证，不得臆造支持 SQLite 连接）。
2. 审查上游 release 供应链，对发布者签名与构建来源进行验证（本试验只有哈希校验）。
3. 在有权操作该项目的**真正 MCP Host** 中，用原版 `aoci` 初始化并重启/重新加载；按厂商 Guide 让模型阅读完整源码、权威要求后，逐项编写 F/R/A/S，不用机器填充假语义。
4. 官方 `verify`、`check` 对齐后，再以含 **旧 PR 最新变更、跨会话冷启动、目标版本修订、撤权、未完成工作准确恢复** 的盲测验证“是否真正少犯错”。仅 token 节省不构成正确性证明。
5. 修改代码后必须回写 AOCI 受影响对象，基于 Git diff、Graphify 关系检查、独立 oracle 与实际 CI 结果完成验证。未能再对齐或没有完整 Overview 应 fail closed，不能宣称掌握全局。
6. 仍保留职责分离：开发 Agent、AOCI索引作者、语义复核者和独立业务验收应有清晰证据角色。一个模型换几种人设并不构成独立验证。

## 预先列出的失败模式

陈旧索引被当作现状、遗漏管理范围、模型编造文件职责、AOCI 自身退化但 CI 未发现、图边缺失/错误推断、跨会话索引未读取、脚本仅检查存在而非实际使用、历史 OT 标识发生语义碰撞、修复破坏合法 sibling 操作、同库哈希被误当外部签名、外部数据中嵌入指令、工具更新的供应链漂移、CI 通过被错判成业务目标实现。

**当前产品状态：NOT_READY。** 本文件和实验没有宣称 AOCI 已正式在你的 Codex/本机上线。
