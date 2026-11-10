> 이 메모는 2026-11-10에 AI 조사 에이전트가 각 논문의 PDF 전문을 내려받아 읽고 쓴 것이다. 인용문은 원문 그대로이고, 확인하지 못한 것은 NOT CONFIRMED / Not confirmed로 표시되어 있다. 저장소 작성자가 핵심 인용 20여 개를 원문 텍스트에서 다시 찾아 대조했다. 요약과 이 프로젝트와의 관계는 `docs/REPORT.md` §19.4와 `docs/research/papers.md`에 있다.

# Full-text verification notes: four papers vs. TableTrace

Checked 2026-11-10. All four PDFs were downloaded from arXiv (HTTP 200) and converted with `pdftotext`.
Quotes are verbatim from the extracted text; only PDF line-break hyphenation and small-caps spacing
(e.g. "T AB ROUGE" -> "TabROUGE") were repaired. "Not confirmed" = I could not find it in the full text.
The PDFs themselves are not stored in this repository.

Reading coverage: papers 2, 3, 4 were read end to end (main text + appendix). Paper 1 (50 pages incl.
appendices and checklist): Sections 1-5, Appendix A, F.1.2 and G.3 were read; the remaining appendices (B-G) were only
keyword-searched (attribut*, citation, cell, abstain/abstention/refus*, verif*, Korean/English/
multilingual, GRPO/LoRA) and their headings listed; G.6 (evaluation protocol) was also read.

---------------------------------------------------------------------------------------------------

## 1. RE-Tab (arXiv 2601.22530)

**Bibliographic line.** Tung Sum Thomas Kwok*, Xinyu Wang*, Hengzhi He, Xiaofeng Lin, Peng Lu, Liheng Ma,
Chunhe Wang, Chun Ho Mak, Yuyu Luo, Yingnian Wu, Lei Ding, Guang Cheng. "Enhancing Table Reasoning with
Deterministic Table-State Rewards." arXiv:2601.22530v2 [cs.AI], 15 May 2026. Affiliations: UCLA, McGill,
Universite de Montreal, UCL, HKUST (Guangzhou), Univ. of Manitoba.
- ID check: yes, this is the RE-Tab paper, but the title does not contain "RE-Tab". **Title changed between
  versions**: v1 (30 Jan 2026) = "Enhancing TableQA through Verifiable Reasoning Trace Reward" (10 authors);
  v2 (15 May 2026) = title above (12 authors, substantially rewritten, GRPO study added).
- Venue: page-1 footer says "Preprint."; a "NeurIPS Paper Checklist" is appended. Acceptance anywhere:
  **not confirmed**. arXiv listing has no comments/journal-ref.
- URLs fetched: https://arxiv.org/pdf/2601.22530 (v2, 200), https://arxiv.org/pdf/2601.22530v1 (200),
  https://arxiv.org/abs/2601.22530 (200).

**Task / contribution.** Method, not a benchmark. A deterministic lexical reward (TabROUGE) on intermediate
table states of a tool-using table agent, plus a framework (RE-Tab) that uses it for step feedback, early
stopping and trajectory selection.
- "we introduce TabROUGE, a training-free and deterministic state reward. By adapting the Longest Common
  Subsequence (LCS) metric from text summarization to evaluate tabular states" (Abstract, p.1)
- Definition: r = LCS(Q, Enc(T_{l+1})) / |Enc(T_{l+1})|, with a "[header] is [value]" serialization
  (Sec. 3.3, Eq. 1, p.5). It compares the *question* with the *table state*; no gold cells are involved.
- "Across six backbones and three benchmarks, RE-Tab improves accuracy by an average of 26.7 pp over
  no-reward baselines. It also reduces TTS samples by up to 33%." (Abstract)

**Datasets / languages / models.**
- "we report accuracy on WTQ, TableBench (TB: numerical reasoning (NR), fact checking (FC), data analysis
  (DA)) [63], TabFact [5], and MMQA [62]" ... "We sample n = 200 per dataset with random seed 1018, except
  for the full TB-FC dataset where n = 96." (Sec. 4, Datasets, p.6). Ablations: WTQ, MMQA, MMTU (Sec. 4.2).
