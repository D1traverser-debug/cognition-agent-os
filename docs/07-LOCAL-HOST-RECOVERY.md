# P2 候选：Windows 本机定时宿主与持久恢复

## 目标 / 限界

使用现有 SQLite 文件和任务队列，不消耗任何远程模型 Token、试用积分、付费 API。Windows Task Scheduler 属于本机 OS 组件，独立于聊天消息唤醒 `host-tick`。本仓库只提供显式 opt-in 的注册脚本；**提交代码并不等于用户电脑已经安装或运行了任务**。本候选尚不具备真实语义验收、未知风险自主发现或自动进化能力。

不使用 GitHub Actions 定时任务来保存 SQLite；GitHub Runner 是临时机器，跨 run 本地 DB 会丢失。GitHub Actions 继续只做公开仓库的免费 CI 测试，不执行本机 scheduler 或创建远程状态。

## 手动本机预备（Windows 11、Python >=3.10）

将开发分支检出到用户信任的固定本机目录。项目无需 `pip install`。以 PowerShell 在仓库根目录执行：

```powershell
New-Item -ItemType Directory -Force .\fixtures | Out-Null
Set-Content -Path .\fixtures\v1.txt -Value 'spec v1'
Set-Content -Path .\fixtures\v2.txt -Value 'spec v2'
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures seed-fixture --old v1.txt --new v2.txt
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures host-tick
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures status
```

此处 fixture 是验证任务，不是长期真实工作目标。`host-tick` 仅处理到期任务，上限默认 16，支持参数 `--max-jobs 1..64`。未种任务/不存在现有 DB 时退出 `HOST_NOT_CONFIGURED`，不会为定时服务自行授予写权限。

## 定时启动（仅用户显式执行后生效）

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_windows_host.ps1 -IntervalMinutes 5
Get-ScheduledTaskInfo -TaskName CognitionAgentOS-Local
```

注册脚本在当前用户上下文运行，不保存远程密钥、不配置云模型、不覆盖同名任务。无管理员策略环境限制时可注册；具体是否允许运行由实际 Windows 安全策略决定。任务每约 5 分钟尝试触发，Windows 关机/睡眠/未登录时不保证执行；恢复执行时查询 SQLite `due_at`，补做尚未完成的到期任务，不伪造错过的每个 tick。

停用：`Disable-ScheduledTask -TaskName CognitionAgentOS-Local`；移除：`Unregister-ScheduledTask -TaskName CognitionAgentOS-Local -Confirm:$false`。不要直接删除仍有 RUNNING 任务的数据库文件。`runtime/` 已被 `.gitignore` 排除，任务数据不应提交到公开仓库。

## 可验证与仍未验证

- 自动测试：跨独立 Python 子进程重启任务不重做、过期周期任务补做、撤权不重新授权、限制每次工作上限、无 DB 不自动初始化，以及单行 `host_ticks` 本机 tick 记录。
- `host_ticks` 仅证明本程序曾在某个时间完成 tick，不能单独证明 Task Scheduler 已被安装、定期真实触发或离线运行。实际宿主证明需核对 `Get-ScheduledTaskInfo` / Windows 任务历史、数据库 tick 递增及真实进程运行记录。
- SQLite 本机单机权威，**不**表示多设备共享、云端持久任务、实际 Ollama 模型或独立语义裁决。新增任务仍需由明确目标/可信输入入队；定时运行没有解决自主目标分解与问题发现。
