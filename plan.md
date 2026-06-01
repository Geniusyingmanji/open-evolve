# 自进化开放优化 Agent 项目计划

## 1. 目标与北极星指标

目标：构建一个可复现、可扩展的自进化 agent / multi-agent 系统，在 Frontier-Eng、MLE-bench、ALE-Bench、RE-Bench 等开放性优化 benchmark 上持续提升分数。

核心评价不只看最终分数，还要看优化效率：

| 指标 | 含义 |
|------|------|
| Best feasible score | 固定预算内的最高可行分数 |
| Normalized improvement | 相对初始 baseline / benchmark reference 的归一化提升 |
| Cost per improvement | 每次有效提升消耗的 token、wall-clock、GPU hour、eval calls |
| Feasibility rate | 候选解通过硬约束和运行验证的比例 |
| Diversity / novelty | 高分候选是否来自不同 idea/operator/lineage |
| Reproducibility | 同 seed / 同 artifact 是否可复跑得到一致结论 |
| Effective Feedback Compute | 预算中真正转化为有效反馈并被后续决策使用的比例 |
| Process quality | 轨迹是否按探索、实现、验证、总结的合理顺序推进，避免 lucky pass |
| Harness regression rate | harness / workflow / memory 改动是否破坏已有任务能力 |

## 2. 总体技术路线

采用“四层进化”，把 harness 作为一等优化对象，但把源码级自修改放到最后：

```text
Level 1: Candidate Evolution
  进化任务解本身：代码、ML pipeline、启发式算法、工程参数。

Level 2: Operator / Skill Evolution
  进化 agent 的操作符 prompt、调试策略、领域 skill、检索策略。

Level 3: Harness / Workflow Evolution
  进化可配置 harness：ACI、工具集、上下文构造、验证门、角色分工、budget allocation、模型路由。

Level 4: Source-Level Harness Evolution
  在审计、回放、回滚机制成熟后，才允许修改核心 runtime / dispatcher / state machine。
```

第一阶段主攻 Level 1、Level 2 和配置级 Level 3。DGM/SICA/MOSS/Live-SWE-agent 式“agent 修改自身源代码”后置，只有在 evaluation harness、沙盒、轨迹审计和回滚机制成熟后再启用。

## 3. 系统架构

```text
open-evolve/
  benchmark_adapters/
    mle_bench/
    ale_bench/
    frontier_eng/
    re_bench/
  core/
    artifact_store.py
    evaluator.py
    search_controller.py
    operators.py
    memory.py
    model_router.py
    budget.py
    trace_recorder.py
    feedback_compute.py
    process_evaluator.py
  harness/
    harness_spec.py
    registry.py
    context_builder.py
    tool_router.py
    verifier_registry.py
    replay.py
    mutation.py
    governance.py
  agents/
    strategist.py
    implementer.py
    debugger.py
    evaluator_critic.py
    researcher.py
    safety_auditor.py
  experiments/
    configs/
    runs/
    reports/
  skills/
    mle/
    algorithm_engineering/
    gpu_kernel/
    operations_research/
```

关键抽象：

| 模块 | 职责 |
|------|------|
| BenchmarkAdapter | 统一加载任务、初始解、约束、评估器、预算和 score schema |
| ArtifactStore | 用 git branch/patch 保存候选、父子关系、日志、score、成本 |
| EvaluationService | 沙盒执行，支持 lint/debug/proxy/full eval cascade |
| SearchController | Greedy、MCTS、MAP-Elites/island、hybrid depth search |
| OperatorLibrary | 初始化、局部修改、debug、merge、hyperparam、simplify、restart |
| MemorySystem | 任务 notebook、episodic traces、verified skill library |
| MetaController | 动态调整 operator/model/budget，做 novelty gate 和 early stop |
| HarnessSpec | 声明一个 agent harness 的工具、上下文、记忆、验证、角色、路由和预算策略 |
| TraceRecorder | 统一记录 thought/action/tool/result/score/cost/feedback retention |
| ProcessEvaluator | 对轨迹质量、lucky pass、无效循环、缺失验证进行二级评分 |
| HarnessRegistry | 保存 harness 变体、适用任务、回归结果、成本曲线和晋级状态 |
| HarnessGovernance | 控制 harness mutation 的权限、审计、回放、promote/rollback |

