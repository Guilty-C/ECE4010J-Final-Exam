# VE401 / ECE4010J 期末题目求解助手 — 完整计划书

**项目代号**：`ve401-solver`
**仓库**：`git@github.com:Guilty-C/ECE4010J-Final-Exam.git`
**本地工作目录**：`D:\4010Cheating Code\`
**远端训练服务器**：`ssh lrrelevant@10.35.13.38`
**核心模型**：`Qwen/Qwen2.5-3B-Instruct`（远端疑似已部署；本地按需缓存）
**计划日期**：2026-04-28
**编写人**：Claude (代 Zhu YiZhen 起草)

---

## 0. 摘要（Executive Summary）

为上海交大密西根学院 **ECE4010J / VE401《概率方法在工程中的应用》** 课程（讲义第 15–32 章）构建一个 **本地可运行的题目求解助手**。系统接收一道自然语言题面，自动识别其题型，从一个混合题库中检索最契合的解答模板，按 VE401 讲义的符号约定渲染分步骤解答（含讲义页码、评分细则、陷阱提示）。

技术路线：**模板检索为主 + Qwen2.5-3B-Instruct 改写为辅**。先以纯规则 + 检索方式产出 **MVP**（断网可用），再通过 GitHub 同步到远端 GPU 服务器对 Qwen2.5-3B 做 LoRA 微调，把微调后的 adapter 拉回本地用于风格化改写。

数据：本地 145 条 VE401 课程定制题（已抽取自现有 PDF / HTML） + A 档外部开源题库 ~1,200 条（OpenIntro Statistics 4e、OpenStax Introductory Statistics 2e、Hendrycks MATH 概率统计子集）。

---

## 1. 背景与目标

### 1.1 用户情景
- 用户在期末复习 / 考试演练时遇到一道新题。
- 用户想要的不是"答案对不对"，而是 **VE401 风格的、严格遵守讲义符号约定的、含讲义页码引用与评分点的步骤化解答**。
- 现有材料分布在 PDF / TeX / HTML 三种格式，无法直接喂给模型；需要先做结构化抽取。

### 1.2 项目目标（按优先级）
1. **(P0)** 拿一道新题进来 → 自动识别题型（25 张测试卡之一） → 从模板库中召回 top-K 模板 → 按用户数据填充并渲染分步解答。
2. **(P0)** 输出格式严格遵循 VE401 讲义约定与 crash-course § 8b "Exam Answer Template" 五段式结构。
3. **(P1)** 引入 Qwen2.5-3B-Instruct 在 GPU 服务器上做 LoRA 微调，作为模板风格改写器，提升对模糊 / 口语化题面的鲁棒性。
4. **(P1)** 在 16 题样卷黄金集上做端到端回归测试，命中率 ≥ 14/16。
5. **(P2)** 提供 CLI（命令行）与可选的 GUI / Web 接口；断网可用。

### 1.3 非目标（Out of Scope）
- 不替代教师批改，不保证答案 100% 正确。
- 不做闭源教材的题目抓取。
- 不引入与 VE401 讲义符号约定冲突的 "标准" 统计实现（例如 NumPy 的分位数算法、Tukey-hinge 四分位数等）。
- 不在期末前追求大模型从头预训练；只做轻量 LoRA 微调。

---

## 2. 资产盘点

### 2.1 本地权威材料（VE401 课程定制，`source_priority = 1`）

| 路径（相对 `D:\4010Cheating Code\`） | 内容 | 角色 |
|---|---|---|
| `ece401_all_lecture_slides.pdf` | 840 页讲义 | 公式 / 符号 / 约定的最终权威 |
| `crash_course_ch15_32.html` | 25 测试卡 + 30 陷阱 + 12+4 演练 + 决策树 + 答题模板 + 词典 + 速查表 | 题型分类骨架 |
| `final_exam_playbook_ch15_32.pdf` / `.tex` | 51 页期末手册 | 样板答题风格 |
| `testing_playbook_ch19_20_21.pdf` / `.tex` | 假设检验手册 | 答题模板补充 |
| `exercises_ch19_20_21.html` | 12 题（Z/T/χ²/ 符号 / Wilcoxon / 比例） | 高质量结构化题库 |
| `exercises_ch22_23_24.html` | 12 题（F / 双样本 T / 配对 / 相关性 / Fisher z） | 同上 |
| `exercises_ch25.html` | 10 题（GoF / 独立性 / 同质性） | 同上 |
| `exercises_ch26_27_28_29_30.html` | 50 题（SLR / 预测 / MLR / 推断 / 模型选择） | 同上 |
| `ve401_summer21_ex06.pdf` … `ex10.pdf` | 25 道作业题 | 题面 + 数据；解答需另行整理 |
| `ve401_sample_final_2021.pdf` | 16 道样卷题 | 黄金回归集 |
| `ve401_sample_final_2021_sol.pdf` | 上 16 题完整解答 | 评估金答案 |
| `ch22_24_slides.txt` | 抽取的讲义文本 | 辅助检索 |
| `critical_values.html` | 临界值表 | 数值参考 |
| `exam_prep_testing.html` | 假设检验复习页 | 辅助 |

合计：**约 90 道带完整解答的 VE401 风格题** + 25 张测试卡 + 30 陷阱 + 16 题黄金集。

### 2.2 A 档外部开源训练样本（`source_priority = 2/3`）

| 来源 | 题量 | 体积 | 许可证 | 下载 URL |
|---|---|---|---|---|
| OpenIntro Statistics 4e（教材 + Solution Manual） | ~600 | ~50 MB | CC-BY-SA | https://www.openintro.org/book/os/ |
| OpenStax Introductory Statistics 2e（教材 + Answer Key） | ~400 | ~80 MB | CC-BY-4.0 | https://openstax.org/details/books/introductory-statistics-2e |
| Hendrycks MATH（仅 `Counting_and_Probability` + `Prealgebra/Statistics`） | ~200 | ~20 MB | MIT | https://github.com/hendrycks/math |

合计：约 **1,200 条** 带解答英文题，~150 MB。

### 2.3 模型资产

| 资源 | 位置 | 状态 |
|---|---|---|
| DistilGPT-2 | `D:\hf_offline\distilgpt2\` | 已弃用（仅备 fallback） |
| Qwen2.5-3B-Instruct | 远端 `~/models/Qwen2.5-3B-Instruct/`（待确认） / 本地 `D:\hf_offline\Qwen2.5-3B-Instruct\`（待下载） | 阶段 H 探查 |
| LoRA adapter | `ve401_solver/checkpoints/qwen25_3b_lora_v1/`（训练后产出） | 阶段 I 产出 |

### 2.4 基础设施

| 资源 | 信息 |
|---|---|
| 远端服务器 | `lrrelevant@10.35.13.38`（SSH） |
| Git 仓库 | `git@github.com:Guilty-C/ECE4010J-Final-Exam.git` |
| 本地 OS | Windows 11，bash 与 PowerShell 都可用 |
| 远端 OS | 待确认（H1 步骤探查） |

---

## 3. 系统架构

### 3.1 推理时数据流

```
┌────────────────────────────────────────────────────────────┐
│ 用户输入：自然语言题面                                       │
└──────────────┬─────────────────────────────────────────────┘
               │
        ┌──────▼──────┐
        │ 1. 预处理    │  规范化 LaTeX、抽取数字、识别符号 (n, σ, x̄ 等)
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │ 2. 题型分类  │  规则触发器（30 trap） + 关键词决策树（25 卡）
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │ 3. 模板检索  │  在 corpus.jsonl 中按 (tags, slide_refs, 关键词) 召回 top-K
        │              │  按 source_priority 加权
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │ 4. 模板填充  │  把用户数字代入占位符；可选 SymPy / scipy.stats 数值评估
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │ 5. (可选) Qwen │  rag 模式下，LoRA-Qwen 用 retrieved 模板做风格化改写
        │     改写      │  rule 模式下跳过此步
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │ 6. 渲染输出  │  五段式：Setup / Hypotheses / Statistic / Computation / Decision
        │              │  + 讲义页码 + 评分细则 + 陷阱提示
        └─────────────┘
