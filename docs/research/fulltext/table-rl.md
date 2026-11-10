> 이 메모는 2026-11-10에 AI 조사 에이전트가 각 논문의 PDF 전문을 내려받아 읽고 쓴 것이다. 인용문은 원문 그대로이고, 확인하지 못한 것은 NOT CONFIRMED / Not confirmed로 표시되어 있다. 저장소 작성자가 핵심 인용 20여 개를 원문 텍스트에서 다시 찾아 대조했다. 요약과 이 프로젝트와의 관계는 `docs/REPORT.md` §19.4와 `docs/research/papers.md`에 있다.

# RL for table reasoning: five papers, verified from full text

Method: each PDF was downloaded from arxiv.org (HTTP 200 for all five), converted with `pdftotext -layout`,
and read in full (main text + appendices; reference lists skimmed). A few tables/figures were rendered to PNG
to check numbers the text layer garbled. Quotes are verbatim except that words hyphenated across line breaks
are re-joined. "Not stated" = I looked and the paper does not say. "Not confirmed" = could not be established.
Dates/venues come from the PDF and the arXiv abs page only (no other source was consulted).

The PDFs themselves are not stored in this repository.

Naming warning: three different papers are called "Table-R1"/"Table-r1". Below: (2) = Yale "Inference-Time
Scaling", (3) = Beihang/China Telecom "Region-based", (4) = Southeast Univ. "Table-r1 ... Small Language Models".

---

## 1. Reasoning-Table (arXiv 2506.01710) -- id confirmed

**Bibliographic line.** Fangyu Lei*, Jinxiang Meng*, Yiming Huang, Tinghong Chen, Yun Zhang, Shizhu He, Jun Zhao,
Kang Liu. "Reasoning-Table: Exploring Reinforcement Learning for Table Reasoning." arXiv:2506.01710v1 [cs.CL],
2 Jun 2025. Affiliations: Institute of Automation, CAS; University of Chinese Academy of Sciences.
Status: preprint (page header "Preprint."; arXiv Comments: "Work in progress"). No venue.

**URL fetched.** https://arxiv.org/pdf/2506.01710 (200; v1, 29 pp.) and https://arxiv.org/abs/2506.01710 (200).

**Tasks / datasets / language.** TableQA, table fact verification, table-to-text, text-to-SQL; 15 datasets
(App. B.2, Table 12): WikiTQ, HybridQA, MultiHiertt, OTT-QA, FinQA, FeTaQA, TAT-QA, HiTab, Spider, BIRD, ToTTo,
TabFact, FEVEROUS, plus out-of-domain AIT-QA and TableBench. All are English benchmarks; the paper never
mentions Korean or any non-English/multilingual data (full-text search; only hit for "Korea" is a table cell).

**Models / training / compute.**
- Main base model Qwen2.5-7B ("We use Qwen2.5-7B models as the base model", Sec. 4.1); Qwen2.5-Coder-7B and
  OmniSQL-7B for text-to-SQL (Table 4).
- Smallest model trained: Qwen2.5-Instruct **1.5B** (scaling study over 1.5B/3B/7B/14B, Sec. 5.3, Fig. 4).
  Fig. 4 values (read from the rendered figure, avg tableQA): base -> Reasoning-Table = 28.5 -> 33.6 (1.5B),
  36.8 -> 48.4 (3B), 46.65 -> 62.6 (7B), 50.7 -> 70.8 (14B). Quote: "post-training performance gains are
  minimal for smaller models (1.5B), while larger models show significant improvements." (Sec. 5.3)
- Four settings: No-Reason SFT, Reason-SFT, RL-zero, Reason SFT+RL. "We use Reason-SFT data for a cold start
  ... followed by GRPO training on the fine-tuned checkpoints." (Sec. 4.1). Algorithm: GRPO with DAPO
  Clip-Higher (App. C.1). SFT is full fine-tuning (App. C.1). lr 1e-6 for RL.