推荐的 `HarnessSpec` 最小 schema：

```text
HarnessSpec = {
  name,
  version,
  task_family,
  agent_roles,
  tool_policy,
  context_policy,
  memory_policy,
  verification_policy,
  feedback_policy,
  search_policy,
  budget_policy,
  promotion_gates,
  rollback_policy
}
```

## 4. 里程碑

### Phase 0：环境与基线复现

交付：
- 跑通 MLE-bench lite 或 3-5 个 selected Kaggle-style tasks。
- 跑通 ALE-Bench 2-3 个 selected tasks。
- 如果 Frontier-Eng 环境可用，先接 3 个不同类别任务。
- 建立统一 run schema：task、candidate、score、cost、logs、seed、parent。

验收：
- 每个任务可以从初始 artifact 到 evaluator 得到可复现 score。
- best-of-N 和 single-chain greedy 两个简单 baseline 可运行。

### Phase 1：统一候选解档案与评估服务

交付：
- `ArtifactStore`：patch/branch lineage、metadata、score history。
- `EvaluationService`：快速失败分类、缓存、timeout、随机种子、资源记录。
- score normalization：支持 maximize/minimize、hard feasibility、multi-objective。

验收：
- 任意候选解能追溯父代、operator、diff、执行日志和 evaluator 版本。
- 重复候选与重复评估能被缓存/去重。

### Phase 2：第一版搜索内核

交付：
- AIDE-style tree search：expand/refine/debug/reuse。
- MAP-Elites/island archive：按 score、novelty、operator lineage 保留多样性。
- Hybrid policy：主链深搜 + 少量 restart/island exploration。
- 基础 operator set：local edit、debug fix、hyperparam tweak、feature/model swap、merge top candidates。

验收：
- 在 MLE/ALE selected tasks 上超过 best-of-N baseline。
- 产出 ablation：greedy vs MCTS vs evolution vs hybrid。

### Phase 3：记忆、技能与检索

交付：
- Task notebook：记录当前任务有效/无效假设、数据观察、失败模式。
- Episodic memory：从 trajectory 中抽取可检索经验。
- Verified skill library：skill 必须附带适用条件、测试、失败案例、版本。
- RAG researcher：按任务检索论文、Kaggle notebook、官方 docs、历史高分轨迹。

验收：
- no-memory vs reflection-memory vs verified-memory 有对照实验。
- skill 写入必须通过 replay 或 held-out improvement gate。

### Phase 4：成本感知多智能体与 harness observability

交付：
- Strategist / Implementer / Debugger / Evaluator-Critic / Researcher / Safety-Auditor 角色。
- Model router：小模型处理局部 debug/format，大模型处理战略重构/跨候选合并。
- Budget allocator：按任务阶段分配 eval calls、tokens、GPU time。
- Proxy-to-full cascade：lint -> smoke -> proxy -> full -> final submit/eval。
- Trace recorder：记录完整 action/result/feedback/cost/score 轨迹。
- Process evaluator：标注探索、实现、验证、总结阶段，识别 lucky pass 和无效循环。
- Effective Feedback Compute：估计哪些反馈被后续决策真正使用。

验收：
- 成本相同条件下，hybrid multi-agent 高于单 agent。
- 能报告每类 agent、operator、模型调用对 score improvement 的贡献。
- 能报告 EFC、process quality、重复工具调用率、验证覆盖率。

### Phase 5：harness registry 与受控 harness evolution

交付：
- Harness registry：保存不同 ACI、工具、上下文、记忆、验证门和角色分工配置。
- Config-level mutation：只允许修改 `HarnessSpec`，不改 runtime 源码。
- Harness ablation：同一模型、同一任务、同一预算下比较多个 harness。
- Promotion gate：新 harness 必须通过 selected tasks + regression suite + 成本上限。
- Source-level mutation prototype：只在独立分支和隔离 worker 中实验，不进入主线。

验收：
- 至少得到 2-3 个 benchmark-family 专用 harness：MLE、ALE、Frontier-Eng。
- 新 harness 晋级时必须附带：提升任务、退化任务、成本变化、轨迹质量变化。
- 源码级 harness mutation 必须支持 replay、diff audit、health probe、rollback。

