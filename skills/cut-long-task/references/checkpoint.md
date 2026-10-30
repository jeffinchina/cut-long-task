# 可恢复检查点

首次执行前、每个工作单元结束后和暂停时更新同任务的紧凑检查点，默认 `.cut-long-task/<线程与任务安全标识>/state.md`。先读现有内容和真实产物，保留用户修改；历史事件单独引用，不反复展开整段旧记录，不记录凭据。`running` 文本不是不可过期的执行锁。

按需保存：

```text
task_id / thread_id / plan_version：
本机 cut-long-task SKILL.md 绝对路径：
状态：running | paused_quota | paused_unverified | blocked | needs_time | expired | completed | cancelled
更新时间 / 用户时区：
目标 / 验收条件 / 原授权范围 / 最新用户修改：
工作目录 / 产物绝对路径 / 适用 AGENTS.md 和其他技能：

mode：fixed | refresh | single_refresh
T：本计划当前有效比例（新用户调用省略时20%；自动节点沿用计划值）
fixed_times：仅 fixed 使用的绝对时间表
delay_minutes：仅 refresh/single_refresh 使用
deadline：可选；来源与是否仍有效
最近真实观测：时间 / limitId / windowDurationMins / usedPercent / R / resetsAt
本节点ID / 版本 / 实际触发时间 / pending-consumed-superseded-cancelled状态：
唯一未来刷新节点：ID / 绝对时间 / 时区 / 配置独立核验结果（无则说明原因）
固定表节点：绝对时间 / ID / 核验结果 / 消费状态（不与刷新模式混用）
本节点消费记录及所接后继ID：
schedule_owner：本次调度维护者的节点ID/主执行轮标识、维护状态及可验证运行状态
decision / reason / 具体错误或硬限制：
是否有已核验未来节点；无节点的原因：

已完成且已核验的成果：
正确半成品 / 已改文件 / 外部操作及结果核对：
下一单元 / 未完成项 / 待做验证与恢复命令：
本任务派生代理的标识、状态、已有成果：
可保留的本地进程/会话及安全查询方式：
本轮之外的同任务执行者的可验证状态（如适用）：
上次有意义通知 / 原因：
```

恢复顺序：

1. 读最新用户限制及当前摘要，核验本节点和计划版本；明确已完成、取消或过期时按终止规则处理。已消费或被替代的重复节点退出，不重建链。
2. 推进工程前读本次实时额度；旧 usedPercent/resetsAt/paused_quota 只作审计，本轮自身 running 不算另一执行者。
3. fixed 只保留尚未消费的未来时间点；refresh/single_refresh 按 [resume-plan.md](resume-plan.md) 使用本次真实刷新时间。持续 refresh 在进入耗时工作或 busy 退出前接好唯一后继；single_refresh 不续建。
4. 实际核验产物和外部动作后，小单元续做并更新；触线保存暂停，结束当前轮，不睡眠等数小时。
5. fixed 最后一次有效机会仍可推进到完成或实际暂停；未完成且需暂停时表已耗尽才记 needs_time。刷新链期限到达记 expired；目标超期限但当前尚可做记 deadline_no_next；无法读额度或创建节点记具体阻塞。完成则 completed，精确清理本任务待执行节点，后续检查静默。