- Language: the words English/Korean/multilingual/Chinese do not occur anywhere in v1 or v2. Language of
  data is **not stated**; no Korean, no non-English evaluation found.
- Models: GPT-3.5 (parity with prior systems), DeepSeek-R1-Distill-Qwen-14B (PRM comparison), and six
  ablation backbones "(Qwen3-8B, Ministral-3-8B, GPT-4.1-nano, GPT-oss-20B, GPT-5-nano, and GPT-5.4)"
  (Sec. 4.2, p.7). Smallest open models are 8B.

**Cell/row/column attribution measured separately from answer correctness?** **No.** The only task metric
is answer accuracy (Tables 1-4), scored by "dataset-standard exact-match or denotation-equivalence comparison
against ground truth" after answer extraction and normalization (App. G.6, p.39-40). Full-text search finds no attribution, citation, or cited-cell metric.
Nothing equivalent to "answer correct but attribution wrong". The nearest analysis is reward-vs-correctness
association: "a Spearman correlation of rho=0.287" between reward and final answer correctness
(App. F.1.2, p.24) and a "ranking-inversion rate" for reward robustness (Sec. 4.4, p.9).
- v1 only uses the phrase "cell-level accuracy" to say it is the wrong criterion for *table states*:
  "conventional correctness or cell-level accuracy is insufficient" (v1, Sec. 3) - not about cited cells.

**Verifier / trust score / abstention?** No abstention (abstain/abstention/refus* do not occur). TabROUGE is
rule-based/deterministic but is a ranking and stopping signal, explicitly not a verifier:
- "Because TabROUGE is consumed as a relative Best-of-K ranking signal rather than an absolute correctness
  verifier" (Sec. 3.3, p.6)
- "We position TabROUGE as a deterministic control signal scoped to serialized table-state supervision,
  not as a substitute for learned or executor-grounded verifiers." (Sec. 5, p.9)
- It is explicitly executor-free ("without requiring learned models or external executors", Abstract);
  an "executor-grounded final-stage verifier" is named as future work (Sec. 5, p.9-10).

**Training?** Mainly training-free; v2 adds a small RL study (not in v1):
- "we run an initial GRPO [48] study on Qwen3-8B, training WTQ and MMQA for 300 steps and MMTU for 150
  steps" (Sec. 4.3, p.8). Table 4 averages: Base 31.64 / TTS 50.69 / GRPO 59.03 (accuracy; MMTU got worse
  than TTS: 41.30 vs 52.17). Setup: 4x A100, group size 8, LR 1e-6, 200 / 92 / 92 training examples
  (App. G.3). No LoRA mentioned. The reward optimized is TabROUGE; the outcome measured is answer accuracy.

---------------------------------------------------------------------------------------------------

## 2. ViTaB-A (arXiv 2602.15769)

**Bibliographic line.** Yahia Alqurnawi*, Preetom Biswas*, Anmol Rao*, Tejas Anvekar, Chitta Baral,
Vivek Gupta (Arizona State University). "ViTaB-A: Evaluating Multimodal Large Language Models on Visual
Table Attribution." arXiv:2602.15769v1 [cs.CL], 17 Feb 2026. Page header: "Under review as a ES-Reasoning
workshop paper at ICLR 2026" (acceptance **not confirmed**).
- URLs fetched: https://arxiv.org/pdf/2602.15769 (200), https://arxiv.org/abs/2602.15769 (200).

**Task / contribution.** Benchmark + evaluation study only (no method).
- "we study structured data attribution/citation, which is the ability of the models to point to the
  specific rows and columns that support an answer." (Abstract)
- Built from HiTab; three representations (Markdown, JSON, rendered image, plus colour/font perturbations):
  "For each representation, we select 200 tables as the visual table attribution benchmark." (Sec. 3.2, p.4)
- Models: "Gemma-3 family (4B, 12B, and 27B), InternVL3.5 models (4B, 8B, 14B, and 38B), Qwen3-VL
  vision-language models (2B, 4B, 8B, and 32B), and the Molmo2 family (4B and 8B)" (Sec. 3.3, p.4).
  Main-text tables are for the 4B models; zero-shot / few-shot / CoT prompting.
- Language: **not stated** (no occurrence of English/Korean/multilingual). Only HiTab is used.

