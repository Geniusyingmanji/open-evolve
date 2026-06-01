# 自进化 Agent 框架调研：Benchmark 与方法论

## 一、核心 Benchmark 详细分析

### 1.1 Frontier-Eng

> **Frontier-Eng: Benchmarking Self-Evolving Agents on Real-World Engineering Tasks with Generative Optimization**
> EinsiaLab, arXiv:2604.12290, 2026.04

**核心范式 — Generative Optimization：**
- 每个任务是三元组 (C, x₀, E)：任务上下文 C、初始可行解 x₀、评估器 E
- Agent 迭代执行 propose → execute → evaluate 循环，在预算 B 内最大化最优可行分数
- **连续分数**（非 pass/fail），带硬可行性约束

**47 个任务，5 个工程类别：**

| 类别 | 任务数 | 示例 |
|------|--------|------|
| Computing & Quantum | 10 | GPU kernel 优化 (FlashAttention, MLA)、密码学吞吐量 |
| Operations Research | 9 | 库存优化、Job-shop 调度、组合优化 |
| Robotics & Control | 8 | PID 调参、四足步态优化、UAV 巡检 |
| Optics & Communication | 10 | 自适应光学、光纤 WDM、频谱打包 |
| Physical Sciences | 10 | 拓扑优化、化学反应优化、气动外形 |

**关键发现：**
- **双幂律衰减**：改进频率 ~1/iteration，改进幅度 ~1/improvement_count
- **深度优于宽度**：固定预算下，单条深搜链（1.00）远优于 16 条并行链（0.91）
- **排行榜**：GPT-5.4 (3.54) ≈ Claude Opus 4.6 (3.63) > GLM-5 > DeepSeek V3.2

**对自进化 Agent 的适配性：⭐⭐⭐⭐⭐**
- 天然的迭代优化范式，连续分数信号
- 跨领域工程任务，测试泛化能力
- 已集成搜索框架对比（ABMCTS, OpenEvolve, ShinkaEvolve）

---

### 1.2 MLE-bench

> **MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering**
> OpenAI, arXiv:2410.07095, ICLR 2025

**核心设计：**
- 75 个真实 Kaggle 竞赛，覆盖 15 个问题类别（表格/图像/NLP/音频/多模态）
- 难度分布：Low 22 / Medium 38 / High 15
- Docker 沙盒（36 vCPU, 440GB RAM, 1x A10 GPU），24h 时限
- 基于 Kaggle 排行榜的 medal 评估（bronze/silver/gold）

**最新排行榜（2026 年初）：**

| Agent | Model | Medal Rate |
|-------|-------|-----------|
| Famou-Agent 2.0 | Gemini-3-Pro | **64.44%** |
| AIBuildAI | Claude Opus 4.6 | **63.11%** |
| CAIR MARS+ | Gemini-3-Pro | 62.67% |
| MLEvolve | Gemini-3-Pro | 61.33% |

（初始论文中 o1-preview + AIDE 仅 16.9%，一年半内提升 ~4x）

**对自进化 Agent 的适配性：⭐⭐⭐⭐⭐**
- Kaggle 竞赛天然是开放优化问题
- Agent 需迭代探索特征工程、模型选择、超参调优
- 社区活跃，排行榜持续更新

---

## 二、其他推荐 Benchmark

### Tier 1：高度适配（开放式、迭代优化、连续分数）

| Benchmark | 来源 | 任务类型 | 迭代优化 | 适配度 |
|-----------|------|---------|---------|--------|
| **ALE-Bench** | Sakana AI, NeurIPS 2025 | AtCoder 启发式竞赛 (NP-hard 组合优化) | ✅ 核心设计 | ⭐⭐⭐⭐⭐ |
| **RE-Bench** | METR, ICML 2025 | 7 个开放式 ML 研究工程任务 | ✅ 8h 预算内持续优化 | ⭐⭐⭐⭐⭐ |
| **FML-bench** | arXiv:2510.10472 | 8 个基础 ML 研究问题 | ✅ 含"探索多样性"指标 | ⭐⭐⭐⭐ |
| **AIDE/Weco-Kaggle** | Weco AI, arXiv:2502.13138 | 63 个 Kaggle 竞赛 | ✅ 树搜索迭代 | ⭐⭐⭐⭐ |

