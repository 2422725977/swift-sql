"""Update Hugging Face Model Cards (README.md) for SwiftSQL-3B-GGUF & SwiftSQL-3B-LoRA without re-uploading weights."""

from __future__ import annotations

import getpass
import os
from pathlib import Path

from huggingface_hub import HfApi

GGUF_REPO_ID = "xiain/SwiftSQL-3B-GGUF"
LORA_REPO_ID = "xiain/SwiftSQL-3B-LoRA"

MODEL_CARD_TEMPLATE = """---
license: apache-2.0
base_model: Qwen/Qwen2.5-Coder-3B-Instruct
language:
  - en
  - zh
pipeline_tag: text-generation
tags:
  - text-to-sql
  - sql
  - gguf
  - qwen2.5-coder
  - dpo
  - rpo
  - postgresql
  - mysql
  - sqlite
  - ollama
  - llama-cpp
  - apple-silicon
datasets:
  - gretelai/synthetic_text_to_sql
  - trl-lab/SQaLe-text-to-SQL-dataset
  - jtjt520j/CSpider_and_DUSQL_sql_create_context
---

# ⚡ SwiftSQL-3B ({variant_label})

**SwiftSQL-3B** is a fast, accurate, bilingual (**English & Chinese**), multi-dialect (**PostgreSQL / MySQL / SQLite**) lightweight Text-to-SQL model fine-tuned from [`Qwen/Qwen2.5-Coder-3B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct) via **SQLite-sandbox-verified SFT + RPO-stabilized Iterative Execution-Guided DPO (`rpo_alpha=0.5`)**.

Built specifically to run comfortably on **16GB Apple Silicon (Mac mini / MacBook)** and consumer GPUs, while powering production Text-to-SQL APIs with **anti-hallucination refusal** and **1-shot SQL self-repair**.

- **GitHub Repository (Training Pipeline, Benchmarks & FastAPI Guardrail Gateway)**: [github.com/2422725977/swift-sql](https://github.com/2422725977/swift-sql)
- **GGUF Quantized Weights**: [`xiain/SwiftSQL-3B-GGUF`](https://huggingface.co/xiain/SwiftSQL-3B-GGUF)
- **LoRA Adapter Weights**: [`xiain/SwiftSQL-3B-LoRA`](https://huggingface.co/xiain/SwiftSQL-3B-LoRA)

---

## ✨ Key Advantages / 核心优势

1. **+10.73% Execution Accuracy over Base 3B**: Reaches **70.15% EX** (with 1-shot repair) vs **59.42%** for Base 3B on held-out multi-dialect execution evaluation.
2. **Industry-Leading Anti-Hallucination Refusal (`98.77%` F1)**: Explicitly returns `"answerable": false` with missing column names instead of fabricating fake columns — outperforming Base-3B (`67.69%`), XiYanSQL-3B (`9.52%`), and Arctic-R1-7B (`0.00%`) in fair head-to-head testing.
3. **4.6× Faster & 5.7× Fewer Tokens than 7B CoT Models**: Auto-Think skips verbose Chain-of-Thought on simple/single-JOIN queries (`98.9` vs `566.3` avg output tokens; `13.8×` higher batch throughput vs `Arctic-Text2SQL-R1-7B`).
4. **Native Multi-Dialect & Bilingual (EN/ZH)**: Directly accepts standard `CREATE TABLE` DDL (no custom schema converter needed) and targets `postgresql`, `mysql`, or `sqlite` with **100% strict JSON** compliance.
5. **Single-Model Generate + 1-Shot Self-Repair + 16GB Apple Silicon Ready**: `Q8_0` (3.06 GB) and `Q4_K_M` (1.80 GB) run smoothly on 16GB Mac mini with built-in `repair_sql` mode.

---

## 📊 Benchmarks / 实测评测

### 1. Held-Out Multi-Dialect & Refusal Progression (`opt2`, 300 Samples)

| Metric | Base-3B | V1 SFT *(Sandbox-Cleaned)* | V2 R1 *(RPO-DPO)* | **V2 R2 *(Exported)*** | **Best + 1-Shot Repair** | Δ vs Base |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Execution Accuracy (EX)** | 59.42% | 67.63% | 71.28% | **69.15%** | **70.15%** | **+10.73%** |
| **Refusal F1 (Anti-Hallucination)** | 0.00% | 80.00% | 67.35% | **90.41%** | **90.41%** | **+90.41%** |
| **Strict JSON Compliance** | 100.0% | 100.0% | 100.0% | **100.0%** | **100.0%** | — |
| **Multi-Dialect Syntax Valid** | 99.63% | 100.0% | 88.01% | **97.38%** | **97.38%** | — |
| **Avg Output Length (chars)** | 177.9 | 222.3 | 210.5 | **216.6** | **217.3** | Compact |

### 2. Head-to-Head Public Benchmark (`BIRD Mini-Dev 2026` + Fair Missing-Column Refusal)

Evaluated on a single NVIDIA L4 GPU (22GB) via [`notebooks/05_public_benchmark.ipynb`](https://github.com/2422725977/swift-sql/blob/main/notebooks/05_public_benchmark.ipynb). All competitors receive standard SQL prompts (stripping `<think>` blocks fairly) and explicit `CANNOT_ANSWER` instructions for missing columns:

| Benchmark Metric | **SwiftSQL-3B** | **SwiftSQL-3B+Repair** | Base-3B | XiYanSQL-3B | Arctic-R1-7B |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Refusal F1 (Missing-Column Stress)** | **98.77%** 🏆 | **98.77%** 🏆 | 67.69% | 9.52% | 0.00% |
| **BIRD Mini-Dev SQLite EX\\*** | **4.32%** *(1st in 3B)* | **4.32%** *(1st in 3B)* | 3.09% | 3.70% | 8.02% *(7B)* |
| **BIRD PG / MySQL Syntax\\*** | 83.50% | 83.50% | **98.00%** | 96.50% | 92.50% |
| **Avg Output Tokens** *(lower is faster)* | **98.9** | **98.9** | 81.5 | 74.0 | 566.3 *(5.7×)* |
| **Single-Request Latency (ms, L4 PyTorch)** | **2,981.7** | **2,981.7** | 2,364.5 | 2,068.4 | 13,694.1 *(4.6× slower)* |
| **Batch Throughput (QPS, L4)** | **1.10** | **1.10** | 1.48 | 1.53 | 0.08 *(13.8× lower)* |

> **\\*Transparent Evaluation Note:** All models were tested under identical short-context caps (`MAX_SCHEMA_CHARS=5500`, `max_length=2560`). Because large BIRD enterprise schemas often span 15,000–35,000 chars with inline comments and examples, truncation cut off target tables on many questions—compressing absolute `BIRD_SQLite_EX` across all models (including Arctic-R1-7B at 8.02%). On those truncated schemas, `SwiftSQL-3B`'s strict anti-hallucination refusal cleanly abstained (`"answerable": false`), explaining the raw syntax percentage while still ranking #1 among 3B models on executable BIRD tasks.

---

## 📦 Files & SHA-256 Checksums

| File | Format | Size | Recommendation | SHA-256 (LFS) |
| :--- | :---: | :---: | :--- | :--- |
| `SwiftSQL-3B-Q8_0.gguf` | GGUF Q8_0 | 3.06 GB | Near-lossless quality, ideal for 16GB Apple Silicon | `dc109bac55e2c176edf47f504b2f1a95429e12b1050c2f4db3fbd8c4617dabec` |
| `SwiftSQL-3B-Q4_K_M.gguf` | GGUF Q4_K_M | 1.80 GB | Ultra-fast, minimal footprint & higher concurrency | `cdb70d928434ff2dabb22382657d969cd9e2ee06243b85bb8e0edcf15b686641` |
| `adapter_model.safetensors` | LoRA (`r=64`) | 228 MB | Adapter in [`xiain/SwiftSQL-3B-LoRA`](https://huggingface.co/xiain/SwiftSQL-3B-LoRA) | `dc635d966ec92fbf347e9cc7de65cfbeaa0245a8ac04bc0350053eb36b7c65a7` |

---

## 🚀 Quick Start

### 1. Run Immediately with Ollama (1 Command)
```bash
ollama run hf.co/xiain/SwiftSQL-3B-GGUF:Q8_0
# Or lightweight Q4_K_M (1.80 GB):
ollama run hf.co/xiain/SwiftSQL-3B-GGUF:Q4_K_M
```

### 2. High-Concurrency OpenAI-Compatible API via `llama.cpp`
```bash
llama-server -hf xiain/SwiftSQL-3B-GGUF:Q8_0 \\
  --port 11434 --ctx-size 4096 --parallel 4 --flash-attn
```

### 3. Production API Gateway (Auth + Read-Only Guardrail + 1-Shot Auto-Repair)
Clone [github.com/2422725977/swift-sql](https://github.com/2422725977/swift-sql) and run `serve/api_gateway.py` in front of `llama-server` / Ollama for API key authentication, rate limiting, `sqlglot` read-only safety blocking, and automatic 1-shot SQL self-repair.

---

## 🧩 Prompt Format

**System Prompt**
```text
You are SwiftSQL, a fast and accurate multi-dialect Text-to-SQL engine.
Rules:
1. Respond ONLY with a single valid JSON object. No markdown fences or extra text.
2. Follow the requested SQL dialect strictly (postgresql, mysql, or sqlite) and output read-only SELECT queries only.
3. Auto-Think: leave "plan" empty ("") for simple and single-JOIN queries; only for complex multi-JOIN, subquery, CTE, HAVING, or window queries, write an ultra-brief plan (<= 60 chars) in "plan" before "sql".
4. Never invent tables or columns. If the schema lacks required information to answer the question, set "answerable": false, "sql": "", and list missing fields in "missing".
```

**User Prompt (`generate_sql`)**
```text
Task: generate_sql
Dialect: postgresql
Mode: auto
Schema:
CREATE TABLE orders (id INT, user_id INT, amount NUMERIC, status TEXT);

Question:
统计每个用户的已完成订单总金额，按总金额降序取前 10 名
```

**Expected Output**
```json
{"answerable": true, "plan": "", "dialect": "postgresql", "sql": "SELECT user_id, SUM(amount) AS total_amount FROM orders WHERE status = 'completed' GROUP BY user_id ORDER BY total_amount DESC LIMIT 10", "tables": ["orders"]}
```

**User Prompt (`repair_sql`)**
```text
Task: repair_sql
Dialect: postgresql
Schema:
CREATE TABLE orders (id INT, user_id INT, amount NUMERIC, status TEXT);

Question:
统计每个用户的订单数

Failed SQL:
SELECT user_id, COUNT(*) FORM orders GROUP BY user_id

Error:
syntax error at or near "FORM"
```

---

## ⚠️ Limitations & License
- Trained with `max_seq_length=2048` (`max_schema_chars=4000`). For large multi-dozen-table schemas, apply lightweight table pre-filtering before invoking generation.
- Always enforce database-level read-only roles alongside static SQL validation (`sqlglot`).
- Released under **Apache 2.0**.
"""


def main() -> None:
    token = os.getenv("HF_TOKEN") or getpass.getpass("Enter your Hugging Face Write Token: ").strip()
    api = HfApi(token=token)
    whoami = api.whoami()
    print(f"Authenticated as: {whoami['name']}")

    targets = [
        (GGUF_REPO_ID, "GGUF"),
        (LORA_REPO_ID, "LoRA Adapter"),
    ]
    tmp_dir = Path("/tmp/swiftsql_hf_cards")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for repo_id, label in targets:
        content = MODEL_CARD_TEMPLATE.format(variant_label=label)
        card_file = tmp_dir / f"{repo_id.replace('/', '_')}_README.md"
        card_file.write_text(content, encoding="utf-8")
        print(f"Uploading updated README.md -> https://huggingface.co/{repo_id} ...")
        api.upload_file(
            path_or_fileobj=str(card_file),
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="model",
            commit_message="docs: sync refactored Model Card with BIRD Mini-Dev & refusal head-to-head benchmarks",
        )
        print(f"  Done: https://huggingface.co/{repo_id}")


if __name__ == "__main__":
    main()