- Compute (GPU type/count/hours): **not stated** anywhere in the paper.

**Reward (Sec. 3.4).**
- Answer: "producing a binary reward Rans in {0, 1}, where 1 indicates a correct or equivalent answer" --
  via exact match, SQL execution-result match, F1 threshold, or BLEU threshold depending on task.
- Format: "we enforce the presence of both <think> and <answer> tags in the model's output."
- Position (cell evidence): "the model is required to annotate table cells with <|cell content|><|column name|>
  tags when directly referencing them in reasoning." Rpos = |P ∩ G| / |P ∪ G| (P = cells annotated by the
  model, G = gold cells) -- i.e. graded partial credit by Jaccard overlap.
- Final: `R(o_i) = Rans(o_i) × (1 + λ1·Rpos(o_i)) + λ2·Rfmt(o_i)`.
- IMPORTANT: the main results do **not** use the position reward: "We utilize the rule-based outcome reward,
  set λ1 = 0, λ2 = 0.2." (Sec. 4.1). Position reward (λ1 = 0.2) appears only in ablations (Tables 3, 4).
- Tool/program execution: only for SQL. Limitations: "we did not integrate a code execution module for other
  tasks such as tableQA".
- Gold positions: LLM-annotated ("we use LLMs to sample each example 5 times. We filter for samples with
  correct final answers", Sec. 3.2; the sentence says "union" but the formula printed is an intersection ⋂ --
  inconsistency in the paper), or existing dataset annotations (TAT-QA, HiTab); gold-SQL column names for
  text-to-SQL.

**Reward hacking / degenerate outputs.** No empirical incident is reported (no counts, no failure analysis).
But the exploit is explicitly anticipated and designed against (Sec. 3.4): "Simply summing these rewards could
allow the model to achieve a high score by prioritizing consistency (e.g., correct cell annotations or format)
even when the answer is incorrect." Fix: "The multiplication of Rans with the position reward term ensures that
Rpos contributes only when the answer is correct". Separately: "To prevent rapid entropy collapse during
training, we follow DAPO ... and apply the Clip-Higher strategy" (App. C.1).

**Cited cells / evidence evaluated separately?** Output cites cells (by cell content + column name, inside the
<think> text; not row/column indices) only in the position-reward variant. Evidence correctness of the
*trained model* is **not** reported; ablations report answer accuracy only (Table 3). The only evidence-validity
numbers are for the LLM-generated annotation data (App. A.3, Table 10): "Valid Evidence Responses indicates
that the evidence in the reasoning process is true from the table; Overall Correct denotes the accuracy of both
correct answers and evidence from the table" (e.g. TAT-QA: solve rate 74.00, valid evidence 72.57%, overall
correct 67.29; average overall 71.17).

**Abstention / inference-time verifier.** None. (LLM-as-judge is used only as an alternative training reward,
Sec. 5.1; test-time scaling = majority voting on BIRD, Sec. 5.4.)

**Headline results.**
- Table 1 (EM/Acc), unified training, Reason SFT+RL: AVG over 7 tableQA sets **62.62** vs Claude 58.79,
  GPT-4o 58.96, Qwen2.5-7B-Inst 46.65. Single-dataset Reason-SFT+RL: WikiTQ 80.07, HiTab 81.94, TAT-QA 79.79.
- Table 2: BIRD EX 63.16, Spider EX 84.20 (Qwen2.5-Coder); Table 4: BIRD dev **68.3** with OmniSQL-7B +
  position reward + N-gram reward.
- Position-reward ablation (Table 3, Reason SFT+RL): λ1=0,λ2=0 -> λ1=0.2,λ2=0: WikiTQ 80.35 -> 80.95,
  TAT-QA 79.62 -> 79.47, HiTab 81.38 -> 81.60. (The text says "approximately 0.6% on WikiTQ and TAT-QA";
  the table shows a small *decrease* on TAT-QA.) Table 4: BIRD 62.1 -> 63.1.