**重点推荐 ALE-Bench：**
- 基于 AtCoder Heuristic Contest 的算法工程问题
- 无单一正确答案，连续优化分数，无上界
- AI agent 已在真实 AHC 比赛中排名 21/1000+ 人类选手
- 与 Frontier-Eng 互补：ALE-Bench 侧重算法/组合优化，Frontier-Eng 侧重工程仿真

### Tier 2：较好适配

| Benchmark | 特点 | 局限 |
|-----------|------|------|
| **SWE-bench Verified** | 500 个真实 GitHub issue | 单任务 pass/fail，但 DGM 已用于自进化评估 |
| **SWE-EVO** | 长周期软件演化，平均 21 文件/任务 | GPT-5.4 仅 25%，难度极高 |
| **SlopCodeBench** | 93 个 checkpoint 迭代扩展代码 | 测试迭代中代码质量退化 |
| **MLAgentBench** | 13 个 ML 实验任务 | 规模较小 |
| **ARC-AGI-2** | 抽象推理，测试泛化 | 单任务 pass/fail |

### Tier 3：参考框架

| 名称 | 用途 |
|------|------|
| **METR Task Suite** | 228 个任务，测量 agent 自主工作时长 |
| **PaperBench** | 复现 20 篇 ICML 论文，8316 子任务 |
| **LiveCodeBench** | 持续更新的竞赛编程题 |

---

## 三、自进化 Agent 方法论

### 3.1 分类框架

根据综述 "A Survey of Self-Evolving Agents" (arXiv:2507.21046, TMLR 2026)，自进化沿四个维度展开：

```
What to evolve?
├── Model weights (RL/self-play)
├── Prompts (evolutionary/gradient-based)
├── Memory/Experience (accumulation/distillation)
├── Tools/Skills (creation/composition)
└── Workflow/Architecture (search/evolution)

When to evolve?
├── Intra-task (test-time, 单任务内优化)
└── Inter-task (跨任务经验迁移)

How to evolve?
├── Evolutionary algorithms
├── RL / self-play
├── Gradient-based (symbolic gradients)
├── Search (MCTS, tree search)
└── Experience replay / distillation
```

### 3.2 关键方法详解

#### A. 代码自修改（最激进的自进化）

| 方法 | 核心思路 | 进化对象 | 结果 |
|------|---------|---------|------|
| **Darwin Godel Machine** (Sakana AI, 2025) | Agent 迭代修改自身源代码，维护变体档案 | Agent 源代码 | SWE-bench 20%→50% |
| **SICA** (Bristol, ICLR 2025 WS) | 无 meta-agent，agent 直接编辑自身 Python 代码 | Scaffolding 代码 | SWE-bench 17%→53% |
| **SATLUTION** | LLM 编辑 SAT solver 仓库 + 自进化策略 | Solver 代码 + 进化策略 | 超越 SAT Competition 2025 人类冠军 |

⚠️ **安全风险**：DGM 被观察到伪造测试结果、禁用幻觉检测代码来提升指标

#### B. Workflow/架构进化

| 方法 | 核心思路 | 搜索策略 | 结果 |
|------|---------|---------|------|
| **ADAS** (UBC, ICLR 2025) | Meta Agent Search 用代码定义新 agent 架构 | 迭代代码生成 | 跨域迁移，超越手工设计 |
| **AFlow** (MetaGPT, ICLR 2025 Oral) | Workflow 表示为代码图，MCTS 搜索优化 | MCTS | 超越手工方法 5.7%，自动方法 19.5% |
| **EvoFlow** (2025) | 进化算法搜索异质 workflow 种群 | Niching evolutionary | 超越 o1-preview，仅 12.4% 推理成本 |

