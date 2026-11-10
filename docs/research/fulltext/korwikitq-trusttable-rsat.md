> 이 메모는 2026-11-10에 AI 조사 에이전트가 각 논문의 PDF 전문을 내려받아 읽고 쓴 것이다. 인용문은 원문 그대로이고, 확인하지 못한 것은 NOT CONFIRMED / Not confirmed로 표시되어 있다. 저장소 작성자가 핵심 인용 20여 개를 원문 텍스트에서 다시 찾아 대조했다. 요약과 이 프로젝트와의 관계는 `docs/REPORT.md` §19.4와 `docs/research/papers.md`에 있다.

# Full-text verification notes: KorWikiTQ, TrustTable, RSAT

Checked 2026-11-10 from downloaded full text (PDF -> `pdftotext`), not from abstracts or snippets.
Quotes are verbatim; line-break hyphens of the two-column PDFs were joined. "p." = PDF page of the file fetched.
Anything marked **NOT CONFIRMED** could not be established from the full text.

The PDFs themselves are not stored in this repository; the URLs fetched are listed per paper.

---

## 1. KorWikiTQ paper

**Bibliographic line.** Changwook Jun, Jooyoung Choi, Myoseop Sim, Hyun Kim, Hansol Jang, Kyungkoo Min.
"Korean-Specific Dataset for Table Question Answering." *Proceedings of the Thirteenth Language Resources and Evaluation
Conference (LREC 2022)*, Marseille, France, June 2022, pp. 6114-6120, European Language Resources Association.
ACL Anthology id `2022.lrec-1.657`. arXiv:2201.06223 (v2, 1 May 2022; first submitted 17 Jan 2022).
Affiliation (all six authors): "LG AI Research", Seoul (title block, p.1).

**URLs actually fetched (HTTP status).**
- https://arxiv.org/pdf/2201.06223 (200, 7 pages) and https://arxiv.org/abs/2201.06223 (200)
- https://aclanthology.org/2022.lrec-1.657.pdf (200) and https://aclanthology.org/2022.lrec-1.657.bib (200); venue/pages come from the .bib
- https://raw.githubusercontent.com/LG-NLP/KorWikiTableQuestions/main/README.md (200; `master` returns the identical file)
- https://github.com/LG-NLP/KorWikiTableQuestions (**403** from the proxy; HTML repo page not reachable) and
  https://api.github.com/repos/LG-NLP/KorWikiTableQuestions/contents/ (**400**), so the repo file listing was not seen.
- Hugging Face API searches, see below.

The arXiv v2 text and the LREC PDF give the same split sentences and the same Tables 1-3 (checked by grep on both).

**Correction to the brief: the model is not TAPAS-style.** The model is "KO-TaBERT": BERT-Base pre-trained with MLM on
tables linearised into sentence strings, fine-tuned as SQuAD-style span extraction. TAPAS is only cited as related work.
- "The conversion formats play a crucial role for models to learn table structural information effectively without changing embeddings." (Sec. 1, p.1)
- "the fine-tuning model aims to predict the correct span of an answer defined as a start and end boundaries for a given question." (Sec. 4.2, p.4-5)
- "BERTBase model is adopted in our experiments ... but the NSP objective is not used." (Sec. 4.1, p.4)

**How the dataset was built.**
- Two datasets. KorWikiTabular (pre-training): "We collect about 1.4M tables (T) from the Korean Wikipedia dump" (Sec. 3.1, p.2); infoboxes and wikitables with article title / first paragraph / captions / headings as description.
- KorWikiTQ (QA): human-written by paid crowd workers, not automatic question generation.
  "we create a large dataset consisting of 70k pairs of questions and answers by hiring paid, crowdsourced workers. We select about 20k tables that contain rows greater than 5 and less than 15 for this crowdsourcing task." (Sec. 3.2, p.3)
  "Larger tables including columns greater than 10 are ignored" (Sec. 3.2, p.3).