- Unified training is worse than single-dataset training on several sets (Limitations).

---

## 2. Table-R1: Inference-Time Scaling for Table Reasoning (arXiv 2505.23621) -- id confirmed

**Bibliographic line.** Zheyuan Yang*, Lyuhao Chen*, Arman Cohan, Yilun Zhao. "Table-R1: Inference-Time Scaling
for Table Reasoning." arXiv:2505.23621v2 [cs.CL], v1 29 May 2025, v2 26 Sep 2025. Yale NLP Lab; Carnegie Mellon
University. Venue: **EMNLP 2025** per the arXiv Comments field (not cross-checked against the ACL Anthology).

**URL fetched.** https://arxiv.org/pdf/2505.23621 (200; v2, 20 pp.) and https://arxiv.org/abs/2505.23621 (200).

**Tasks / datasets / language.** Short-form table QA (WTQ, HiTab), fact verification (TabFact), free-form QA
(FeTaQA) for training (Table 1); 13 evaluation sets incl. out-of-domain TabMCQ, TabMWP, FinQA, InfoTabs,
PubHealthTab, FEVEROUS, ToTTo, QTSumm, RotoWire (Sec. 4.2). English only; no Korean/multilingual data.

**Models / training / compute.**
- "We initialize Table-R1 with Qwen2.5-7B-Instruct and Llama-3.1-8B-Instruct models." (Sec. 4.1). Base
  (non-instruct) variants in ablation. Smallest trained: 7B.
- Two *separate* variants, not a pipeline: Table-R1-SFT (distillation from DeepSeek-R1 traces, 33,601 examples)
  and Table-R1-Zero (RLVR directly on the instruct model, 48,563 examples; App. A.1).
- RL: GRPO with DAPO-style token-level loss and asymmetric clipping; "we omit the KL penalty term" (Sec. 3.3).
  "we use a batch size of 256 and 16 rollouts per prompt ... It is trained for 2 epochs." lr 1e-6.
- Compute: "All the experiments are conducted on 4 NVIDIA A100 80GB GPUs." (Sec. 4.1)

**Reward (Sec. 3.3).** "Our reward framework consists of two components: accuracy rewards and format rewards."
- TQA: "We employ exact match to assign a reward of 1 for a correct answer and 0 otherwise."
- TFV: 1 if label matches, else 0.
- FF-TQA: "We use the average of normalized BLEU and ROUGE-L scores" (continuous).
- Format: "The format reward is computed by a deterministic regular expression-based checker, which assigns
  partial credit as outputs progressively satisfy structural requirements (e.g., tag presence, JSON structure,
  valid answer types), and awards full credit for strictly conformant outputs."
- No program execution, no cell/evidence/position reward. Partial credit exists only for format (and the
  BLEU/ROUGE reward).

**Reward hacking / degenerate outputs.** Mentioned only as a design claim, no incident reported: "This
combination of rule-based and metric-based evaluation ensures reward interpretability and robustness,
mitigating instability and reward hacking." (Sec. 3.3). Reported instability: "Table-R1-Zero-Llama-3.1-8B
displays considerable instability, ultimately failing to acquire the desired response format." (Sec. 4.4; in
App. Table 7 that base-model variant scores 50.3 on binary TabFact). Removing the format reward "reduces
training stability and slightly lowers in-domain performance" (Sec. 4.7).

**Cited cells / evidence.** None. Output is <think>...</think><answer>{"answer": ...}</answer>. Column-aware
reasoning is discussed only qualitatively (Sec. 4.6). No evidence metric.

**Abstention / inference-time verifier.** None. (GPT-4.1 mini re-judges EM failures at *evaluation* time only.)

