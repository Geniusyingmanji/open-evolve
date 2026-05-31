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