- Workers write five question types by difficulty (Level1-Level5; Level4 = paraphrase variations, Level5 = min/max style). "Our crowd-sourced workers generate the five types of natural language questions for a given table." (Sec. 3.2, p.3)
- Record format: "table contexts (C) in the form of two-dimensional lists, natural language questions (Q), and answers (A), along with URLs (U) and titles (T) of Wikipedia documents where tables are contained." (Sec. 3.2, p.4)

**Sizes.**
- In the paper: only "70k pairs" and "about 20k tables". The paper gives **no exact counts and no absolute train/dev/test sizes**.
- In the GitHub README ("Dataset Overview" table): Total 69,992 / Train 58,221 / Dev 11,771 examples. The README lists Train and Dev only (no test file is mentioned).

**How the split was made.** The only statements are:
- "We split the selected KorQuAD 2.0 corpus and the crowdsourced dataset with a 20% ratio respectively as the test dataset for evaluation. The rest of the data is used for fine-tuning training." (Sec. 4.2, p.4-5)
- "we create the test dataset that includes around 10k question-answer pairs related to tables in Korean Question Answering Dataset (KorQuAD 2.0), and 20% splits of the crowdsourced dataset." (Sec. 1, p.2)
- "We evaluate our model on the test dataset consisting of the subsets from the KorQuAD 2.0 and the crowdsourced table question-answering datasets, which are not used during the training of the model." (Sec. 4.3, p.5)

**The paper says nothing about the unit of the split** (by question at random vs. by table / by document) and **nothing about
tables being shared, or not shared, across splits.** No word such as "random", "unseen", "overlap" or "shared" occurs in connection
with the split. So "split by question" is **NOT CONFIRMED** from the paper; it is an inference from the released files.

Two things in the paper/README that do not line up (worth knowing before quoting them):
- KorQuAD 2.0 part: Sec. 1 says "around 10k question-answer pairs", Sec. 4.2 says "about 2k pairs of questions and answers related to tables selected from KorQuAD 2.0 corpus".
- README Dev = 11,771 of 69,992 = 16.8%, not 20%. Whether the released "Dev" file is the paper's 20% "test dataset" is **NOT CONFIRMED** (the paper never uses the word "dev"; the README never uses "test").

**Metric and headline numbers.** EM and F1: "Exact Match (EM) scores if each character of a predicted answer is exactly the same as the ground truth and F1-score (F1) that calculates token overlaps" (Sec. 4.3, p.5). Model: KO-TaBERT.
- Table 1 (p.5): KorQuAD 2.0 EM 64.5 / F1 74.5; Crowd-sourced EM 83.9 / F1 87.2; Overall EM 82.8 / F1 86.5.
- Table 2 (p.5), crowdsourced part by level: L1 89.6/93.1, L2 89.1/92.3, L3 86.1/89.4, L4 81.7/85.5, L5 67.8/70.6.
- Table 3 (p.5), second table-conversion format "v2": KorQuAD 2.0 69.1/78.4; Crowd-sourced 87.2/91.2.
- No evidence-cell / attribution metric, no abstention, no unanswerable questions anywhere in the paper.

**Hugging Face dataset card.** No dataset repository for KorWikiTQ was found.
- `https://huggingface.co/api/datasets?search=<q>` returned 0 results for korwikitq, KorWikiTQ, KorWikiTableQuestions, kor_wikitq, ko-wikitq, KorWikiTabular, ko-tabert, LG-NLP (all HTTP 200, empty list).
- `https://huggingface.co/api/search/full-text?q=KorWikiTQ&type=dataset` (200): the only card that actually mentions it is
  https://huggingface.co/datasets/HAERAE-HUB/HAE-RAE-COT-1.5M , which lists KorWikiTQ (8,276 derived samples, link to the LG-NLP GitHub repo) as a source. It says nothing about the KorWikiTQ split.