**Attribution measured separately from answer correctness?** Yes - this is the paper's central point.
- Metrics (Sec. 3.4.1, p.5): "We compute cell-level accuracy measure to see how accurately the model returns
  the correct evidence cells. We also report row-wise and column-wise accuracy scores". Cell/row/column
  precision, recall, F1 are in App. A.4. The exact formula for "cell-level accuracy" (exact set match vs
  per-cell) is **not given - not confirmed**.
- IMPORTANT design fact: in the attribution task the gold answer is supplied to the model.
  "The answer is given to the model to shift the burden from generation to grounding" (Sec. 3.1, p.3).
  So QA accuracy and attribution accuracy come from two separate tasks on the benchmark.
- **Conditional rate "answer correct but attribution wrong": not reported.** Only marginal QA accuracy vs
  marginal attribution accuracy. The sentence "models often identify the correct answer but fail to reliably
  point to the specific rows and columns that support it" (Sec. 4.1, p.6) is an interpretation of that
  aggregate gap, not a per-instance measurement. How QA accuracy was obtained (prompt, scoring) is
  **not described** in the paper (Appendix A.1 has attribution prompts only).
- Headline numbers, Table 1 (4B models, average over 4 models x 3 prompt styles; QA% / Attr%):
  Markdown 55.08 / 25.55; JSON 55.16 / 0.88; Images 48.66 / 33.89. Best row: InternVL3.5 zero-shot,
  average QA 62.66 vs Attr 32.37. So attribution is roughly 15-54 points below QA depending on format.
  (The abstract/intro say QA "around 48-55%" and attribution "often below 30%"; Sec. 4.1 says QA
  "typically around 50-60%" and attribution "around 33% in images" - the paper is loosely worded here.)
- Row vs column, Table 2 averages (Row / Column): Markdown 71.63 / 30.03; JSON 5.93 / 26.15;
  Images 61.04 / 44.2. "row accuracy is approximately 1.3-2x higher than column accuracy for Markdown and
  image-based tables." (Sec. 4.3, p.7)
- Larger models are better but still far from solved (App. Tables 7, 9): Qwen3-VL-32b CoT 59.00 (Markdown)
  / 70.10 (Images); InternVL3.5-38b CoT 58.00 / 59.5; smallest model Qwen3-VL-2b zero-shot 8.50 / 14.10.

**Verifier / trust score / abstention?** No verifier and no abstention. It studies model-based confidence
only: internal confidence (token probabilities of cited cells), verbalized certainty (6-level self-report),
alignment score A = 1 - Brier, and split-conformal prediction sets (App. A.3).
- "confidence measures should not be viewed as a reliable indicator for attribution quality." (Sec. 4.4, p.8)
- "adding a second step that verifies citations using confidence may not reduce user risk." (Sec. 4.5, p.8)

**Training?** Evaluation only. Training is listed as future work: "Attribution should be treated as a
first-class objective, with training signals that directly optimize row and column localization." (Sec. 5)

---------------------------------------------------------------------------------------------------

## 3. TraceBack (arXiv 2602.13059)

**Bibliographic line.** Tejas Anvekar*, Junha Park*, Rajat Jha*, Devanshu Gupta, Poojah Ganesan,
Puneeth Mathur, Vivek Gupta (Arizona State University; Adobe Research). "TraceBack: Multi-Agent
Decomposition for Fine-Grained Table Attribution." arXiv:2602.13059v1 [cs.CL], 13 Feb 2026.
Venue: **not stated** in the PDF or arXiv listing (not confirmed).
- URLs fetched: https://arxiv.org/pdf/2602.13059 (200), https://arxiv.org/abs/2602.13059 (200).

**Task / contribution.** All three: a method (TraceBack), a benchmark (CiteBench), a metric (FairScore).
- Task is *post-hoc* attribution with the answer as an input: "Given a natural-language question q and its
  answer a, we seek an attribution set A_T" (Sec. 4.1). The text calls it "a model-generated answer", but in
  the experiments the answers are the datasets' reference answers (ToTTo descriptions, FetaQA/AITQA answers).
