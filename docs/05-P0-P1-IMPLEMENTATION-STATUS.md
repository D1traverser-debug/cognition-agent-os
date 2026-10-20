# P0/P1 实际工程状态（2026-10-20）

> **DRAFT IMPLEMENTATION / 不可宣称自治总控已完成。** 本文对应 Draft 文档 PR #1 的 [03-FIRST-VERTICAL-SLICE.md](03-FIRST-VERTICAL-SLICE.md)。代码 PR 从文档分支派生，保持 `main` 不变。

## 1. 已实现的可执行边界

- 标准库 Python CLI，**必须由用户或外部宿主调用** `worker-once`；未启用 cron、Actions、付费云任务、模型调用或自动发布。
- SQLite WAL 任务记录：入队、领取、租约、任务版本、目标版本、授权撤销、后续任务预定、事件日志。
- 公开 GitHub 源适配器：仅 `api.github.com`，强制 `owner/repo` 与完整 40 位 commit SHA，对返回的字节按 Git blob SHA 重新核验；另有受限本地 fixture 模式。**运行测试通过 mock GitHub API 响应，没有真正部署 GitHub 定时抓取。**
- 可替换规划器的**确定性差异基线**：源相同 → `NO_CHANGE`；源不同 → `CHANGE_REQUIRES_REVIEW`。不会声称 LLM 已理解业务影响，也不会将自生成结论晋升权威。
- 本地写入受隔离工作区和当前授权约束。SQLite 写事务跨越授权复核与 O_EXCL 文件创建；崩溃后通过与原定 bytes 比对恢复。不宣称任意网络请求 exactly-once。
- 产物技术核验：重新读回文件，校验 hash；源证据在执行中二次读取。**这不是独立人工/模型语义验收，也没有构成真正的外部 Provider 业务确认。**
- 授权在源读取期间撤销，最终事务状态为 `BLOCKED` 并如实返回；合法的无变化只读仍然可以完结。

## 2. 17 项可复算测试

执行：`PYTHONPATH=src python -m unittest discover -s tests -v`。

检查范围：无变更不假报、变更待审、来源错误 UNKNOWN、撤权后合法余项、目标版本过期、两个 worker 争抢、实际子进程在领取后崩溃、写入后确认前崩溃与读回恢复、篡改产物 UNKNOWN、周期任务持久化不冒充 host、路径逃逸阻断、GitHub URL/ref 校验、已知 Git blob SHA、二次源读取期间撤权、提交后哈希核验、GitHub SHA 伪造拒绝、两真实进程竞争。

**调试真实发现**：初轮曾出现“数据库已 BLOCKED，但 CLI 误报 NEEDS_REVIEW”；已修正为执行后按权威任务表读取实际状态，覆盖回归测试。最终 17 项全部 PASS。

## 3. 与架构验收 VS01–VS14 的关系

| VS | 当前测试状态 | 缺口 |
|---|---|---|
| VS01 真实规范变更与影响 | `PARTIAL` | 能比较 fixture/读取 GitHub pinned commit；尚无真实 LLM/独立语义裁决 |
| VS02 不变负例 | `EXECUTED_LOCAL` | 本地相同源不造假；真正远端相同 commit 未独立执行 |
| VS03 变化但不影响 ADR | `NOT_IMPLEMENTED` | 没有语义相关性裁决 |
| VS04 源 403/404/网络失败 | `PARTIAL` | 受限错误分支、mock；未做真实远端 403/429/重试成本 |
| VS05 写后崩溃 | `EXECUTED_LOCAL` | 子进程退出恢复；非远端 API exactly-once |
| VS06 领取后崩溃 | `EXECUTED_LOCAL` | 人为置租约过期后恢复，未长时间真实时钟试验 |
| VS07 争抢 | `EXECUTED_LOCAL` | 双独立子进程仅一个实际处理；不含跨主机/断网 |
| VS08 授权撤销 | `EXECUTED_LOCAL` | 覆盖本地受控写；远端在途无法保证 |
| VS09 目标变更 | `EXECUTED_LOCAL` | 旧任务被拒；复杂知识依赖尚未实现 |
| VS10 模型错误引用 | `NOT_IMPLEMENTED` | 未接入模型，也无真实独立语义评分 |
| VS11 宿主丢 tick | `NOT_IMPLEMENTED` | `next_due_at` 已存，但无实际独立 scheduler |
| VS12 预算上限 | `NOT_IMPLEMENTED` | 零付费调用，尚无全局额度账本 |
| VS13 产物篡改 | `EXECUTED_LOCAL` | 哈希读回能检出，但需要可信存储防护 |
| VS14 自评 PASS | `PARTIAL` | 默认不允许自动语义成功；独立 oracle 未建立 |

## 4. 需要在下一轮立即改进的技术问题

1. **真实 host**：cron / systemd / Actions /托管等实际触发证明；当前 CLI 没有后台能力，不能叫“自动运行”。
2. **模型适配**：接口支持真实 LLM 有界计划，保证所有模型输出仅作为 proposal；需批准供应商和费用。
3. **独立语义 oracle**：真实关联 ADR 的含义判定和人工/外部可核对正确性，而非 diff 自证。
4. **宿主/安全/运行强化**：对路径 TOCTOU、lease/fencing、目录权限、受限磁盘、供应商 429、持续运行账单做真实负载测试。
5. **状态和版本迁移**：当前 schema 为可逆 prototype，尚无受支持的正式数据库迁移和版本兼容。

## 5. 非目标

不修改旧 UAOS、`main`、仓库可见性、默认规则、GitHub 凭据或托管任务。不把这次测试当成自主发现未知风险、系统性治理或自主学习晋升的证明。初版只是完整总控未来需要的一条真实工程基础链。