### Phase 6：benchmark campaign

优先顺序：

1. **MLE-bench lite / selected**：检验 ML pipeline 搜索、proxy eval、RAG、merge。
2. **ALE-Bench selected**：检验长程算法工程、局部搜索接口、编译执行稳定性。
3. **Frontier-Eng selected**：检验工程仿真、硬可行性、连续 score、depth search。
4. **RE-Bench**：检验研究工程能力和长时任务鲁棒性。

每个 benchmark campaign 输出：
- baseline 表：best-of-N、greedy、AIDE-style、OpenEvolve-style、hybrid。
- cost-normalized score 曲线。
- improvement frequency / magnitude 曲线。
- top candidates lineage 分析。
- 失败模式报告。

## 5. 初始实验矩阵

| 实验 | 对照 | 目的 |
|------|------|------|
| Search policy | greedy / MCTS / island / hybrid | 找出不同 benchmark 的最优搜索形态 |
| Depth-width | 1 deep chain / k parallel chains / hybrid | 验证 Frontier-Eng 的 depth > width 是否跨任务成立 |
| Operator set | debug-only / local edit / strategic rewrite / merge | 识别真正贡献提升的操作符 |
| Memory | none / raw reflection / verified memory | 防止反思污染与负迁移 |
| Proxy eval | no proxy / early metric / learned proxy / fidelity-aware | 降低 MLE 和仿真任务完整评估成本 |
| Model routing | single frontier / small+frontier routed / bandit ensemble | 控制成本并保持高质量突变 |
| RAG | none / docs only / papers+notebooks+history | 检查外部知识是否提高 ideation diversity |
| Harness / ACI | shell-only / SWE-agent-style ACI / benchmark-specific tools | 衡量工具接口对搜索效率和错误率的影响 |
| Context policy | full history / summarized history / retrieved state / task notebook | 控制上下文污染和长程漂移 |
| Feedback policy | raw logs / summarized feedback / structured verifier feedback / EFC-gated | 提升有效反馈密度 |
| Process scoring | outcome-only / outcome+trajectory / AgentLens-style quality | 避免把 chaotic lucky pass 当作高质量策略 |
| Harness evolution scope | fixed / config mutation / prompt-skill mutation / source mutation | 判断 harness 自进化的真实收益和风险 |
| Meta-scaffold | single harness / parallel heterogeneous harnesses / blackboard | 检查异构 harness 组合是否提升覆盖率 |

## 6. 实现细节决策

1. **所有候选必须是可执行 artifact。** 不接受只存在于自然语言里的“方案”进入 archive。
2. **每次写入长期 memory/skill 都要过验证门。** 至少要求 replay 成功，最好要求 held-out 或 sibling task 提升。
3. **候选评分使用 score vector。** 包括 objective、feasibility、runtime、cost、novelty、risk，不用单一 scalar 过早压缩。
4. **默认不让 agent 修改核心 harness 源码。** 允许受 schema 约束的 `HarnessSpec` 配置变体；源码级 harness mutation 作为单独实验，并经过审计、回放和回滚。
5. **严格区分 train/proxy/final eval。** MLE-bench 尤其要避免 leaderboard overfitting 和数据泄漏。
6. **保留失败样本。** 失败轨迹是调试器、反思器和 skill optimizer 的主要训练信号。
7. **harness 评估必须固定模型和任务。** 比较 harness 时先固定 base model、任务集、预算和 evaluator，否则无法区分模型能力与系统设计收益。
8. **结果分数和过程分数都要记录。** outcome-only 会高估 lucky pass，过程质量用于过滤不稳定策略。
9. **harness 变体必须有回归套件。** 新 harness 只在少数任务提升但破坏通用能力时不能晋级。

## 7. 风险与缓解