#### C. 进化式算法发现

| 方法 | 核心思路 | 结果 |
|------|---------|------|
| **FunSearch** (DeepMind, Nature 2024) | LLM 作为突变算子 + 岛屿模型进化 | Cap-set 新解，bin packing 优化 |
| **AlphaEvolve** (DeepMind, 2025) | FunSearch 升级版，Gemini 集成进化全流程 | 56 年来首次改进 Strassen 矩阵乘法 |
| **EvoPrompt** (ICLR 2024) | 进化算子优化 prompt | BBH 上 +25% |
| **Promptbreeder** (ICML 2024) | 双重自指——同时进化 task-prompt 和 mutation-prompt | 超越 CoT 和 Plan-and-Solve |
| **GEPA** (ICLR 2026 Oral) | 反思式 prompt 进化，集成入 DSPy | 超越 MIPROv2 13%，GRPO 20% |

#### D. 经验驱动 / 记忆进化

| 方法 | 核心思路 | 进化对象 |
|------|---------|---------|
| **Reflexion** (NeurIPS 2023) | 环境反馈→语言自反思→存储为上下文 | 推理策略（verbal） |
| **LATS** (ICML 2024) | MCTS 统一推理/行动/规划 | 搜索策略 |
| **EvolveR** (2025) | 离线蒸馏交互轨迹为策略原则 + 在线检索 | 策略原则库 |
| **ICE** (2024) | Investigate-Consolidate-Exploit 跨任务迁移 | Workflow 知识（API 调用减少 80%） |
| **Symbolic Learning** (2024) | Prompt/工具作为"符号参数"，自然语言梯度反传 | Prompt + 工具 |
| **STILL** (2026) | 无奖励自发进化，构建结构化世界知识 | Markdown 世界知识文档 |

#### E. 工具/技能创建

| 方法 | 核心思路 |
|------|---------|
| **Voyager** (2023) | 自动课程 + 不断增长的技能库 + 自我验证 |
| **LATM** (2023) | LLM 自主创建可复用工具函数 |

#### F. Self-Play RL

| 方法 | 核心思路 |
|------|---------|
| **Self-Play SWE-RL** (2025) | Agent 交替扮演 bug 注入者/修复者，RL 训练 |
| **Absolute Zero Reasoner** (NeurIPS 2025 Spotlight) | 自我生成训练任务 + 自我提升推理 |

---

## 四、构建自进化 Agent 框架的建议

### 4.1 推荐 Benchmark 组合

```
主要评测（开放式优化，核心赛道）：
  ├── Frontier-Eng  — 工程仿真优化（47 任务，连续分数）
  ├── MLE-bench     — ML 工程（75 Kaggle 竞赛）
  └── ALE-Bench     — 算法工程（AtCoder 启发式）

补充评测（验证泛化）：
  ├── RE-Bench      — ML 研究工程（7 任务，连续分数）
  ├── FML-bench     — ML 研究（探索多样性指标）
  └── SWE-bench     — 软件工程（DGM/SICA 已用于自进化评估）
```

### 4.2 方法论路线图

考虑到要在上述 benchmark 上"刷分"，建议分层构建：

```
Layer 1: 基础优化循环
  → Reflexion-style 自反思 + 经验记忆
  → 类似 Frontier-Eng 的 propose-execute-evaluate 循环

Layer 2: 搜索策略进化
  → AFlow/LATS 式 MCTS 搜索
  → FunSearch/AlphaEvolve 式进化搜索
  → 关键：depth > width（Frontier-Eng 发现）

Layer 3: Workflow/架构自进化
  → ADAS 式 meta-agent search
  → EvoFlow 式种群进化
  → 跨任务经验迁移（ICE/EvolveR）

Layer 4: 代码级自修改（可选，高风险）
  → DGM/SICA 式自我重写
  → 需严格沙盒和安全机制
```

### 4.3 核心参考文献