```

### 3.2 训练时双轨架构

```
┌──────────────────────────────────────────────────────────────────┐
│  本地（D:\4010Cheating Code\ve401_solver\）                        │
│  - PDF/HTML/TeX 抽取                                              │
│  - JSONL 合并、去重、加权                                           │
│  - 推理 CLI 给用户用                                                │
└─────────────────┬────────────────────────────────────────────────┘
                  │  git push (代码 + JSONL)
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  GitHub: Guilty-C/ECE4010J-Final-Exam（代码 + 数据 + adapter LFS） │
└─────────────────┬────────────────────────────────────────────────┘
                  │  git clone / pull
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  远程：lrrelevant@10.35.13.38                                       │
│  - tokenize 数据集                                                 │
│  - LoRA 微调 Qwen2.5-3B-Instruct（GPU）                           │
│  - 评估 + 写 eval_report.md                                        │
│  - 推回 adapter (LFS) / scp                                         │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. 文件夹结构

```
D:\4010Cheating Code\                # 现有材料保留不动
├── (现有 PDF / HTML / TeX / .m / .py)
└── ve401_solver/                    # 新建项目根；整体作为 git repo
    ├── .gitignore
    ├── .gitattributes               # LFS 规则
    ├── README.md
    ├── plan.md                      # 本文档
    ├── progress.md                  # 时间线日志
    ├── requirements.txt
    ├── data/
    │   ├── raw/                     # gitignore；本地与远端各自获取
    │   │   ├── openintro/
    │   │   ├── openstax/
    │   │   └── hendrycks_math/
    │   ├── extracted/               # 入库
    │   │   ├── ve401_local.jsonl
    │   │   ├── crash_course.jsonl
    │   │   ├── openintro.jsonl
    │   │   ├── openstax.jsonl
    │   │   └── hendrycks_math.jsonl
    │   ├── corpus.jsonl             # 入库（合并、去重、加权后的最终题库）
    │   └── corpus.index.faiss       # 入库（小，可选）
    ├── extractors/
    │   ├── extract_ve401_html.py    # 4 个练习题库 HTML
    │   ├── extract_ve401_pdf.py     # homework + sample-final
    │   ├── extract_crash_course.py  # 25 卡 + 30 陷阱
    │   ├── extract_openintro.py
    │   ├── extract_openstax.py
    │   ├── extract_hendrycks.py
    │   └── common.py                # 共享 schema / 工具
    ├── classifier/
    │   ├── tag_taxonomy.json        # 标签字典（一致性的单一真源）
    │   ├── triage_rules.py          # 关键词触发器
    │   └── decision_tree.py         # 25 卡决策树
    ├── retriever/
    │   ├── retrieve.py              # tag + 关键词倒排
    │   └── embed.py                 # 可选：嵌入式检索（DistilGPT-2 / bge-small）
    ├── solver/
    │   ├── template_filler.py       # 占位符填充
    │   ├── numerical_eval.py        # SymPy / scipy.stats（可选）
    │   └── render.py                # 五段式格式化
    ├── infer/
    │   ├── load_qwen.py             # transformers + peft 加载
    │   └── rag_pipeline.py          # 检索 + Qwen 改写
    ├── train/
    │   ├── prepare_dataset.py       # JSONL → tokenized arrow
    │   ├── train_lora.py            # PEFT-LoRA 微调
    │   ├── eval_on_samplefinal.py   # 16 题黄金集打分
    │   └── configs/
    │       ├── qwen25_3b_lora.yaml
    │       └── ds_zero2.json        # DeepSpeed（可选）
    ├── ops/
    │   ├── ssh_setup.sh
    │   ├── sync_to_remote.sh
    │   ├── pull_checkpoint.sh
    │   └── check_remote_model.sh
    ├── cli/
    │   └── solve.py                 # 主入口：python -m ve401_solver.cli.solve
    ├── tests/
    │   ├── test_extractors.py
    │   ├── test_triage.py
    │   ├── test_retriever.py
    │   └── test_end_to_end.py       # 16 题样卷回归
    └── checkpoints/                 # gitignore 内大文件，LFS 推 adapter
        └── qwen25_3b_lora_v1/
            ├── adapter_config.json
            └── adapter_model.safetensors  # LFS
```