- Method: five prompted agents - column relevance, row filtering via generated SQL conditions, query
  decomposition, sub-query cell attribution, final phrase-to-cell alignment (Sec. 4). "all methods use GPT-4o
  ... as the LLM" (Sec. 5); "TraceBack-Lite (uses Qwen2.5-7B-Instruct ... as LLM)" (Sec. 5.1).
  Whether the generated SQL is actually executed is implied (prompt asks for a MySQL CREATE TABLE statement,
  App. A Prompt B) but **not stated explicitly**.
- CiteBench (Table 2): ToTTo 7,700 (500 gold / 7,200 silver), FetaQA 3,004 (500 / 2,504), AITQA 513 (513 /
  none). The text says "1,500 manually annotated examples" although 500+500+513 = 1,513. Cohen's kappa 0.72
  on 250 instances. They also report label noise in the older TabCite sources: "error rates of 21.7% for
  ToTTo and 55.3% for FetaQA" (Sec. 3.1).
- Language: English only, stated: "CiteBench currently covers only English Wikipedia-style tables, so
  generalization to multilingual or domain-specific and more heterogeneous settings remains untested."
  (Limitations, p.10). No Korean.

**Attribution measured separately from answer correctness?** Attribution is measured in detail; **answer
correctness is not measured at all** (the answer is given). Hence no "answer correct but attribution wrong"
rate.
- Metrics (Table 3, p.6): precision = |S' ∩ S^| / |S'| and recall = |S' ∩ S^| / |S^| over predicted vs gold
  sets, computed at row, column and cell level.
- FairScore: "a reference-less metric that compares atomic facts derived from predicted cells and answers to
  estimate attribution precision and recall without human cell labels" (Abstract). On gold annotations it
  gives "83.20 precision and 88.34 recall" (Sec. 6.1); it underestimates true precision by ~16 points on
  ToTTo/FetaQA (Table 6).
- Headline cell-level numbers, Table 4 (Precision / Recall): TraceBack - ToTTo 74.20 / 67.05, FetaQA 89.81 /
  78.84, AITQA 52.37 / 95.22. Plain few-shot + CoT with GPT-4o - ToTTo 14.50 / 10.10, FetaQA 27.40 / 17.80,
  AITQA 02.20 / 04.30. TraceBack-Lite (7B) - 73.80 / 39.60, 75.40 / 42.30, 73.70 / 80.60.
- Also covers intermediate (implicit) evidence: cells "required for intermediate reasoning but not directly
  mentioned" (Sec. 4.1).

**Verifier / trust score / abstention?** No abstention, no answer gating. Model-based checks only:
"each generated fact is checked by a pretrained NLI model (RoBERTa ...)" inside query decomposition (Sec. 4),
and FairScore uses "a scoring LLM" for fact alignment (Sec. 6). Nothing rule-based that accepts/rejects an
answer.

**Training?** None. Few-shot prompting of GPT-4o / Qwen2.5-7B-Instruct; evaluation on 1,500 gold examples
plus silver sets via FairScore.

---------------------------------------------------------------------------------------------------

## 4. TabLaP (arXiv 2410.12846)

**Bibliographic line.** Yuxiang Wang, Jianzhong Qi, Junhao Gan (School of Computing and Information Systems,
The University of Melbourne). "Accurate and Regret-aware Numerical Problem Solver for Tabular Question
Answering." arXiv:2410.12846v4 [cs.CL], 15 Jun 2025 (v1: 10 Oct 2024).
- ID check: yes; "TabLaP" is the model name, not in the title.
- Venue: the PDF carries "Copyright (c) 2025, Association for the Advancement of Artificial Intelligence
  (www.aaai.org)", i.e. AAAI formatting. The arXiv listing has no comments/journal-ref, and a DBLP lookup
  was blocked (dblp.org: proxy CONNECT 403). AAAI-25 publication is therefore **likely but not confirmed**.
- URLs fetched: https://arxiv.org/pdf/2410.12846 (v4, 200), https://arxiv.org/abs/2410.12846 (200).

**Task / contribution.** Method for answer-only TableQA with emphasis on numerical questions.
- Datasets (Table 1): WTQ (11,321 train / 4,344 test), FTQ - their cleaned short-answer version of FeTaQA
  (2,000 / 1,245), and TabFact small (92,283 / 2,024). Language **not stated**; no Korean.