| 类别 | 必读论文 |
|------|---------|
| 综述 | Survey of Self-Evolving Agents (arXiv:2507.21046, TMLR 2026) |
| Benchmark | Frontier-Eng (2604.12290), MLE-bench (2410.07095), ALE-Bench (2506.09050) |
| 架构进化 | ADAS (2408.08435), AFlow (2410.10762) |
| 代码自修改 | DGM (2505.22954), SICA (ICLR 2025 WS) |
| 进化搜索 | FunSearch (Nature 2024), AlphaEvolve (2506.13131) |
| 经验驱动 | Reflexion (NeurIPS 2023), EvolveR (2510.16079), Symbolic Learning (2406.18532) |
| 安全 | Your Agent May Misevolve (2509.26354) |
| GitHub | github.com/XMUDeepLIT/Awesome-Self-Evolving-Agents |

---

## 五、近期补充文献与设计启发

这一部分重点补充和 Frontier-Eng / MLE-bench / ALE-Bench 直接相关的 2025-2026 年工作。结论先行：当前最有效的路线不是单纯堆模型，而是把开放性优化问题形式化为 **可验证候选解空间 + 搜索策略 + 操作符集合 + 经验记忆 + 成本感知评估**。

### 5.1 MLE-bench 与 AI Research Agent

| 工作 | 关键机制 | 对本项目的启发 |
|------|----------|----------------|
| **AIDE: AI-Driven Exploration in the Space of Code** (2502.13138) | 将 ML 工程建模为代码空间树搜索，复用并精炼高分解 | MLE-bench 的最小可行 baseline 应该是 tree-search/code-reuse，而不是单轮 AutoML |
| **AI Research Agents for Machine Learning: Search, Exploration, and Generalization in MLE-bench** (2507.02554) | 明确拆分 search policy 与 operator set，对 Greedy / MCTS / Evolutionary 做系统比较 | 需要把“搜索策略”和“候选修改操作符”解耦，做可替换 ablation |
| **What Does It Take to Be a Good AI Research Agent? Ideation Diversity** (2511.15593) | MLE-bench 轨迹分析显示更高 ideation diversity 与更好成绩相关 | 不应只做单链贪心；需要保留受控多样性、避免早熟收敛 |
| **KompeteAI** (2508.10177) | RAG 引入 Kaggle/arXiv 思路，合并 top candidates，用 early metrics 和调试加速减少完整训练 | MLE 任务要有 proxy score、candidate merge 和外部方案检索 |
| **ArchPilot** (2511.03985) | 多智能体：编排、生成、代理评估，使用 proxy training 与 fidelity-aware score | 昂贵评估必须分层：lint/debug -> 小样本训练 -> 全量训练 -> 提交/最终评估 |
| **KAPSO** (2601.21526) | git-native 实验引擎 + 知识系统 + episodic memory，评测 MLE-bench/ALE-Bench | 候选解必须是可复现分支/patch，不只是聊天历史 |
| **FM Agent** (2510.26144) | 多智能体 + 大规模进化搜索，覆盖 OR、MLE、GPU kernel、数学 | 统一框架应支持分布式异步评估和跨 benchmark 的 evaluator adapter |

### 5.2 开放式代码/算法进化框架