---

## 5. 数据架构

### 5.1 统一 JSONL Schema

```json
{
  "id": "ve401_local_ch19_q1",
  "source": "ve401_local | crash_course | openintro | openstax | hendrycks_math",
  "source_priority": 1,
  "chapter": "19",
  "topic_tags": ["one-sample-Z", "two-sided", "sigma-known"],
  "slide_refs": [436, 437],
  "difficulty": "easy",
  "language": "en",
  "type": "exercise | card | trap | drill",
  "question": "A bottling line ... σ=2.0 mL ... n=25, x̄=24.3 mL ... at α=0.05 test H₀:μ=25 vs H₁:μ≠25.",
  "given": {"n": 25, "x_bar": 24.3, "sigma": 2.0, "mu_0": 25, "alpha": 0.05},
  "solution_steps": [
    {"step_id": 1, "label": "Setup", "content": "σ known → Z-test [slide 436]"},
    {"step_id": 2, "label": "Hypotheses", "content": "H₀: μ=25 vs H₁: μ≠25 (two-sided)"},
    {"step_id": 3, "label": "Statistic", "content": "Z = (X̄-μ₀)/(σ/√n) ~ N(0,1)"},
    {"step_id": 4, "label": "Computation", "content": "z = -1.75"},
    {"step_id": 5, "label": "Decision", "content": "|z|<1.96 → fail to reject; p≈0.080"}
  ],
  "rubric": [
    {"point": "State σ known ⇒ Z-test", "marks": 1},
    {"point": "Symbolic H₀, H₁", "marks": 1},
    {"point": "Statistic with null distribution", "marks": 2},
    {"point": "Compute z=-1.75 with sign", "marks": 2},
    {"point": "Critical or p-value", "marks": 1},
    {"point": "Decision in problem context", "marks": 2}
  ],
  "traps": [
    "T2: 单侧测试中误用 z_{α/2}",
    "T3: 写成 'accept H₀'"
  ],
  "trail_of_thought": "看到 'known σ' 立即锁 Z；'differs from' 锁两侧 → z_{0.025}=1.96。",
  "final_answer": "Fail to reject H₀ at 5%; two-sided p ≈ 0.080."
}
```