| 风险 | 表现 | 缓解 |
|------|------|------|
| 评估过慢 | MLE/full simulation feedback 周期太长 | proxy eval、early stop、缓存、并行队列 |
| 反思污染 | 错误经验进入长期记忆，造成负迁移 | verified memory gate、过期策略、失败回放 |
| 早熟收敛 | 多轮只做小修小补，score plateau | novelty gate、island restart、merge/crossover、RAG idea injection |
| 不可复现 | 高分候选无法重跑 | 固定 seed、环境快照、artifact lineage、日志强制保存 |
| benchmark leakage | 利用测试集/leaderboard 细节刷分 | adapter 层隔离 final eval，记录提交次数，使用 holdout/proxy |
| 自修改失控 | agent 改 evaluator/harness 或伪造日志 | evaluator read-only、沙盒、diff audit、独立复跑 |
| 多智能体资产低质 | 大量 skill/asset 无复用价值 | 采用率和独立验证作为保留标准 |
| harness overfit | 某个任务族提升，但跨任务退化 | harness registry、回归套件、held-out task family |
| lucky pass | 结果通过但过程混乱，不可稳定复现 | process evaluator、轨迹 PTA/阶段标注、复跑验证 |
| feedback waste | 大量工具调用没有被后续决策使用 | EFC 指标、反馈摘要质量门、重复调用惩罚 |
| harness 指标误读 | 同一行为特征在不同框架里含义相反 | 固定框架内分析，跨 harness 只比较端到端和回归 |

## 8. 两周 MVP 建议

第 1-2 天：
- 确认 benchmark 环境可用性，选定 MLE 3 个、ALE 2 个、Frontier-Eng 1-3 个 smoke tasks。
- 定义 `Task`、`Candidate`、`ScoreVector` schema。

第 3-5 天：
- 实现 artifact store + evaluator wrapper + best-of-N / greedy baseline。
- 每个 selected task 产出第一条可复现 score 曲线。

第 6-9 天：
- 实现 tree search + operator library v0。
- 加入 debug operator、local edit operator、hyperparam operator、restart。

第 10-12 天：
- 加入 island archive、novelty feature、proxy/full eval cascade。
- 跑第一组 ablation：greedy vs tree vs island vs hybrid。
- 加入 trace recorder v0，开始记录 action/result/feedback/cost。

第 13-14 天：
- 写第一版 benchmark report。
- 根据结果决定下一步优先优化 MLE proxy、ALE algorithm operator，还是 Frontier-Eng depth search。
- 追加 harness report：工具调用效率、验证覆盖、重复调用、EFC 粗估。

## 9. 下一步具体 TODO

- [x] 拉取 MLE-bench、ALE-Bench、Frontier-Eng 官方/指定仓库。
- [x] 验证 ALE-Bench 真实本地运行方式：`ahc039` public/private eval。
- [x] 验证 Frontier-Eng 真实本地运行方式：official smoke + `WirelessChannelSimulation/HighReliableSimulation` baseline。
- [ ] 验证 MLE-bench 真实本地运行方式：当前被 Kaggle credentials 阻塞。
- [x] 建立统一实验目录和 metadata schema。
- [x] 实现最小 `BenchmarkAdapter` 接口。
- [x] 实现通用 `LocalCommandBenchmarkAdapter`：候选文件 + 静态评测文件 + `eval_command` + `score.json`。
- [x] 实现 `ArtifactStore` 和 evaluator cache。
- [x] 跑 best-of-N / greedy baseline。
- [x] 实现 AIDE-style tree search 的最小 greedy/archive 搜索内核。
- [x] 实现 island archive + novelty gate 的第一版 archive 机制。
- [x] 接入本地 Azure managed-identity GPT-5.5 Responses 调用 smoke。
- [x] 建立 MLE/ALE/Frontier 三类 proxy benchmark smoke tasks。
- [ ] 加入 proxy/full evaluation cascade。
- [ ] 建立 verified skill/memory 写入门槛。
- [ ] 输出第一份 cost-normalized benchmark report。
- [x] 定义 `HarnessSpec` schema 和 harness registry。
- [x] 实现 trace recorder：action/tool/result/score/cost 的 JSONL 轨迹。
- [x] 实现 EFC 粗估：有效、无效、重复、未保留反馈分类。
- [x] 增加 process evaluator：探索/实现/验证/总结阶段粗标注。
- [x] 做固定模型下的 harness ablation runner。
- [x] 建立 harness promotion gate：selected tasks + regression + cost cap 的基础接口。

## 10. Harness 与 self-evolving 近期文献结论