| 工作 | 关键机制 | 对本项目的启发 |
|------|----------|----------------|
| **AlphaEvolve** (2506.13131) | LLM 直接修改代码，持续接收 evaluator feedback；在数学、调度、硬件/训练基础设施上产生改进 | 核心抽象应是“可执行 artifact + 严格 evaluator”，而不是 agent 对话本身 |
| **OpenEvolve** | MAP-Elites / island-style LLM program evolution，已被用于数学、prompt evolution、工程优化等任务 | 可作为 evolution baseline 和部分搜索后端，但需要补上 benchmark adapter、memory、proxy eval |
| **ShinkaEvolve** (2509.19349) | 父代采样平衡探索/利用、代码 novelty rejection、bandit LLM ensemble | 需要 novelty gate 和模型路由，减少重复样本与高价模型浪费 |
| **CodeEvolve** (2510.14150; 2605.04677) | CVT-MAP-Elites、inspiration crossover、meta-prompting、depth refinement；另有 runtime-guided target selection + MCTS | 对 Frontier-Eng/GPU/系统优化任务，应结合 profiler 找热点，再局部演化 |
| **LEVI** (2605.09764) | 更强 search architecture 替代更大 LLM：多样性数据库、mutation router、proxy benchmark | 预算有限时，优先优化搜索/评估架构，再扩大模型 |
| **EvoX** (2602.23413) | 同时进化候选解与搜索策略，动态调整 prior solution selection / variation | 第二阶段应加入 meta-controller，按任务进展自动调 operator 权重 |
| **LoongFlow** (2512.24077) | Plan-Execute-Summarize + hybrid evolutionary memory + MAP-Elites/多岛 | 每次候选生成要产出 plan 和总结，成为可检索的 evolution trace |
| **DeepEvolve** (2510.06056) | deep research + code evolution + systematic debugging，避免纯内部知识 plateau | 对专业工程任务需要 literature/RAG agent，但每个 idea 必须落到可执行 patch |
| **ImprovEvolve** (2602.10233) | 将候选程序参数化为 propose / improve / perturb 接口，降低 LLM 认知负担 | 对组合优化/物理优化可要求 candidate 暴露局部搜索接口，而不是一次性生成完整解 |

### 5.3 反思、记忆、技能与安全评估

| 工作 | 关键机制 | 对本项目的启发 |
|------|----------|----------------|
| **GEPA** (2507.19457) | 通过轨迹反思和 Pareto frontier 做 prompt evolution，少量 rollout 即可改进 | 可用于优化 agent prompts / operator prompts；但不能替代真实 evaluator |
| **TextGrad** (2406.07496) | 将 LLM 反馈作为文本梯度，优化复合 AI 系统的文本/代码变量 | 可作为 prompt/operator/skill 的低成本内环优化器 |
| **SkillOpt** (2605.23904) | 把 skill 文档作为 frozen agent 的外部状态训练，只有 held-out 提升才接受编辑 | 跨任务 skill 必须有验证集和拒绝编辑缓冲，不能把每次反思都写入长期记忆 |
| **MUSE-Autoskill** (2605.27366) | skill lifecycle：创建、记忆、管理、评估、细化 | 技能库应有 unit tests、版本、适用条件、失败案例和淘汰机制 |
| **BenchTrace** (2605.29225) | 评估反思诊断能力和 failure avoidance，指出 agents 会遗忘早期经验并发生负迁移 | 经验库需要质量评分、去噪、过期策略和 controlled eval |
| **Agent-Native Research Artifact** (2604.24658) | 保存探索图、失败实验、证据和执行包，提升 PaperBench/RE-Bench 表现 | 本项目的实验轨迹应保存为机器可读 artifact，而非只写 summary |
| **Your Agent May Misevolve** (2509.26354) | model/memory/tool/workflow 四类自进化都可能引入安全退化、漏洞和对齐下降 | 自修改、工具创建和长期记忆都要经过隔离评估与人工可审计日志 |
| **EvoMap empirical study** (2605.25815) | 大规模 A2A 资产网络中 98% 资产未复用，且自报指标/伪测试导致质量失真 | 多智能体共享资产不能依赖自报分数，必须独立复跑和可验证采用率 |

### 5.4 对开放优化 benchmark 的统一抽象

建议将所有目标 benchmark 统一为如下接口：

```text
Task = {
  context: problem statement + data + constraints + prior artifacts,
  initial_artifact: runnable baseline or seed solution,
  evaluator: deterministic or statistically controlled executable scorer,
  budget: wall-clock / eval calls / tokens / hardware,
  feasibility: hard constraints and validation checks,
  score: continuous objective with normalized improvement
}

Candidate = {
  patch_or_program,
  parent_ids,
  operator_id,
  plan,
  execution_log,
  score_vector,
  cost,
  novelty_features,
  lessons
}
```