### 5.2 标签字典（`classifier/tag_taxonomy.json` 摘要）

按章节归类（与 crash-course 25 卡对齐）：

```
parameters:
  - one-sample-Z, one-sample-T, one-sample-chi2-variance     (Ch 19)
  - sign-test, wilcoxon-signed-rank                          (Ch 20)
  - one-sample-prop-Z, two-sample-prop-Z                     (Ch 21)
  - F-test-variances                                         (Ch 22)
  - two-sample-Z, pooled-T, welch-T                          (Ch 23)
  - paired-T, wilcoxon-rank-sum, correlation-rho             (Ch 24)
  - chi2-gof, chi2-independence, chi2-homogeneity            (Ch 25)
  - SLR, SLR-CI, SLR-PI, lack-of-fit                         (Ch 26-27)
  - MLR, partial-F, MLR-CI, MLR-PI                           (Ch 28-29)
  - model-selection, PRESS                                   (Ch 30)
  - one-way-ANOVA, bartlett, posthoc-tukey, posthoc-bonferroni (Ch 31-32)

modifiers:
  - one-sided / two-sided / left-tailed / right-tailed
  - sigma-known / sigma-unknown
  - paired / independent
  - small-n (<25) / large-n
  - normal / non-normal / unknown-distribution
  - ci / pi / test / sample-size / power / oc-curve
```

### 5.3 数据加权策略

`prepare_dataset.py` 在采样时：
- `source_priority=1`（VE401 本地）：每条样本重复 3 次
- `source_priority=2`（OpenIntro / OpenStax）：每条 1.5 次
- `source_priority=3`（Hendrycks MATH）：每条 1 次

理由：本地 145 条是与讲义符号约定一致的"金标准"；外部扩量但不让其稀释风格。

---

## 6. 阶段化里程碑

### 阶段 A：本地材料抽取（3–5 h，本地，无需联网）

| 子任务 | 输入 | 输出 | 工时 |
|---|---|---|---|
| A1 | 4 个 `exercises_*.html` | `data/extracted/ve401_local.jsonl`（≈ 84 题） | 1.5 h |
| A2 | `crash_course_ch15_32.html` | `data/extracted/crash_course.jsonl`（25 卡 + 30 陷阱 + 16 题 drill） | 1 h |
| A3 | `ve401_summer21_ex06–10.pdf` + `sample_final_2021.pdf/_sol.pdf` | 加入 `ve401_local.jsonl`（25 + 16 题，部分需手工拼合解答与题面） | 1.5 h |
| A4 | 合并 + 去重 + 写 schema 校验 | `ve401_local.jsonl` 总条数 ≈ **145** | 0.5 h |

**接受标准**：
- JSONL 通过 `jsonschema` 校验
- 抽样 10 条人工核验通过
- 所有 `slide_refs` 字段非空率 ≥ 70%

### 阶段 B：A 档外部数据下载与抽取（3–5 h，本地，需联网）