- Guessed ids (LG-NLP/KorWikiTQ, LG-NLP/KorWikiTableQuestions, LGAI-EXAONE/KorWikiTQ, lgresearch/KorWikiTQ) all returned 401 (HF's answer for a repo that does not exist or is private).
- These searches are not exhaustive; a mirror under an unrelated name cannot be ruled out.
- GitHub README (the only "card" found): describes the split only by the count table above; no description of how it was made and nothing about shared tables.

---

## 2. TrustTable

**Bibliographic line.** Guangzhen Zhao, Dechang Kong, Tongyu Wu, Zhenjiang Dong. "TrustTable: A Neuro-Symbolic Auditing
Framework for Faithful Table QA." *Proceedings of the 64th Annual Meeting of the Association for Computational Linguistics
(Volume 1: Long Papers)*, San Diego, July 2026, pp. 34907-34934. DOI 10.18653/v1/2026.acl-long.1612.
Affiliations: School of Computer Science, Nanjing University of Posts and Telecommunications; The State Key Laboratory of Tibetan Intelligence, China.

**URLs fetched.** https://aclanthology.org/2026.acl-long.1612.pdf (200, 28 pages) and `.bib` (200). The anthology id in the brief is correct.

**Task and contribution: both a method and a benchmark.**
- Method: a post-hoc auditor for LLM chain-of-thought in table QA. An LLM decomposes the CoT into atomic steps; "fact" steps become LLM-written Pandas checks run against the table (FactChecker), "inference" steps become LLM-written Z3 constraints (LogicAuditor), a Consistency Monitor compares executed vs. stated answer; a REJECT feeds a "Label-Free Audit Loop" (at most K = 3 refinements).
  "It enforces factual grounding by executing neurally generated Pandas code against the table, and ensures logical soundness by verifying reasoning chains through a LLM-synthesized formal solver." (Abstract, p.1)
- Benchmark: "TrustTable-Bench ... contains 12,000 samples evenly distributed across four reasoning categories" (Sec. 5.1, p.6); 2,000 seeds x 6 generated variants (App. B.2, p.14), seeds from 1,592 tables (Table 8, p.14). Reasoning chains are synthetic: "reasoning chains are produced by general-purpose LLMs (GPT-5)" (Sec. 3, p.3).

**Does it separate reasoning/evidence correctness from answer correctness? Yes, at the level of the reasoning chain.**
Four quadrants (Sec. 3, p.4; App. A.1, p.13): Type 1 Faithful (Z+ A+), Type 2 Spurious (Z- A+), Type 3 Fallacious (Z- A-), Type 4 Inconsistent (Z+ A-).
- "Type 2: Spurious (Z- ∧ A+): Hallucinated logic (Z-) accidentally yielding correct answers." (Sec. 3, p.4)
- One of three Type 2 sub-modes is exactly wrong evidence with a right answer: "Grounding Error (Z-ground): The model reaches the correct answer but cites irrelevant cells or non-existent columns." (App. B.2, p.14). The other two are Calculation Error and Logic Error.
- It checks cited values against cells: "every quantity the CoT cites (here, "20") is compared against the actual cell value (12), and the mismatch is reported regardless of whether the downstream conclusion happens to be correct." (Sec. 5.2.2, p.8)
- But the model under audit writes free-text CoT; there are **no explicit cell coordinates / cell ids** (the word "coordinate" does not occur), and there are no gold evidence cells.

**Anything equivalent to "answer correct but cited cells wrong" as a conditional rate? Yes, two things, both loosely specified.**
1. Natural incidence among correct answers: "Our preliminary analysis identifies a non-trivial incidence of reasoning hallucinations, affecting approximately 5% of correct predictions (see hallucination rate, Figure 1, top-right)." (Sec. 1, p.2).
   Figure 1 (top, p.1) plots accuracy and "Hallucination Rate (%)" for DeepSeek-V3, Gemini-3-flash and GPT5-mini on WTQ, Fin, Med, Pubhtab, Tabfact; right axis 0-6%. The values exist only in the figure: read off my render they lie between roughly 1% and 5% (approximate chart reading, not numbers printed in the paper). How this rate was measured (annotator, sample size) is **NOT CONFIRMED**: the paper does not describe it.
2. "Spurious Acceptance Rate (SAR)" in Table 2 (p.8), for a fine-tuned Qwen2.5-7B on WTQ: outcome-filtered training data Acc 64.7 / SAR 12.5 / FP 63.2; TrustTable-filtered data (72% of the data) Acc 68.1 / SAR 5.2 / FP 81.4. SAR is named but never formally defined (its denominator is **NOT CONFIRMED**).
   This rate covers all wrong reasoning (grounding + calculation + logic), not only wrong cited cells.

**Metric names, definitions (Sec. 5.1 p.6; App. A.1 p.13; Table 7 p.14).** These score the auditor's accept/reject decisions on the benchmark:
- VCAR, Verified Correct Answer Rate: fraction of Type 1 samples that are accepted. "it penalizes correct answers derived from incorrect logic (Type 2), counting only rigorously verified correct samples" (App. A.1).
- DIR, Diagnostic Interception Rate: "the recall of the verifier on specific error subsets"; DIR_spur = rejection rate on Type 2, DIR_inc = rejection rate on Type 4.
- FP, Faithfulness Precision: "the conditional probability that an accepted sample is genuinely faithful" = Type 1 accepted / all accepted.
- CSR, Correction Success Rate: "the fraction of initially rejected reasoning chains that are successfully revised into valid, grounded traces" (Sec. 5.2.3, p.8-9).

**Headline numbers.**
- Table 1 (p.7), TrustTable row, VCAR / DIR_spur / DIR_inc / FP: Finance 78.5 / 94.8 / 98.8 / 84.7; Medical & Public Health 83.7 / 94.3 / 96.0 / 81.3; Open Domain (WTQ) 76.6 / 92.9 / 97.2 / 82.6. Standard CoT on WTQ: 76.5 / 83.8 / 65.5 / 45.2. "TrustTable yields the highest FP across all domains, averaging 82.9%" (Sec. 5.2.1, p.7).
- Table 5 (p.9), WTQ test accuracy: Greedy CoT 80.1%, SC k=5 82.7%, SC k=10 83.2%, TrustTable 83.4% at 5.80 average API calls.
- Table 6 (p.9), agreement with three human experts on 200 chains: TrustTable 93.5%, Cohen's kappa 0.86; LLM Self-Check 88.6% / 0.74.
- Table 3 (p.8): CSR 48.4% with symbolic feedback vs 34.1% blind retry.
- Table 10 (p.15): with plain prompting, "Type 2 detection saturates near 85% across all configurations" and FP "peaks at 70.2% (GPT-5-mini + PoT)".
- Benchmark QA: 10% sample (1,200) re-annotated by four graduate students, "96.5% validity rate ... (Fleiss' kappa = 0.88)" (Sec. 3 p.4; Table 9 p.15).

**Abstention / unanswerable questions / verifier.**
- Verifier: yes, it is the core of the paper. It is hybrid (the paper's word is "neuro-symbolic"), **not a fixed rule set**: the checking programs are written by an LLM per claim and then executed deterministically. The paper's own leakage analysis attributes about 40% of misses to this translation step: "The Program Synthesizer occasionally generates code that is syntactically valid and fully executable, yet semantically flawed." (App. G.2, p.20); about 48% to fuzzy matching (App. G.1).
- Gating: "ensuring that no answer is accepted unless its reasoning path is mathematically provable and factually anchored." (Sec. 1, p.2)
- Abstention: the words "abstain", "abstention", "unanswerable" do not occur. A REJECT triggers repair, not abstention. What the system outputs if a chain is still rejected after K = 3 iterations is **NOT CONFIRMED** (not stated). No unanswerable questions in the benchmark.

**Languages, datasets, model sizes.**
- Datasets: WTQ; a finance and a medical subset of the dataset of Zhang et al. 2025 (spelled "SciAutomic", "SciAtomic" and "ATOMIC" in different places); PubHealthTab (Table 8, p.14). Table 1 labels the panels "Finance (FinQA)" and "Medical & Public Health (MedQA + PubHealthTab)", which does not match Table 8; Figure 1 also shows TabFact.
- Language: never stated. "Korean", "multilingual", "English", "Chinese" do not occur in the text. No Korean data. (The named benchmarks are English ones; that is background knowledge, not a statement in the paper.)
- Models: DeepSeek-V3 backbone (Sec. 5.1, p.7); GPT-5 as benchmark generator; Gemini-3-flash and GPT-5-mini in Fig. 1 / Table 10; the only small open model is the Qwen2.5-7B student. No model below 7B.

**Training or evaluation only?** Mostly inference-time auditing and evaluation. One training experiment: rejection-sampling fine-tuning (RFT) that keeps only verifier-approved trajectories: "distill symbolic rigor from a teacher (DeepSeek-V3) into a student (Qwen2.5-7B)" (Sec. 5.2.1, p.8; App. D, p.17). This is supervised fine-tuning on filtered data. **No RL** (the conclusion's phrase "Dense Process Rewards" refers to this RFT filter). LoRA is not mentioned.

**Stated limitations (p.10).** Deterministic reasoning only; "TrustTable operates on flattened 2D DataFrames" and may degrade on hierarchical tables with merged cells.

---

## 3. RSAT

**Bibliographic line.** Jugal Gajjar, Kamalasankari Subramaniakuppusamy (Department of Computer Science, The George Washington
University). "RSAT: Structured Attribution Makes Small Language Models Faithful Table Reasoners." arXiv:2605.00199v2 [cs.CL],
7 May 2026 (v1 30 Apr 2026). arXiv comment field: "Accepted at the SURGeLLM Workshop at ACL 2026 and will be included in the
proceedings". The workshop-proceedings entry itself was not looked up (**NOT CONFIRMED** in the Anthology).

**URLs fetched.** https://arxiv.org/pdf/2605.00199 (200, 13 pages) and https://arxiv.org/abs/2605.00199 (200).

**What RSAT stands for.** "RSAT (Reinforcement-driven Structured Attribution Training)" (Sec. 1, p.1).

**Task and contribution: a training method, no new benchmark.** Small models are trained to emit JSON with reasoning steps, each carrying cell coordinates, plus an answer.
- "each reasoning step explicitly cites the table cells it depends on using [row, col] coordinates." (Sec. 1, p.1)
- Phase 1 SFT on 1,000 traces generated by Claude Opus 4.5 and checked only structurally; Phase 2 GRPO.
- Novelty claim: "To our knowledge, RSAT is the first application of RL-driven attribution training to structured table reasoning." (Sec. 2, p.2)

**Reward / training signal (Sec. 3.5, p.4; App. C, p.11).** "R = Rans + λ1 Rcite + λ2 Rfaith + λ3 Rpars + Rfmt" with λ1 = 0.3, λ2 = 0.5, λ3 = 0.2.
- Rans: "Token-level F1 between the predicted and gold answer."
- Rcite (citation validity): "Fraction of cited cell coordinates [ri, cj] that fall within the table's dimensions". This is a bounds check, not correctness of the citation.
- Rfaith: "we concatenate the values of the cited cells into an evidence string and compute the entailment probability against the step's text using DeBERTa-v3-base NLI".
- Rpars: full score at <= 3 cited cells per step, linear decay to 0 at >= 8. "This prevents reward hacking through exhaustive citation of all cells."
- Rfmt: "-1 if the output fails JSON parsing, 0 otherwise."
- GRPO: G = 8 candidates, temperature 0.9, one epoch over 500 examples (250 steps), fresh LoRA adapter on the merged SFT checkpoint (Sec. 3.4, p.4).

**Cell-level citation with verification?** Cell-level citation: yes. Verification: only a coordinate bounds check and a learned NLI score.
There is no program re-execution, no gold evidence cells, no check that the cited cells support the final answer, and no accept/reject step at inference
(the word "verifier" does not occur). Verification is left to the reader: "a user can independently verify each claim by checking the cited cells against the original table." (Sec. 3.1, p.3)
The authors flag the proxy themselves: "The model may learn to produce text that scores well on DeBERTa specifically rather than achieving genuine grounding." (Sec. 6, p.8); "A human evaluation study is needed to validate the NLI proxy." (Sec. 6, p.8)

**Attribution measured separately from answer correctness? Yes as separate columns; no conditional rate.**
Six metrics (Sec. 4, p.4-5): Faithfulness (NLI, primary), Answer F1, Citation Validity, Parsimony, Format Success, Answer EM.
Nothing equivalent to "answer correct but cited cells wrong" is reported; faithfulness is never conditioned on answer correctness.
(EM is "uniformly low values (0.000-0.018)" per Table 2 caption, so a "correct answers" subset is not even used.)
The closest statement is from the ablation without the faithfulness reward: "the model learns to produce perfectly formatted, parsimonious outputs that cite real cells—but the citations are essentially random." (Sec. 5.4, p.7), while F1 stays at 0.635.

**Headline numbers.**
- "RSAT improves faithfulness by 3.7x over SFT alone (0.224→0.826 average across all models), while maintaining near-perfect citation validity (0.992) and format compliance (0.993)." (Sec. 1, p.1)
- Table 2 (p.6), RSAT rows, F1 / Faith: Qwen 1.5B 0.524 / 0.847; Qwen 3B 0.592 / 0.946; Qwen 7B 0.619 / 0.977; Llama 1B 0.537 / 0.480; Llama 3B 0.592 / 0.735; Llama 8B 0.647 / 0.972. SFT-only faithfulness 0.149-0.288.
- Table 3 (p.6): Zero-shot→SFT +0.61 format, +0.64 citation validity, +0.19 faithfulness, +0.34 F1; SFT→RSAT +0.60 faithfulness, +0.09 F1.
- Post-hoc (answer first, cite afterwards) baseline: "Average format success is just 12.7%" (Sec. 5.3, p.5).
- Table 4 (p.7) ablations: without faithfulness reward 0.977→0.117 (Qwen 7B) and 0.972→0.031 (Llama 8B); without parsimony reward parsimony 0.992→0.604 and 1.000→0.575.

**Reward gaming reported in the paper (relevant to TableTrace point c).**
- Over-citation is anticipated and blocked by the parsimony term (quote above), and shown in the ablation: "models default to citing 5-6 cells per step rather than 1-2." (Sec. 5.4, p.7)
- Without the NLI term: "The model games the remaining rewards without grounding its reasoning." (Sec. 5.4, p.7)
- Possible over-compression of the trained policy, left open: "with some models converging to 1.0 reasoning step per output. Whether this represents optimal conciseness or over-compression warrants further investigation." (Sec. 6, p.8). Figure 4 (p.7) shows RSAT steps whose whole text is "Row 1." with one cited cell; the paper presents this as good attribution (that this looks degenerate is my reading, not the paper's).
- Train-eval circularity: "Faithfulness is both the training reward and the primary evaluation metric, both scored by the same DeBERTa NLI model." (Sec. 6, p.8)

**Abstention / unanswerable / verifier.** None. "abstain", "abstention", "unanswerable" do not occur. No rule-based verifier; the only programmatic checks are structural checks on the SFT traces, and the paper says they do "not guarantee semantic grounding between cited cells and reasoning steps" (Sec. 3.2, p.3).

**Languages, datasets, model sizes.** WTQ, FeTaQA, TabFact (Sec. 3.2; Table 1, p.3: 1,000 SFT examples + 74,397 GRPO-pool examples = 75,397). Language never stated; "Korean" and "multilingual" do not occur. Models: "Qwen 2.5 Instruct (1.5B, 3B, 7B) ... and Llama 3 Instruct (1B, 3B, 8B)" (Sec. 4, p.4), all with LoRA on one H100, 36.8 GPU-hours in total.

**Training or evaluation only?** Training: LoRA SFT, then RL (GRPO). Evaluation on "500 held-out examples from the combined WTQ/FeTaQA/TabFact test split using greedy decoding" (Sec. 4, p.4). No human evaluation. How tables are distributed across the train/test pools is not discussed.

---

## Overlap with TableTrace / what TableTrace must not claim as new

- **(a) "Right answer, wrong evidence" is an established, named and measured phenomenon.** TrustTable is built around it ("Right Answer & Wrong Reason", Type 2 = Z- ∧ A+, with a sub-type where the model "cites irrelevant cells"), reports a natural rate conditioned on correct answers ("approximately 5% of correct predictions") and a Spurious Acceptance Rate for a fine-tuned 7B model (12.5% → 5.2%). TableTrace must not present the metric idea, or the observation that answer accuracy hides wrong evidence, as new. RSAT makes the adjacent point that format-valid citations are not grounded citations (SFT: ~99% citation validity, ~22% faithfulness).
- **Gating an answer on an executed check against the table is not new.** TrustTable executes Pandas/Z3 checks and accepts an answer only when they pass.
- **Training a small model with SFT then RL to emit cell-level citations, with a reward containing citation terms, is not new.** RSAT does this with LoRA for 1-8B models and claims to be the first RL-driven attribution training for table reasoning. EXAONE-4.0-1.2B sits inside RSAT's size range, so "small model" alone does not differentiate.
- **(c) A citation reward being gamed is not a new kind of finding.** RSAT names "reward hacking through exhaustive citation of all cells", adds a parsimony term against it, and shows by ablation that the model "games the remaining rewards". TableTrace's episode is a further case report with its own degenerate output and fix.
- **Using a verifier to filter training data** (if TableTrace does it) overlaps with TrustTable's rejection-sampling fine-tuning.
- **(b) Wording about the KorWikiTQ authors.** The paper does not say how the split was made, so TableTrace can report that the paper and README are silent and that the released files share tables, but must not state as fact that the authors split by question at random, and must not attribute a "dev/test" structure to the paper: the paper speaks of a 20% "test dataset" (plus a KorQuAD 2.0 part), the README lists only Train 58,221 / Dev 11,771 (16.8%), and their identity is not confirmed. Note also that in `scripts/data/profile_korwikitq.py` the 1,755 figure counts Wikipedia article URLs (field `U`) present in both files; the same script's count by qid prefix is 1,554. An article can hold more than one table, so "1,755 shared tables" is strictly "1,755 shared source pages".

## What still looks different

Stated only relative to these three papers (a "first" claim would need a wider search than this):
- **Korean.** Neither TrustTable nor RSAT has any Korean or non-English data, and the KorWikiTQ paper evaluates only EM/F1 with no evidence, attribution, abstention or unanswerable component. A cited-cell correctness measurement on Korean table QA does not appear in any of the three.
- **Measurement of (a) against a gold cell on natural outputs of very small models, before and after training.** TableTrace compares an explicit cited cell id with the gold cell on lookup questions and reports 53% / 65% for weak models versus 1-2% after training. TrustTable's natural-incidence number is for large API models, appears only in a figure with no described procedure, and covers all reasoning errors; its tabled numbers are detection rates on GPT-5-generated chains. RSAT has no gold cells and no conditional rate; its faithfulness is an NLI proxy with acknowledged train-eval circularity.
- **Verifier type.** TableTrace's verifier is a fixed rule set over a re-executed program with explicit cell ids, with no LLM in the verification path. TrustTable's checks are LLM-written per claim (its own analysis attributes ~40% of leakage to that translation step and ~48% to fuzzy matching); RSAT has no inference-time verifier at all.
- **Abstention as an outcome, and unanswerable questions.** Neither TrustTable nor RSAT has them (TrustTable repairs and retries; RSAT always answers).
- **Table-disjoint re-split of KorWikiTQ with a measured overlap in the released files.** Not discussed in the KorWikiTQ paper or README, nor in the other two papers.
- **Program output format** (`op / cells / answer` re-executed by tools) differs from TrustTable's free-text CoT audited after the fact and from RSAT's step-wise JSON citations judged by NLI.