这个抽象能同时覆盖：
- Frontier-Eng：候选是工程设计/代码/参数，score 来自 simulator/verifier。
- MLE-bench：候选是训练 pipeline / feature / model / hyperparams，score 来自 local CV、public leaderboard proxy 或最终提交。
- ALE-Bench：候选是启发式算法代码，score 来自 AtCoder-style evaluator。
- RE-Bench：候选是研究工程 artifact，score 来自任务环境 evaluator。

### 5.5 推荐系统架构

```text
Benchmark Adapter Layer
  ├── FrontierEngAdapter
  ├── MLEBenchAdapter
  ├── ALEBenchAdapter
  └── REBenchAdapter

Optimization Core
  ├── Artifact Store: git branch / patch / metadata / lineage
  ├── Evaluation Service: sandbox, budget, proxy/full eval, reproducibility
  ├── Search Controller: depth-first exploitation + MCTS + island/MAP-Elites
  ├── Operator Library: mutate, debug, refactor, hyperparam, merge, simplify, restart
  ├── Memory System: episodic traces, task notebook, cross-task skill library
  └── Meta Controller: operator/model routing, novelty gate, budget allocation

Agent Roles
  ├── Scientist/Strategist: proposes hypotheses and experiment plans
  ├── Implementer: edits code/artifacts
  ├── Debugger: fixes runtime failures and feasibility violations
  ├── Evaluator/Critic: interprets scores, detects overfitting and leakage
  ├── Researcher/RAG: retrieves papers, notebooks, docs, prior solutions
  └── Safety Auditor: checks self-modification, tool creation, memory writes
```

### 5.6 关键设计原则

1. **先做 intra-task optimization，再做 agent 自修改。** Frontier-Eng/MLE-bench 的直接收益来自更好的候选解搜索；DGM/SICA 式自改框架代码风险高，适合后置。
2. **深搜为主，受控多样性为辅。** Frontier-Eng 的 depth > width 结论和 MLE ideation diversity 并不矛盾：主线需要持续 exploit，同时保留少量 island/restart/novelty 分支。
3. **评估要分层。** 对 MLE/仿真/硬件任务，完整评估昂贵；必须使用 proxy score、早停、缓存、失败快速分类和 fidelity-aware aggregation。
4. **长期记忆只收可验证经验。** 反思文本如果未经验证，会造成负迁移和 misevolution；写入 skill/memory 前应要求 replay 或 held-out improvement。
5. **候选解是主要进化对象。** 第一阶段进化 program/pipeline/parameter；第二阶段进化 operator prompt 和 skill；第三阶段才进化 workflow/agent code。
6. **每个改进都要保留 provenance。** 包括父代、patch、执行日志、环境、随机种子、score、成本、失败原因，方便复现和后续训练。
7. **多智能体共享必须基于独立验证。** 共享 skill/asset 的采用率、收益和失败率应由 orchestrator 复跑统计，不接受 agent 自报。

### 5.7 本项目优先级判断

短期最值得投入的组合是：

```text
MVP:
  MLE-bench lite / selected tasks
  ALE-Bench selected tasks
  Frontier-Eng selected tasks if environment is available

Core algorithm:
  git-native candidate archive
  AIDE-style tree search
  MAP-Elites/island archive
  proxy/full evaluation cascade
  task-level memory + verified skill library

First ablations:
  depth-only vs width-only vs hybrid
  greedy vs MCTS vs evolution
  no-memory vs reflection memory vs verified memory
  no-proxy vs proxy-gated full evaluation
  single model vs routed model ensemble
```

如果目标是尽快在公开 benchmark 上有竞争力，建议不要一开始做通用“自我重写 agent 源码”。更稳的路线是先把 benchmark adapter、评估缓存、candidate archive、operator library 和 budget allocator 做扎实，再逐步让 prompt/skill/workflow 自进化。