| 子任务 | 操作 | 工时 |
|---|---|---|
| B1 | `curl` / `wget` 下载 OpenIntro / OpenStax PDF 与 Solution Manual 至 `data/raw/` | 1 h（含网速） |
| B2 | `git clone https://github.com/hendrycks/math` | 0.2 h |
| B3 | `extract_openintro.py`：用 `pdftotext -layout` 抽题号块，正则匹配 "Exercise N." 与 "Solution N." | 1.5 h |
| B4 | `extract_openstax.py`：同上 | 1 h |
| B5 | `extract_hendrycks.py`：仅遍历 `MATH/test/Counting_&_Probability/` 与 `MATH/test/Prealgebra/`（统计相关），把 JSON 转成统一 schema | 0.5 h |
| B6 | 合并 + 去重 → `data/corpus.jsonl`（约 **1,350** 条） | 0.5 h |

**接受标准**：
- corpus 总条数 ≥ 1,200
- 各 source 的 schema 一致性 100%
- 去重后没有 question 字段相同的两条

### 阶段 C：题型分类器（2–3 h，本地）

| 子任务 | 内容 |
|---|---|
| C1 | 写 `tag_taxonomy.json`（约 50 个标签） |
| C2 | 写 `triage_rules.py`：把 crash-course "Triage from question wording" 表（约 30 条 if-else）固化 |
| C3 | 写 `decision_tree.py`：决策树返回 `(card_id, confidence ∈ [0,1])` |
| C4 | 单测：用 16 题样卷题面跑一遍，输出每题命中的 card_id；准确率 ≥ 75% |

### 阶段 D：检索器（1–2 h，本地）

| 子任务 | 内容 |
|---|---|
| D1 | 写 `retrieve.py`：tag 倒排 + BM25-lite 关键词召回；按 `source_priority` 加权排序 |
| D2 | 可选 `embed.py`：用 `sentence-transformers/all-MiniLM-L6-v2`（22 MB）或 DistilGPT-2 mean-pool，cosine 召回 |
| D3 | 单测：每个 card_id 至少能召回到 ≥ 1 条对应 tag 的模板 |

### 阶段 E：模板填充与渲染（2–3 h，本地）

| 子任务 | 内容 |
|---|---|
| E1 | `template_filler.py`：识别 `{n}`, `{x_bar}`, `{sigma}` 等占位符；用正则从用户输入抽数值 |
| E2 | `numerical_eval.py`（可选）：用 `scipy.stats` 算 z, t, χ², F 统计量与 p-value；查表 / 解析临界值 |
| E3 | `render.py`：五段式 Markdown 输出 + 讲义页码 + rubric + traps |
| E4 | 单测：3 道典型题（Z 检验、卡方 GoF、SLR 斜率检验）端到端跑通 |

### 阶段 F：CLI + 端到端测试（2 h，本地）—— **MVP 完结**

| 子任务 | 内容 |
|---|---|
| F1 | 写 `cli/solve.py`：`python -m ve401_solver.cli.solve "题面"` 或 `--file question.txt` |
| F2 | `--mode rule` / `--mode rag` / `--mode llm-only` 开关 |
| F3 | 跑 `tests/test_end_to_end.py`：16 题样卷至少 12 题命中正确题型与解答骨架 |
| F4 | 写 `README.md` 的 Quick Start 段 |

**MVP 验收标准**：
1. 16 题样卷题型识别 ≥ 14/16
2. 每题响应 < 2 秒
3. 完全断网可运行
4. 提交至 GitHub 可被 `git clone` 后 `pip install -r requirements.txt` 跑通

### 阶段 H：基础设施 — Git + SSH + 模型探查（1–2 h）