**Headline results (Table 2; TQA = EM "with ambiguous cases re-evaluated by GPT-4.1 mini").**
- Table-R1-Zero (Qwen2.5-7B-Instruct): WTQ 79.8, HiTab 78.1, TabFact 87.6, FeTaQA BLEU 30.6
  (base Qwen2.5-7B: 54.8 / 61.8 / 72.2 / 21.0).
- Table-R1-Zero (Llama-3.1-8B-Instruct): WTQ 81.2, HiTab 81.4, TabFact 87.6, FeTaQA 32.7.
- Table-R1-SFT (Llama): WTQ 83.8, HiTab 81.8, TabFact 91.1. Note: on in-domain WTQ/HiTab/TabFact the SFT
  (distillation) variant is equal or better than the RL variant for both backbones; the paper's claim for RL
  is better FeTaQA and out-of-domain generalization ("RLVR methods yielding stronger generalization").

---

## 3. Table-R1: Region-based Reinforcement Learning for Table Understanding (arXiv 2505.12415) -- id confirmed

**Bibliographic line.** Zhenhe Wu, Jian Yang, Zhongjiang He, Changzai Pan, Jie Zhang, Jiaheng Liu, Xianjie Wu,
Yu Zhao, Shuangyong Song, Yongxiang Li, Zhoujun Li, Xuelong Li. "Table-R1: Region-based Reinforcement Learning
for Table Understanding." arXiv:2505.12415v3 [cs.CL]; v1 18 May 2025, v2 13 Jun 2025, v3 13 May 2026 (v3 is
what I read). Beihang University; Xingchen AGI Lab, China Telecom AI Technology (Beijing); TeleAI, China Telecom.
Venue: **not confirmed** (no Comments/journal-ref on arXiv; ACL-style template but no venue line in the PDF).

**URL fetched.** https://arxiv.org/pdf/2505.12415 (200; v3, 18 pp.) and https://arxiv.org/abs/2505.12415 (200).

**Tasks / datasets / language.** Table QA. Train: TableInstruct (19,661 samples; four reasoning modes DP, TCoT,
SCoT, PoT). Test: TableBench (3,544), WikiTQ test (4,344), WikiSQL test (15,878) (Table 1). English; no Korean
or multilingual data mentioned.

**Models / training / compute.**
- Seven bases: Qwen2-7B, CodeQwen-7B, DeepSeek-Coder-7B, Llama3.1-8B, TeleChat2-7B, **Qwen2.5-3B** (smallest),
  Qwen3-8B (Table 2). "Our experiments are conducted exclusively on models with 3B to 8B parameters"
  (Limitations).
- Two stages: RE-SFT (region-enhanced SFT on TableInstruct-RE) then TARPO (a GRPO extension, with KL term).
- Gold regions: "We employ DeepSeek-R1 to generate the minimal table regions ... manually verify the
  correctness, and obtain the TableInstruct-RE dataset." (Sec. 3)
- Compute: RE-SFT "8*A100 GPUs ... 2 to 2.5 hours for each training"; TARPO "7B/8B-sized LLMs are trained on
  4*80GB-H100 GPUs, and the 3B-sized LLM on 8*40GB-A100 GPUs. The training lasts for 3 epochs and around
  72 hours." G = 16, lr 7e-7.

**Reward (Sec. 2.4).**
- Mixed reward, *additive*: `r_i = α_τ·r_i^t + (1 − α_τ)·r_i^a`.
- Answer: "r_i^a is binary, taking a value of 1 when the inferred answer matches the correct answer, and 0
  otherwise (Numerical answers match if equal, while string answers match if the Rouge-L score exceeds
  threshold ζ)".
- Region (graded partial credit): "computing the IoU ... separately for the rows and columns between the table
  region obtained in the reasoning process and the ground truth. The results are then summed and averaged".
- Decaying weight: α_τ = γ·e^(−ρτ); {ζ, γ, ρ, λ} = {0.6, 0.3, 9e-4, 0.1}. "as training progresses ... we shift
  the focus of the reward more towards the accuracy of the answers."