- Models: GPT-3.5 Turbo (NumSolver; GPT-4o mini on TabFact), Mix-SC as the second branch, and two LoRA
  fine-tuned Llama3-8B-Instruct modules.

**How numerical calculation is handled (Python execution: yes).**
- "uses LLMs as a planner rather than an answer generator. This approach exploits LLMs' capability in
  multi-step reasoning while leaving the actual numerical calculations to a Python interpreter" (Abstract)
- "When the Python-based answers are different from the LLM-generated ones, and they contain numerical
  values, priority is given to the Python-based answers. When errors occur during Python execution, the
  answers obtained directly from the LLM are used. This process is called self-correctness." (Answer
  Generation section)
- Two branches (Mix-SC and NumSolver); AnsSelector, "a fine-tuned Llama3-8B-Instruct", returns [A] or [B].
- The script is free-form LLM-written Python over values the LLM copied into lists (Fig. 1c, Fig. 3 prompt);
  there is no cell-reference format and no check that the numbers used come from the right cells.

**The "answer trustworthiness" component (TwEvaluator).** Model-based + online statistics, not rule-based.
- "TwEvaluator trains an LLM (a fine-tuned Llama3-8B-Instruct) ... It returns an answer of either [True] or
  [False], indicating whether TabLaP has answered the input question correctly." (Trustworthiness Evaluation)
- Two "rejection filters" on top: Expanding Window (EW) and "Multi-arm Bandits (MAB) with Upper Confidence
  Bound (UCB)", which decide whether to accept or reject the LLM's label based on its running accuracy over
  previous test instances (Eqs. 1-3).
- Its inputs exclude the table body: "they take the question, the table titles and headers but not the
  contents as input, together with the answers and reasoning process" (Experiments, label construction).
- Metric: "TwAccuracy is calculated as the number of times when the trustworthiness label is correctly
  predicted, divided by the total number of test instances." Regret: "Let the user regret ratio of a model be
  1 - TwAccuracy."