| 文献 | 关键观点 | 对计划的改动 |
|------|----------|--------------|
| **Code as Agent Harness** (2605.18747) | 代码不仅是输出，也是 agent 的推理、行动、环境建模和验证底座 | 新增 `harness/` 模块和 `HarnessSpec`，把 harness 从实现细节提升为优化对象 |
| **From Model Scaling to System Scaling: Scaling the Harness** (2605.26112) | agent 能力来自 model、memory、context、routing、orchestration、verification 的系统组合 | 指标加入 context efficiency、memory hygiene、verification cost、safe evolution |
| **Scaling Laws for Agent Harnesses via Effective Feedback Compute** (2605.29682) | raw tokens/tool calls 不是关键，关键是有效、非冗余、被保留并用于后续决策的反馈 | 新增 EFC 指标和 feedback policy ablation |
| **SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering** (2405.15793) | 专门设计的 ACI 显著影响 agent 行为和性能 | 对 MLE/ALE/Frontier-Eng 设计 benchmark-specific ACI，而不是只暴露 bash |
| **OpenHands Software Agent SDK** (2511.03690) | 生产 agent 需要可组合接口、沙盒执行、生命周期控制、多模型路由和安全分析 | `HarnessRegistry` 与 `HarnessGovernance` 需支持生命周期、沙盒和模型路由 |
| **Same Signal, Different Semantics** (2605.18332) | 43 个 SWE agent framework 中，同一行为信号在不同 harness 下可能正负相反 | process metrics 不跨框架粗暴套用；harness 比较必须固定模型和任务 |
| **AgentLens: Lucky Pass** (2605.12925) | outcome-only 会把混乱试错和稳健解法等同，约 10.7% passing trajectories 是 lucky pass | benchmark report 增加过程质量分和复跑稳定性 |
| **PTCG-Bench** (2605.29653) | self-evolution 表现对 harness 设计敏感，必须做 modular harness ablation | Phase 5 增加 harness ablation 和 harness registry |
| **Sibyl-AutoResearch** (2605.22343) | 自主研究需要 trial-and-error harness，把 trial 信号转成后续行为和 harness repair | memory 写入从“总结文本”升级为 trial-to-behavior / trial-to-harness conversion |
| **OpenComputer** (2605.19769) | 可靠评估需要结构化 state verifier、partial-credit rewards 和可审计轨迹 | evaluator 层优先结构化 verifier，减少 LLM-as-judge 依赖 |
| **Governed Evolution of Agent Runtimes** (2605.27328) | HarnessMutation 应该受验证、追踪、评估和回滚约束 | 源码级 harness evolution 必须走 governance gate |
| **MOSS** (2605.22794) | 文本层进化无法触达 routing、hook ordering、state invariants；源码重写需 evidence batch、ephemeral trial workers、rollback | Level 4 只在 evidence batch + replay worker + health probe 成熟后启动 |
| **Live-SWE-agent** (2511.13646) | agent 可在运行中从基础 scaffold 演化自身 scaffold，但风险和泛化需独立验证 | 可作为后期强 baseline；早期先复现其“运行时 scaffold evolution”思想的受控版本 |
| **A Self-Improving Coding Agent** (2504.15228) | agent system 可通过自编辑从 17% 提升到 53%，说明 harness 源码是高杠杆变量 | 源码 mutation 是高收益方向，但必须后置 |
| **Huxley-Gödel Machine** (2510.21614) | agent 当前性能不等于其后代改进潜力，需衡量 metaproductivity | harness archive 不只按当前分数排序，也记录后代平均提升潜力 |
| **CSI meta-scaffold** (2605.28334) | 单一 scaffold 不支配所有任务；异构 scaffold + blackboard 提升覆盖率 | Phase 5 加入 parallel heterogeneous harnesses / blackboard 实验 |

## 11. Harness-first 执行方案

### 11.1 Harness 分层

```text
Layer A: Tool/ACI
  bash, file edit, notebook, profiler, evaluator, simulator, benchmark-specific commands

Layer B: Context
  full history, summarized history, retrieved task state, candidate lineage, failure registry

Layer C: Feedback
  raw logs, structured verifier output, proxy score, full score, critic summary, EFC label

Layer D: Control
  role routing, model routing, search policy, budget policy, stop/restart/merge policy

Layer E: Governance
  permission, audit, replay, promotion gate, rollback, read-only evaluator boundary
```