- Consistency penalty on advantages: P_i = −λ·ΔA_i^t·ΔA_i^a when the two have opposite signs.
- No format reward is described. Whether PoT code is executed to compute the RL answer reward: **not stated**.

**Reward hacking / degenerate outputs.** The term is not used and no exploit incident is reported. Closest
statements: "If ΔA^t and ΔA^a are of opposite signs, we consider that the reasoning process might be accidental
and violates the consistency preference." (Sec. 2.4.3); the penalty works by "preventing the LLM from learning
low-quality reasoning strategies that generate correct answers accidentally" (Sec. 4.2). Sec. 4.3 notes that a
fixed (non-decaying) region weight keeps mean reward higher while accuracy is lower: "fixed-weight TARPO
continues to benefit from the reward of the table region part". Plain GRPO inflated response length (+373%
tokens on WikiSQL, Table 3).

**Cited cells / evidence.** Yes, but as a row/column *region*, not cells: the model emits
`<gold_area>{"columns": [...], "rows": [...]}</gold_area>` inside its reasoning (App. B, Figs. 5-8). A
cell-index format `{"cells": [(0,0), (0,3), ...]}` was considered and rejected (Fig. 1: "Weakness: 1. waste
tokens 2. no sub-table structure"; Fig. 3e-f shows it scoring lower with more tokens). Region is admittedly
loose: "it may inevitably include some irrelevant cells". Region accuracy of the trained model on test sets is
**not reported** -- Tables 2-4 give answer metrics and token counts only; there is no "answer right but region
wrong" analysis at test time.

**Abstention / inference-time verifier.** None. (The TableBench PoT prompt contains "If the user's question is
not related to data analysis, please politely refuse", Fig. 8, but refusal is never evaluated.)

**Headline results (Table 2).** Table-R1 on Qwen3-8B: TableBench DP 44.54 / TCoT 49.30 / SCoT 47.21 / PoT 44.54,
WikiTQ 73.87, WikiSQL 72.50, Overall 55.33 (GPT-4o overall 49.17). Qwen2.5-3B: overall 36.12 (SFT) -> 39.22
(RE-SFT) -> 45.74 (Table-R1). Abstract: "average performance improvement of 14.36 points across multiple base
models"; "TARPO significantly reduces the reasoning token consumption by 67.5% compared to GRPO". Caveat from
Table 3: RE-SFT alone lowered out-of-domain WikiTQ (−3.96) and WikiSQL (−1.57) on Qwen3-8B.

---

## 4. Table-r1 for Small Language Models (arXiv 2506.06137) -- id confirmed; it IS a third "Table-r1"

**Bibliographic line.** Rihui Jin, Zheyu Xin, Xing Xie, Zuoyi Li, Guilin Qi, Yongrui Chen, Xinbang Dai, Tongtong
Wu, Gholamreza Haffari. "Table-r1: Self-supervised and Reinforcement Learning for Program-based Table Reasoning
in Small Language Models." arXiv:2506.06137v1 [cs.LG], 6 Jun 2025. Southeast University (Nanjing); Monash
University. Status: "Preprint. Under review." (NeurIPS-style checklist attached). No venue.

**URL fetched.** https://arxiv.org/pdf/2506.06137 (200; v1, 28 pp.) and https://arxiv.org/abs/2506.06137 (200).

**Tasks / datasets / language.** Table reasoning (QA + fact verification): WTQ, TabFact, HiTab, AIT-QA
(Table 1). English; no Korean/multilingual data. "Small" here means 7-8B: "The SLMs used in this study refer to
7B or 8B-scale language models, and the proposed approach may not be directly applicable to smaller models such
as 3B or 0.5B LMs." (App. A)

**Models / training / compute.**
- "Our base models are Qwen2.5-Coder-7B and LLaMA3.1-8B-Instruct, with DeepSeek-v3 serving as the teacher
  model for the cold-start phase." Smallest trained: 7B.
- "Both supervised fine-tuning (SFT) and reinforcement learning (RL) are implemented using LoRA, with a rank
  of 32 for SFT and 64 for RL." (App. C)
- Pipeline: Stage 1 self-supervised "Layout Transformation Inference" (SFT); Stage 2 distillation cold-start
  SFT, then "mix-paradigm" GRPO (model picks program output or direct text answer). trl library; 1 epoch;
  "input tables are truncated to the first 10 rows"; best at ~400 steps.
- Compute: "All experiments are conducted on NVIDIA RTX 4090 GPUs and NVIDIA H100 GPUs." Counts/hours not stated.

**Reward (Sec. 4.2.3 + App. D Table 6).** Sum of components, R(c_i) = Σ_j R_j:
- strict_format_reward (max 0.75); ans_reward (max 1.5, "Measures the similarity between the model output and
  the reference answer" -- graded, not pure EM); compilation_correctness (0.75); comment_ratio (0.45);
  multiple_python_blocks_penalty (1.0); code_short_length_penalty (0.5).
- "For P-TR outputs, we execute the generated code to obtain the answers; for text-based outputs, we use
  regular expression matching."
- No cell/evidence/position reward.

**Reward hacking / degenerate outputs.** Described as reward-design rationale (no counts, no before/after
analysis): "Incorrect but compilable outputs (e.g., print(final answer)) are penalized heavily."; "Short Code
Penalty. To discourage degenerate behaviors (e.g., overly short programs), we impose penalties on code
completions that are below a specified length threshold."; "Text-based outputs are assumed valid by default,
which introduces a bias that is counteracted by other reward terms." (Sec. 4.2.3). Limitation: "the reward
weighting ... heavily reliant on empirical tuning and lacking automation."

**Cited cells / evidence.** None. Output is <reasoning> + either <code_solution> (Python) or <answer>.

**Abstention / inference-time verifier.** No abstention. The "fallback" is from program to direct text answer,
not to "no answer". Inference uses a code executor plus "self-consistency (SC) with majority voting, using 5
samples per prediction" (Sec. 5.1).

**Headline results (Table 2; accuracy, SC=5, mean ± sd over three runs).** Qwen2.5-Coder-7B: WTQ 76.5 ± 0.74,
TabFact 85.3 ± 0.81, HiTab 76.7 ± 0.72, AIT-QA 89.9 ± 0.88 (base: 63.5 / 76.0 / 62.7 / 55.5). LLaMA3.1-8B:
74.3 / 84.4 / 74.2 / 86.5. Ablation (Table 3, Qwen): without GRPO 71.7 / 81.2 / 70.4 / 83.3; without cold
start 71.1 / 80.5 / 68.8 / 67.3 -- "Cold start provides the largest gains". Also: "GRPO after distillation
reduces potential. Moreover, GRPO still cannot fully convert potential into actual capability." (Sec. 5.4)
Claim to note: "To the best of our knowledge, we are the first to apply GRPO to TR." (Reasoning-Table and the
Yale paper make similar "first" claims; all three are May-June 2025.)

---

## 5. TableGPT-R1 (arXiv 2512.20312) -- id confirmed

**Bibliographic line.** Saisai Yang*, Qingyi Huang*, Jing Yuan*, Liangyu Zha*, Kai Tang*, Yuhang Yang*, Ning Wang,
Yucheng Wei, Liyao Li, Wentao Ye, Hao Chen, Tao Zhang, Junlin Zhou, Haobo Wang, Gang Chen, Junbo Zhao.
"TableGPT-R1: Advancing Tabular Reasoning Through Reinforcement Learning." arXiv:2512.20312v2 [cs.LG]; v1
23 Dec 2025, v2 25 Dec 2025. Zhejiang University; Institute of Computing Innovation, Zhejiang University.
Status: "TableGPT-R1 technical report." No venue.

**URL fetched.** https://arxiv.org/pdf/2512.20312 (200; v2, 18 pp.) and https://arxiv.org/abs/2512.20312 (200).

**Tasks / datasets / language.** Agentic table analysis with Python execution, table QA, NL2SQL, plus general
math/code/QA data. Evaluation: internal benchmark (59 tables, 620 QA pairs), Spider, BIRD, TableBench,
RealHitBench, InfiAgent-DABench; general: HumanEval, MBPP, GSM8K, MATH, AIME, CMMLU-5, GPQA-Diamond. Chinese and
English both appear (language filter example "a Chinese question paired with an English response", Sec. 2.2;
a Chinese case in Fig. 7; CMMLU). No Korean.

**Models / training / compute.**
- Base Qwen3-8B (only size). "we sample approximately 3% of the full dataset ... and fine-tune the base model
  (Qwen3-8B)" as SFT warm-up, then three-stage RL (general -> table-agentic -> hard samples) (Sec. 3.5).
- Algorithm: GRPO "with recent improvements introduced by DAPO and GSPO" (sentence-level importance ratio,
  asymmetric clipping) plus entropy bonus / entropy-decay terms against "the entropy collapse commonly
  observed in GRPO training" (Sec. 3.3).
- Compute, lr, batch size, rollouts: **not stated**.

**Reward (Sec. 3.4).**
- Terminal reward routed by task type (Table 1): rule-based for labelled tasks ("when the task admits exact
  matching or execution-based verification (e.g., SQL execution followed by rule extraction)"), or a
  "Criteria-Injected Reward Model" (LLM judge, 0-10 score against pre-generated criteria) for open-ended tasks.
- Process step reward: "if the model selects an incorrect function, we assign a negative reward as -0.2";
  +0.1 for correct function with successful execution before termination; −0.1 if execution fails.
- R(τ) = Σ_t (R_base(t) + R_reg(t)); R_reg = "composite penalty that captures length control, repetition
  suppression, and invalid-reflection mitigation (e.g., excessive "wait"-like tokens)" plus a plotting penalty.
- No cell/evidence/position reward. No ablation of reward components is reported.

**Reward hacking / degenerate outputs.** Reported explicitly (qualitatively; no counts or before/after numbers):
- "to prevent reward hacking where the policy inserts unnecessary plotting code to gain credit, we introduce a
  simple need_plot supervision signal ... and apply a strong negative penalty whenever the policy generates
  visualization code for samples labeled as need_plot=False" (Sec. 3.4.3).
- "beyond steps 120-200, models consistently exhibit a sharp decline in general capabilities alongside various
  reward-hacking behaviors—such as generating corrupted tokens or skipping reasoning steps to directly output
  final answers." (Sec. 3.5)
- Mitigation: three-stage curriculum with early stopping ("We terminate each stage at step 200") and data
  re-filtering by pass@k.

**Cited cells / evidence.** None. Output is <think> / <tool_call> / <tool_response> / <answer>.

**Abstention / inference-time verifier.** None. Verifiers (rules, LLM judge) are used for training reward and
data filtering only; at inference the model just runs code in a Python environment.

**Headline results (Table 2, TableGPT-R1-8B).** Spider EX 86.73; BIRD EX 63.17 (Qwen3-8B: 86.07 / 61.67);
TableBench (Rouge) DP 48.35, PoT 35.12, SCoT 49.53, TCoT 48.28; RealHitBench FC 63.85, NR 49.03, SC 64.12,
DA 66.53, CG 55.84; InfiAgent-DA 80.54; internal benchmark 80.00 (Table Info) / 82.70 (Table Path). "an average
improvement of 11.32% over TableGPT2-7B" (Sec. 1). PoT is 4.68 below TableGPT2-7B. General ability roughly
preserved (+1.01% avg vs Qwen3-8B; regressions on MBPP, CMMLU-5, GPQA-Diamond; Table 3).

---

## What TableTrace must NOT claim as new given these papers

1. **RL with verifiable/rule-based rewards (GRPO, "RLVR") for table QA.** All five do this; papers 1, 2 and 4
   each already claim to be first (May-June 2025).
2. **A reward for citing the right cells / evidence positions.** Reasoning-Table has a cell-level position
   reward (Jaccard of annotated vs gold cells); region-based Table-R1 has a row/column IoU region reward.
3. **Partial credit for evidence overlap.** Both of those rewards are graded overlap scores.
4. **The insight that evidence partial credit can be earned with a wrong answer, and the fix of gating it on
   answer correctness.** Reasoning-Table states the risk and multiplies Rpos by Rans; region-based Table-R1
   decays the region weight and penalises region/answer inconsistency. TableTrace's v1 -> later-version fix is
   a re-discovery of a documented design point (it can be reported as an independent empirical confirmation).
5. **"First to observe reward hacking in table RL."** TableGPT-R1 reports opportunistic plotting, corrupted
   tokens and skipped reasoning; Table-r1 (SLM) penalises `print(final answer)`-style and overly short programs.
6. **Program output + tool execution as the reward source, with LoRA on a "small" model.** Table-r1 (SLM)
   does exactly this at 7-8B (LoRA r=32/64, executed Python, format + answer + compile rewards).
7. **SFT-then-RL pipelines and format-validity rewards.** Papers 1, 3, 4, 5 use SFT -> RL; paper 2 has a
   partial-credit format reward.
8. **"RL did not beat supervised" as a surprising finding.** Paper 2's distillation-SFT model is equal or better
   than its RL model on in-domain WTQ/HiTab/TabFact; paper 1 finds gains "minimal for smaller models (1.5B)";
   paper 4 finds cold-start SFT gives the largest gain. A null RL result at ~1B is consistent with these.

## What still looks different (and how confident)

Scope caveat: these statements are relative to these five papers only, not to the whole literature.

1. **Korean / KorWikiTQ.** None of the five uses Korean data; four are English-only, TableGPT-R1 adds Chinese.
   Confidence: high (datasets read in full + text search).
2. **Inference-time rule-based verifier with abstention** (answer accepted only if the cited cells support it).
   None of the five has abstention, unanswerable handling, or an accept/reject verifier at inference; all use
   verification only as a training reward. Confidence: high.
3. **Evidence correctness measured separately from answer correctness for the trained model** ("answer right,
   evidence wrong"). None reports it. Closest: Reasoning-Table Table 10 (validity of LLM-generated evidence
   annotations, not of the trained model) and region-based Table-R1's training-time consistency penalty.
   Confidence: medium-high.
4. **Model scale.** mT5-small and a 1.2B model with LoRA are below everything trained here except
   Reasoning-Table's 1.5B Qwen2.5 point (close to 1.2B, so "smaller than prior work" is only marginally true);
   others are 3B (paper 3) or 7-8B. Paper 4 explicitly says its method may not transfer to 3B/0.5B.
   Confidence: high on the facts, medium on how much novelty this carries.
5. **Index-addressed cell citations (r{i}c{j}) inside a compact, deterministically re-executed op program.**
   Reasoning-Table cites by cell content + column name in free text; region-based Table-R1 uses a row/column
   region and explicitly rejected a cell-index format on token cost; papers 4-5 execute free-form Python with no
   citations. The combination looks different; the ingredients are not. Confidence: medium.
6. **A quantified exploit report** (160 exploiting outputs -> 0 after the reward change). The prior papers
   describe hacking qualitatively or as design rationale, with no counts. This is a difference in reporting
   detail, not a new concept. Confidence: medium.
7. **Table-level re-split to prevent table leakage.** None of the five discusses table-disjoint re-splitting
   (paper 4 even splits AIT-QA "8:2 based on questions"; paper 3 splits TableInstruct-RE 9:1 at random).
   Confidence: medium (absence of discussion, not evidence that their splits leak).