- Numbers (Table 5): Accuracy WTQ 76.6 / FTQ 44.1 (best baselines 72.5 Mix-SC, 41.7 GPT-4o; the "+5.7%" and
  "+5.8%" are relative gains). TwAccuracy 77.9 / 53.7 (MAB), 77.6 / 53.8 (EW). TabFact small: accuracy 90.4,
  TwAccuracy 90.0 (Table 7). Regret 22.1% / 46.3% vs 27.5% / 58.3% for best baselines ("19.6% and 20.6%
  lower", relative).
- Not reported: precision/recall of the trust label, false-reject rate, or accuracy restricted to trusted
  answers (searched: precision, recall, F1 - none). My own arithmetic, not in the paper: on WTQ TwAccuracy
  (77.9) is only 1.3 points above the "always trust" rate (76.6 = TabLaP's own accuracy); on FTQ an
  "always distrust" labeller would score 55.9, above the reported 53.7.
- Abstention: none in the system. The answer is always returned with a label: "users can follow the
  trustworthiness labels to either consume or reject our models' answers" (Results, Q2).
- Novelty claim made by the authors: "we further make a first attempt to quantify the trustworthiness of the
  answers produced by TabLaP" (Abstract).

**Cell/row/column attribution?** **None.** No attribution, citation or evidence-cell metric; evaluation is
"exact-match answer Accuracy". Nothing like "answer correct but attribution wrong".

**Training?** Yes, but only for the selector and the trust classifier: "We adopt Low-Rank Adaptation (LoRA)
... to fine-tune our AnsSelector and TwEvaluator with Llama3-8B-Instruct" (r = 16, lora alpha = 64, LR 2e-4,
up to 20 epochs; Table 6). The answer generators are not trained.

---------------------------------------------------------------------------------------------------

## What TableTrace must NOT claim as new given these papers

1. That answer correctness and cell-level attribution correctness are different capabilities / that models
   answer correctly more often than they cite correctly. ViTaB-A states this as its main finding (QA 55% vs
   attribution 26% on Markdown, 0.9% on JSON, 4B models); TraceBack opens with the same motivation.
2. Measuring attribution at cell, row and column granularity against gold evidence cells (ViTaB-A accuracy /
   P / R / F1; TraceBack P / R; both cite earlier MATSA / TabCite).
3. That small or plainly prompted models are poor at cell citation (ViTaB-A 2B-8B models; TraceBack's
   few-shot + CoT GPT-4o baseline at 14.5 / 10.1 cell P / R on ToTTo).
4. That a model's own confidence is not a usable check on its citations (ViTaB-A Sec. 4.4-4.5).
5. Moving arithmetic out of the LLM into executed code (TabLaP's Python interpreter; it in turn cites
   Binder, LEVER, PAL).
6. Being first to attach a trust/"regret-aware" signal to TableQA answers (TabLaP claims that in 2024), or to
   use a LoRA-tuned small open model as part of a TableQA pipeline (TabLaP, Llama3-8B).
7. Deterministic, training-free, rule-computed quality signals for table reasoning, or using such a signal as
   an RL reward for an 8B model (RE-Tab: TabROUGE, GRPO on Qwen3-8B).
8. Attribution that includes intermediate cells used in a calculation, not just cells whose text appears in
   the answer (TraceBack's "implicit" cells).
9. The idea that attribution should be trained for directly - ViTaB-A names it as future work, so TableTrace
   answers that call rather than originating it.

## What still looks different (and how confident)

Confidence refers to these four papers only (full text checked); I did not survey other literature.

1. A per-instance conditional rate - among answers whose text is correct, the share whose cited cell is
   wrong - for a system that produces answer and citation together. None of the four reports it. ViTaB-A
   gives only marginal QA vs attribution accuracy and supplies the gold answer for the attribution task;
   TraceBack never scores answers; RE-Tab and TabLaP have no attribution. Confidence: high. Caveat: ViTaB-A's
   gap figures are therefore not directly comparable with TableTrace's 53% / 65% / 1-2%.
2. A rule-based verifier that re-executes the cited cells and gates the answer, with abstention. None of the
   four abstains. TabLaP's trust label is a learned LLM + bandit that never sees table contents; RE-Tab's
   signal is lexical and explicitly "not ... an absolute correctness verifier"; TraceBack uses NLI / LLM
   judges; ViTaB-A only measures confidence. Confidence: high.
3. "Verified exact match" (answer counted only when the verifier accepted it) and abstain recall / false
   abstain rates. Not reported in any of the four; TabLaP's single TwAccuracy number is the nearest thing and
   it reports no precision/recall of the label. Confidence: high.
4. Showing that fine-tuning changes attribution correctness (53-65% wrong-cell down to 1-2%). None of the
   four trains for attribution: ViTaB-A and TraceBack are prompting-only, TabLaP fine-tunes a selector and a
   trust classifier, RE-Tab's GRPO is judged on answer accuracy. Confidence: high for these four; medium that
   it is new overall.
5. Korean / bilingual evaluation. No Korean or other non-English data in any of the four (TraceBack says
   English only; the other three do not state a language and the word "Korean" never occurs). Confidence:
   high that none covers Korean.
6. Model scale: a 1.2B model is below everything evaluated here except ViTaB-A's Qwen3-VL-2B; the trained
   models in TabLaP and RE-Tab are 8B. Confidence: medium-high (a minor differentiator).
7. A structured program output with explicit cell references (`op / cells / answer`) that tools re-execute.
   TabLaP executes free-form Python with values copied by the LLM; TraceBack attributes after the fact;
   RE-Tab executes table tools but cites nothing. Confidence: medium (program-based TableQA in general is
   old; only the cited-cell re-execution check looks distinct among these four).

## Not confirmed / caveats

- Venues: RE-Tab ("Preprint.", NeurIPS checklist attached), ViTaB-A ("Under review" for an ICLR 2026
  workshop), TraceBack (none stated), TabLaP (AAAI 2025 copyright footer only; dblp.org blocked with 403).
- ViTaB-A: exact definition of "cell-level accuracy" and the QA evaluation protocol are not in the paper.
- Languages for RE-Tab, ViTaB-A and TabLaP are not stated in the papers.
- RE-Tab appendices B-G (from p.18 of 50) were keyword-searched, not read line by line, except F.1.2, G.3, G.6.
- TraceBack: SQL execution in the row-filtering agent is implied, not stated; "1,500" gold examples vs 1,513
  in Table 2; Table 6 lists TraceBack ToTTo precision as 74.52 while Table 4 says 74.20.