### 11.2 Harness 变体从配置开始

第一轮只允许修改 `HarnessSpec`：

```text
safe mutations:
  - add/remove tool from allowlist
  - change context window construction
  - change feedback summarizer
  - change verification cascade threshold
  - change model/operator routing weights
  - add role handoff rule

unsafe mutations:
  - edit evaluator
  - bypass sandbox
  - suppress failing logs
  - mutate benchmark adapter final scoring
  - alter artifact lineage or score records
```

### 11.3 Harness 晋级门槛

一个新 harness 只有同时满足以下条件才进入 registry 的 `promoted` 状态：

1. selected tasks 上 best feasible score 或 cost-normalized score 提升。
2. regression suite 上没有超过阈值的退化。
3. EFC 提升或总成本下降，不能只靠更多 token/tool calls。
4. process quality 不下降，lucky pass 比例不升高。
5. 至少一次独立 replay 复现主要提升。
6. 完整保存 diff、配置、轨迹、score、成本、失败和回滚记录。

### 11.4 Benchmark-specific harness 初版

| 任务族 | Harness 重点 | 必备工具 |
|--------|--------------|----------|
| MLE-bench | notebook/pipeline 管理、数据检查、CV/proxy/full 分层评估、实验表 | Python runner、GPU monitor、CV scorer、submission builder、Kaggle/RAG reader |
| ALE-Bench | 快速编译运行、多 seed score、局部搜索可视化、算法 profiling | C++/Python runner、seed batch evaluator、profiler、visualizer |
| Frontier-Eng | 仿真器调用、硬约束解释、参数/代码混合搜索、失败分类 | simulator wrapper、constraint checker、proxy scorer、artifact differ |
| RE-Bench | 研究轨迹、假设管理、实验复现、claim scoping | experiment runner、paper/repo RAG、evidence tracker、report compiler |

### 11.5 Source-level harness evolution 触发条件

只有当连续多次出现配置层无法解决的结构性失败时，才启动源码级 mutation：

- routing/hook ordering 错误导致反馈丢失。
- state invariant 无法通过配置表达。
- replay / sandbox / trace recorder 发现系统性 runtime 缺陷。
- 多个任务族共享同一 harness failure class。

源码级 mutation 的流程：

```text
evidence batch -> propose patch -> isolated trial image -> replay selected tasks
-> regression suite -> audit diff -> promote with health probe -> rollback on failure
```

## 12. 当前 framework 落地状态

已完成第一版可运行骨架：

| 模块 | 状态 | 说明 |
|------|------|------|
| Python package | ✅ | `src/open_evolve`，零外部依赖，Python 3.8 可运行 |
| Core schema | ✅ | `Task`、`Candidate`、`CandidateDraft`、`ScoreVector`、`EvaluationResult`、`RunSummary` |
| Artifact store | ✅ | 文件型 run/candidate/evaluation/summary 落盘 |
| Evaluation service | ✅ | adapter 调用、缓存、trace hook、异常封装 |
| Search loop | ✅ | greedy depth-biased controller + archive-driven diverse parent controller |
| Operators | ✅ | JSON 数值 step/random、文件字符串替换、文件追加 |
| Archive | ✅ | 内存级 candidate archive，支持 artifact 去重、cell best、diverse parents |
| Harness | ✅ | `HarnessSpec`、registry、safe config mutation、promotion governance |
| Trace / EFC | ✅ | JSONL trace recorder、EFC 粗估、process quality 粗评、stage 粗标注 |
| Memory | ✅ | verified memory store，支持按 task family 查询 |
| Local command adapter | ✅ | 写候选文件、跑本地 evaluator command、读 `score.json` |
| Model clients | ✅ | `AzureOpenAIResponsesClient` 支持本地 managed-identity bearer token 调 GPT-5.5 Responses API |
| CLI | ✅ | `run-toy`、`eval-local`、`test-azure`、`eval-frontier`、`run-frontier`、`eval-ale`、`run-ale` |
| Harness ablation | ✅ | `HarnessAblationRunner` 支持固定回调下比较多个 `HarnessSpec`，并可输出 JSON/Markdown |
| Examples | ✅ | toy numeric、`examples/local_command`、`examples/benchmark_smoke` |
| Tests | ✅ | `unittest` 覆盖 core/harness/local-command/search/memory/operator/LLM parse |

