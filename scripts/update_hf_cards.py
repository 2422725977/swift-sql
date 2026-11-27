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
  - nl2sql
  - sql
  - gguf
  - small-language-model
  - qwen2.5-coder
  - dpo
  - postgresql
  - mysql
  - sqlite
  - ollama
  - llama-cpp
  - local-llm
datasets:
  - gretelai/synthetic_text_to_sql
  - trl-lab/SQaLe-text-to-SQL-dataset
  - jtjt520j/CSpider_and_DUSQL_sql_create_context
---

# ⚡ SwiftSQL-3B ({variant_label})

**A fast, accurate, bilingual (English & Chinese), multi-dialect (PostgreSQL / MySQL / SQLite) lightweight Text-to-SQL model — built to drop straight into real business databases and automation workflows.**

**轻量、极速、不瞎编字段的中英双语 Text-to-SQL 模型（仅 1.8GB 起步）——Windows / Mac / Linux 普通电脑、笔记本、消费级显卡甚至纯 CPU 都能流畅离线运行，开发者拿过去就能直接接进中小型业务库或 Dify / n8n 自动化工作流。**

- **GitHub (Full Code, Benchmarks & Ready-to-Use FastAPI Guardrail Gateway)**: [github.com/2422725977/swift-sql](https://github.com/2422725977/swift-sql)
- **GGUF Quantized Models**: [`xiain/SwiftSQL-3B-GGUF`](https://huggingface.co/xiain/SwiftSQL-3B-GGUF)
- **LoRA Adapter**: [`xiain/SwiftSQL-3B-LoRA`](https://huggingface.co/xiain/SwiftSQL-3B-LoRA)

---

## ✨ Why SwiftSQL? / 5 大实用优势

1. **🛡️ Refuses Missing Columns Instead of Hallucinating (`98.77%` Refusal F1)**: When a user asks for a column that doesn't exist in your schema (e.g., asking for `phone` when only `name` & `city` exist), SwiftSQL honestly returns `"answerable": false` and lists missing fields — vs `67.69%` for Base-3B, `9.52%` for XiYanSQL-3B, and `0.00%` for Arctic-R1-7B.
2. **⚡ Runs on Any Everyday Hardware (4.6× Faster & 5.7× Fewer Tokens than 7B CoT)**: Only **1.80 GB (`Q4_K_M`)** to **3.06 GB (`Q8_0`)**. Runs smoothly on 8GB–16GB laptops (Windows / Mac / Linux), 4GB+ consumer GPUs, or even CPU-only machines — with **13.8× higher batch throughput** than Arctic-R1-7B.
3. **🎯 +10.73% Execution Accuracy Jump over Base 3B**: Reaches **70.15% Execution Accuracy** (with 1-shot self-repair) vs **59.42%** for Base-3B on held-out multi-dialect execution evaluation.
4. **🌍 Standard DDL In, Production Dialects Out (EN & ZH)**: Paste standard `CREATE TABLE` DDL directly (no custom schema converter needed) and target **PostgreSQL**, **MySQL**, or **SQLite** in English or Chinese.
5. **📦 100% Strict JSON + Built-in Self-Repair**: Always outputs clean, directly parseable JSON with zero conversational filler, and natively supports 1-shot SQL error repair (`Task: repair_sql`).

---

## 📊 Benchmarks / 实测对比

### 1. Held-Out Multi-Dialect & Refusal Progression (300 Samples)

| Metric | Base-3B | **SwiftSQL-3B** | **SwiftSQL-3B + 1-Shot Repair** | Improvement |
| :--- | :---: | :---: | :---: | :---: |
| **Execution Accuracy (EX)** | 59.42% | 69.15% | **70.15%** | **+10.73%** |
| **Refusal F1 (Anti-Hallucination)** | 0.00% | **90.41%** | **90.41%** | **+90.41%** |
| **Strict JSON Compliance** | 100.0% | **100.0%** | **100.0%** | Zero filler |
| **Multi-Dialect Syntax Valid** | 99.63% | **97.38%** | **97.38%** | Production-ready |

### 2. Head-to-Head Public Benchmark (`BIRD Mini-Dev 2026` + Fair Missing-Column Refusal)

| Benchmark Metric | **SwiftSQL-3B** | Base-3B | XiYanSQL-3B | Arctic-R1-7B *(7B)* |
| :--- | :---: | :---: | :---: | :---: |
| **Refusal F1 (Missing-Column Stress)** | **98.77%** 🏆 | 67.69% | 9.52% | 0.00% |
| **BIRD Truncated-Schema SQLite EX\\*** | **4.32%** *(1st in 3B)* | 3.09% | 3.70% | 8.02% |
| **Avg Output Tokens** *(lower is faster)* | **98.9** | 81.5 | 74.0 | 566.3 *(5.7×)* |
| **Single-Request Latency (ms, L4)** | **2,981.7** | 2,364.5 | 2,068.4 | 13,694.1 *(4.6× slower)* |
| **Batch Throughput (QPS, L4)** | **1.10** | 1.48 | 1.53 | 0.08 *(13.8× lower)* |

> **\\*Evaluation Note:** All models were evaluated under identical short-context caps (`MAX_SCHEMA_CHARS=5500`, `max_length=2560`). Because large BIRD enterprise schemas often exceed 15,000–35,000 chars with comments, truncation cut off target tables on many questions—compressing absolute EX for every model (including 7B Arctic-R1). Full reproducible script: [`notebooks/05_public_benchmark.ipynb`](https://github.com/2422725977/swift-sql/blob/main/notebooks/05_public_benchmark.ipynb).

---

## 📦 Available Files & Verified SHA-256

| File | Size | Best For | SHA-256 (LFS) |
| :--- | :---: | :--- | :--- |
| `SwiftSQL-3B-Q8_0.gguf` | 3.06 GB | Near-lossless precision (16GB+ RAM or 6GB+ VRAM) | `dc109bac55e2c176edf47f504b2f1a95429e12b1050c2f4db3fbd8c4617dabec` |
| `SwiftSQL-3B-Q4_K_M.gguf` | 1.80 GB | Everyday laptops (8GB RAM / 4GB VRAM / CPU / high concurrency) | `cdb70d928434ff2dabb22382657d969cd9e2ee06243b85bb8e0edcf15b686641` |
| `adapter_model.safetensors` | 228 MB | LoRA (`r=64`) adapter in [`xiain/SwiftSQL-3B-LoRA`](https://huggingface.co/xiain/SwiftSQL-3B-LoRA) | `dc635d966ec92fbf347e9cc7de65cfbeaa0245a8ac04bc0350053eb36b7c65a7` |

---

## 🚀 30-Second Quick Start (Windows / Mac / Linux)

### 1. Run with Ollama (1 Command)
```bash
# Near-lossless Q8_0 (3.06 GB)
ollama run hf.co/xiain/SwiftSQL-3B-GGUF:Q8_0

# Lightweight Q4_K_M (1.80 GB, runs easily on 8GB RAM laptops)
ollama run hf.co/xiain/SwiftSQL-3B-GGUF:Q4_K_M
```

### 2. High-Concurrency OpenAI-Compatible API (`llama.cpp`)
```bash
# --parallel 4 handles 4 concurrent requests; --ctx-size 4096 fits typical business schemas
llama-server -hf xiain/SwiftSQL-3B-GGUF:Q8_0 \\
  --port 11434 --ctx-size 4096 --parallel 4 --flash-attn
```

### 3. Production FastAPI Gateway (Auth + Read-Only Guardrail + Auto-Repair)
See [github.com/2422725977/swift-sql](https://github.com/2422725977/swift-sql) for the ready-to-use `serve/api_gateway.py` with API key auth, rate limiting, `sqlglot` read-only safety blocking, and automatic 1-shot SQL self-repair.

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

---

## ⚠️ Scope & License
- Ideal for small-to-medium schemas (≤ ~10 tables / ~4,000 DDL chars). For databases with dozens of tables, pre-filter relevant tables before querying.
- Always enforce database-level read-only permissions in production alongside static SQL validation.
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
        content = MODEL_CARD_TEMPLATE.replace("{variant_label}", label)
        card_file = tmp_dir / f"{repo_id.replace('/', '_')}_README.md"
        card_file.write_text(content, encoding="utf-8")
        print(f"Uploading updated README.md -> https://huggingface.co/{repo_id} ...")
        api.upload_file(
            path_or_fileobj=str(card_file),
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="model",
            commit_message="docs: update Model Card with plain-language advantages, cross-platform guide & benchmarks",
        )
        print(f"  Done: https://huggingface.co/{repo_id}")


if __name__ == "__main__":
    main()