| 子任务 | 内容 |
|---|---|
| H1 | `git init` + 关联 `git@github.com:Guilty-C/ECE4010J-Final-Exam.git`；首次 `git push` |
| H2 | 配置 `.gitignore` / `.gitattributes`（见 § 7） |
| H3 | 测试 `ssh lrrelevant@10.35.13.38`；记录 `known_hosts`；远端 `git clone` |
| H4 | 远端 `python -m venv .venv && pip install -r requirements.txt`（含 `transformers`, `peft`, `accelerate`, `datasets`, `bitsandbytes`, `trl`, `scipy`, `sympy`） |
| H5 | `ops/check_remote_model.sh`：探查远端是否已有 Qwen2.5-3B-Instruct（候选路径见 § 8.2）；记录 `nvidia-smi` / `df -h` / `free -h` 输出到 `progress.md` |
| H6 | 若远端无该模型：远端执行 `huggingface-cli download Qwen/Qwen2.5-3B-Instruct --local-dir ~/models/Qwen2.5-3B-Instruct`；若远端无外网，回退本地 `D:\hf_offline\` 下载后 `scp` 上传 |

### 阶段 I：训练数据准备 + LoRA 微调（5–8 h，远端为主）

| 子任务 | 内容 |
|---|---|
| I1（本地） | `train/prepare_dataset.py`：JSONL → Qwen chat 模板 + 加权采样 + 90/5/5 划分；push |
| I2（远端） | `git pull`，运行 `prepare_dataset.py` 输出 tokenized 数据集到 `~/ve401-solver/data/tokenized/` |
| I3（远端） | 跑 `train_lora.py`，配置见 § 8.3；2 epoch，bf16 / fp16 视 GPU 而定 |
| I4（远端） | `eval_on_samplefinal.py`：16 题样卷打分；写 `eval_report.md` |
| I5（同步） | adapter（LoRA `safetensors`，~50–200 MB）通过 Git LFS 推回 ；或 `scp` 到本地 `checkpoints/qwen25_3b_lora_v1/` |

**接受标准**（阶段 I）：
- 训练 loss 单调下降，val loss 在 1–2 epoch 内不显著上升（无明显过拟合）
- 16 题样卷题型识别准确率 ≥ rule baseline + 5 pp
- 决策一致率（reject / fail to reject）≥ 80%

### 阶段 J：本地推理打通（2–3 h）

| 子任务 | 内容 |
|---|---|
| J1 | `infer/load_qwen.py`：transformers + peft 加载基座 + adapter；优先 GPU，回退 CPU 4-bit |
| J2 | `infer/rag_pipeline.py`：把检索器召回的模板放进 system prompt，让 Qwen 做风格化改写与缺步骤填补 |
| J3 | CLI `--mode rag` 全链路打通；`tests/test_end_to_end.py` 增加 RAG 模式 |

---

## 7. Git 与同步策略

### 7.1 `.gitignore`

```
data/raw/
*.pdf
*.tex
*.aux
*.log
*.toc
*.out
.venv/
__pycache__/
*.pyc
.DS_Store
checkpoints/*/optimizer.pt
checkpoints/*/scheduler.pt
checkpoints/*/training_args.bin
checkpoints/*/global_step*/
data/tokenized/
.env
```

### 7.2 `.gitattributes`

```
*.bin           filter=lfs diff=lfs merge=lfs -text
*.safetensors   filter=lfs diff=lfs merge=lfs -text
*.gguf          filter=lfs diff=lfs merge=lfs -text
*.faiss         filter=lfs diff=lfs merge=lfs -text
data/corpus.jsonl text
data/extracted/*.jsonl text
```

### 7.3 推 / 拉策略

| 内容 | 入 git | 备注 |
|---|---|---|
| `*.py`, `*.yaml`, `*.json`, `*.md` | ✅ | 主代码 |
| `data/extracted/*.jsonl`, `data/corpus.jsonl` | ✅（普通 git） | < 50 MB |
| `data/raw/` 原 PDF / HTML | ❌ | 各端自行下载 |
| `D:\4010Cheating Code\` 根目录的 PDF / HTML / TeX | ❌ | 留在原地不污染仓库；extractors 通过相对路径访问 |
| `checkpoints/*adapter*.safetensors` | LFS | LoRA 权重 50–200 MB |
| Qwen2.5-3B 基座权重 | ❌ | 6 GB；远端与本地各自维护 |
| `data/corpus.index.faiss` | ✅ 或 LFS（视大小） | |
| `eval_report.md` | ✅ | 训练结果留档 |

---

## 8. 关键配置 / 参数

### 8.1 `requirements.txt`

```
# 数据处理
beautifulsoup4>=4.12
lxml>=5.0
pdfminer.six>=20231228
PyPDF2>=3.0
jsonschema>=4.20

# 数值计算
numpy>=1.26
scipy>=1.12
sympy>=1.12

# 检索
rank-bm25>=0.2.2
faiss-cpu>=1.8       # 可选

# 模型（本地推理）
torch>=2.2
transformers>=4.41
peft>=0.10
accelerate>=0.30
bitsandbytes>=0.43   # 可选；4-bit 量化

# 训练（远端额外）
datasets>=2.18
trl>=0.8
deepspeed>=0.13      # 可选

# CLI / 工具
click>=8.1
rich>=13.7
pytest>=8.0
```

### 8.2 远端 Qwen2.5-3B-Instruct 候选路径（H5 探查脚本检查顺序）

```
1. ~/.cache/huggingface/hub/models--Qwen--Qwen2.5-3B-Instruct
2. ~/models/Qwen2.5-3B-Instruct
3. ~/Qwen2.5-3B-Instruct
4. /data/models/Qwen2.5-3B-Instruct
5. /opt/models/Qwen2.5-3B-Instruct
6. /workspace/models/Qwen2.5-3B-Instruct
7. /home/lrrelevant/models/Qwen2.5-3B-Instruct
```

### 8.3 LoRA 微调配置（`train/configs/qwen25_3b_lora.yaml`）

```yaml
base_model: ~/models/Qwen2.5-3B-Instruct
output_dir: ./checkpoints/qwen25_3b_lora_v1

# LoRA
lora_r: 16
lora_alpha: 32
lora_dropout: 0.05
target_modules:
  - q_proj
  - k_proj
  - v_proj
  - o_proj
  - gate_proj
  - up_proj
  - down_proj

# 训练
learning_rate: 2.0e-4
per_device_train_batch_size: 2
gradient_accumulation_steps: 8        # 有效 batch = 16
num_train_epochs: 2
max_seq_length: 2048
warmup_ratio: 0.03
lr_scheduler_type: cosine
weight_decay: 0.01
gradient_checkpointing: true

# 精度（视 GPU）
bf16: true            # A100 / H100 / 4090
fp16: false           # T4 / V100 用 fp16 = true, bf16 = false

# 量化（显存紧张时启用 QLoRA）
load_in_4bit: false
bnb_4bit_compute_dtype: bfloat16

# 评估 & 保存
eval_strategy: epoch
save_strategy: epoch
save_total_limit: 2
logging_steps: 20
report_to: none
```

显存预估（3B + LoRA + bf16 + 2048 ctx + bs=2，无 ZeRO）≈ 12–16 GB；4090 / 3090 / A6000 / A100 都可。
若 GPU 仅 8 GB：启用 `load_in_4bit: true`（QLoRA），降到 6–7 GB。

### 8.4 Qwen Chat 模板（`prepare_dataset.py`）

```
<|im_start|>system
你是 VE401 (ECE4010J) 助教。请严格按讲义符号约定回答，并给出讲义页码引用、评分点、陷阱提示。<|im_end|>
<|im_start|>user
{question}<|im_end|>
<|im_start|>assistant
{rendered_solution_steps_with_rubric_and_traps}<|im_end|>
```

---

## 9. 工作流程（端到端）

```
1. 本地 git init → push 空仓
2. 阶段 A：抽 145 条本地题 → 提交
3. 阶段 B：下载 + 抽 1,200 条外部题 → 合并 corpus.jsonl → 提交
4. 阶段 C/D/E/F：MVP 求解器 → 提交（断网可用）
5. 阶段 H：ssh + check_remote_model → 探查远端
6. 远端：git pull → prepare_dataset → train_lora → eval
7. 远端：git push checkpoints (LFS) + eval_report.md
8. 本地：git pull → infer/load_qwen → CLI --mode rag 测试
9. 16 题样卷端到端跑一遍 → 结果写到 progress.md
```

---

## 10. 时间预估

| 阶段 | 工时 | 联网 | 位置 | 阻塞下一阶段 |
|---|---|---|---|---|
| A 本地抽取 | 3–5 h | 否 | 本地 | — |
| B 外部下载抽取 | 3–5 h | 是 | 本地 | — |
| C 分类器 | 2–3 h | 否 | 本地 | D/E |
| D 检索器 | 1–2 h | 否 | 本地 | E |
| E 模板填充渲染 | 2–3 h | 否 | 本地 | F |
| F CLI + 端测 | 2 h | 否 | 本地 | **MVP 完成** |
| H 基建 | 1–2 h | 是 | 本地+远程 | I |
| I 数据准备 + LoRA 训练 | 5–8 h | 是 | 远程 | J |
| J 本地推理打通 | 2–3 h | 否 | 本地 | — |
| **MVP（A–F）** | **13–20 h** | — | — | — |
| **完整版（A–J）** | **21–33 h** | — | — | — |

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 远端 10.35.13.38 上 Qwen2.5-3B 实际不存在 / 路径不同 | I 阶段无法启动 | H5 脚本探查；不存在则远端 `huggingface-cli download` 或本地 `D:\hf_offline\` 下载后 `scp` 上传 |
| 远端 GPU 显存不足 | bf16 跑不动 | 切 QLoRA 4-bit，显存压到 6–8 GB |
| 远端无外网 | 模型与依赖装不上 | 本地下完所有 wheel + 模型权重 → tar → scp → 离线安装 |
| OpenStax / OpenIntro PDF 抽取格式杂乱 | B3/B4 抽取质量差 | 抽 100 题人工校验后迭代正则 |
| Hendrycks MATH 与 VE401 风格差异大 | 微调时引入噪声 | 加权时 `priority=3` 降权；只在本地题库无命中时使用 |
| 1,350 条数据训 3B 模型可能过拟合 | 测试集差 | I3 限 1–2 epoch + early stopping by val loss；保留检索路径 fallback |
| GitHub LFS 配额 | 推送 adapter 卡住 | adapter 一般 < 200 MB；若超出改 `scp` 直传 |
| 远端 `lrrelevant` 账号无 sudo | 系统级依赖装不上 | 一切在 `~/` 下 + venv，conda 也走用户态 |
| 用户输入题面与所有模板都对不上 | 输出乱 | 输出"未命中"+ top-3 最近模板 + 决策树路径 |
| 数值评估包行为差异（scipy 与讲义约定） | 计算结果不一致 | 始终以讲义约定为准；`numerical_eval.py` 全部从 first principles 实现关键统计量 |

---

## 12. 验收标准（DoD）

### 12.1 MVP（阶段 A–F 完结）
1. **题型识别**：`ve401_sample_final_2021.pdf` 16 题，至少 **14/16** 命中正确题型。
2. **解答骨架一致**：14 题中至少 **12 题**输出步骤与官方解答的 5 段骨架对齐（核心步骤名称匹配）。
3. **作业回归**：`ve401_summer21_ex06–10.pdf` 25 题，至少 **20 题**命中正确题型。
4. **响应时间**：CLI 平均 < 2 秒（`--mode rule`）。
5. **断网**：完全离线可运行。
6. **可复现**：`git clone` + `pip install -r requirements.txt` + 跟 README 跑通 MVP。

### 12.2 完整版（A–J 全部完成）
7. **LoRA 提升**：题型识别准确率较 rule baseline 提升 ≥ **5 pp**；最终决策一致率 ≥ **80%**。
8. **同步链路**：从 `git pull` 到本地 CLI `--mode rag` 跑通一道题端到端 ≤ **5 分钟**。
9. **训练日志**：`eval_report.md` 含 train/val loss 曲线、16 题样卷逐题打分表。

---

## 13. 立刻可执行的下一步

按顺序执行：

1. **创建项目骨架**（已建 `ve401_solver/`，下一步写 `plan.md`、`progress.md`、`README.md` 雏形、`requirements.txt`、`.gitignore`、`.gitattributes`）。
2. **`git init` + 关联远端仓库**：`cd D:\4010Cheating Code\ve401_solver && git init && git remote add origin git@github.com:Guilty-C/ECE4010J-Final-Exam.git && git branch -M main`，首次 `git push -u origin main`。
3. **阶段 A 启动**：写 `extract_ve401_html.py`，产出第一份 `ve401_local.jsonl`（约 84 条），提交。
4. **并行：执行 `ops/check_remote_model.sh`**——SSH 进 10.35.13.38，探查 Qwen2.5-3B 是否已存在、GPU/显存/磁盘状态，把结果写进 `progress.md`。
5. **根据 4 的结果决定**：远端已有模型 → 直接进 H4；不存在 → 启动本地下载到 `D:\hf_offline\Qwen2.5-3B-Instruct\` 并安排 `scp`。

---

## 14. 待确认事项

- [ ] 是否走 **MVP 优先**（A→F 先全跑通，再启动 H–J）还是 **并行**（A 边抽数据，同时探查远端环境）？
- [ ] 远端 SSH 鉴权方式（密码 / 已配密钥）？是否已 `ssh-copy-id`？
- [ ] GitHub 推送权限（当前 SSH key 是否已加进仓库 collaborators / deploy keys）？
- [ ] 是否允许执行阶段 B 的网络下载（约 150 MB）？
- [ ] 是否启用 numerical_eval（用 SymPy / scipy 真实算 z-score 与 p-value）？默认关闭仅出模板。
- [ ] LoRA 训练用哪个 GPU 精度配置（bf16 / fp16 / 4-bit）？需 H5 探查后定。

---

**计划完。请审阅。确认后从 § 13 第 1 步开始执行。**