当前验证命令：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m open_evolve.cli run-toy --workspace /tmp/open_evolve_smoke --iterations 4 --max-evaluations 40
PYTHONPATH=src python3 -m open_evolve.cli eval-local --task-config examples/local_command/task.json --candidate-json examples/local_command/candidate.json
PYTHONPATH=src python3 examples/local_command/run_search.py
PYTHONPATH=src python3 -m open_evolve.cli test-azure --prompt 'Return exactly: OPEN_EVOLVE_OK'
PYTHONPATH=src python3 examples/benchmark_smoke/run_three_benchmarks.py --workspace .open_evolve/benchmark_smoke
PYTHONPATH=src python3 -m open_evolve.cli eval-frontier --benchmark WirelessChannelSimulation/HighReliableSimulation
PYTHONPATH=src python3 -m open_evolve.cli run-frontier --benchmark WirelessChannelSimulation/HighReliableSimulation --workspace .open_evolve/frontier_smoke --iterations 3 --max-evaluations 4 --llm-timeout-seconds 120 --llm-retries 1
PYTHONPATH=src python3 -m open_evolve.cli run-ale --problem ahc039 --lite --operator numeric --iterations 3 --max-evaluations 7 --samples 2
PYTHONPATH=src python3 -m open_evolve.cli eval-ale --problem ahc039 --lite --split private
```

本地 Azure 免 key GPT-5.5 调用方式已实测通过：

```text
provider: azure_uami
wire_api: responses
model: gpt-5.5
endpoint shape: /openai/v1/responses?api-version=preview
auth: managed-identity bearer token from environment, no API key
```

三类 benchmark smoke 已通过同一个 `LocalCommandBenchmarkAdapter`：

| Smoke task | Candidate source | Feasible | Objective |
|------------|------------------|----------|-----------|
| MLE proxy | Azure GPT-5.5 | ✅ | 98.0 |
| ALE proxy | Azure GPT-5.5 | ✅ | 111.5 |
| Frontier proxy | Azure GPT-5.5 | ✅ | 99.0 |

真实 benchmark repo 已开始接入，详见 `benchmark_runs.md`：

| Benchmark | 本地路径 | 当前状态 |
|-----------|----------|----------|
| MLE-bench | `/data/zyf/benchmarks/mle-bench` | repo 和 Python env 已安装；`mlebench prepare -c detecting-insults-in-social-commentary` 被 Kaggle credentials 阻塞 |
| ALE-Bench | `/data/zyf/benchmarks/ALE-Bench` | `ALEBenchAdapter` 已接入；`ahc039` public-search 3 轮/7 eval 正常，private final 150/150 `ACCEPTED` |
| Frontier-Eng | `/data/zyf/benchmarks/Frontier-Engineering` | `FrontierEngineeringAdapter` 已接入；`WirelessChannelSimulation/HighReliableSimulation` GPT-5.5 3 轮/4 eval 正常，best `combined_score≈197.71` |

proxy task 仍保留为 CI smoke；真实证据以后以官方 runner wrapper 为准。

下一批实现建议：

1. **Campaign runner**：批量加载真实 task configs，执行 search/harness ablation 并产出统一 report。
2. **MLEBenchAdapter**：等 Kaggle credentials 配好后，先接 `detecting-insults-in-social-commentary` 或另一个低复杂度小数据任务。
3. **ALE LLM repair loop**：当前 GPT-5.5 对极简 baseline 容易返回重复候选；需要 prompt/schema 记录 raw response，并引入 problem-specific generator。
4. **Frontier full campaign**：在 `WirelessChannelSimulation/HighReliableSimulation` 上扩大到 20-50 eval，并加入 archive search 和 replay。
5. **Proxy/full cascade**：每个 task config 增加 `smoke -> proxy -> full` 分层评估，记录 fidelity。
6. **Process evaluator v2**：用 task-level successful traces 构建更接近 AgentLens 的过程参考。
