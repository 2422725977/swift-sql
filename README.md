# SwiftSQL

**SwiftSQL** 是一个面向 **Apple Silicon 16GB 统一内存（如 Mac mini）本地部署与 API 分发** 的轻量级、高准确率、极速 **Text-to-SQL** 专用模型训练与服务框架，支持在 **Google Colab Pro（L4 / A100）** 一键复现。

[![Open V1 SFT in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/2422725977/swift-sql/blob/main/notebooks/01_data_prep_and_sft.ipynb)
[![Open V2 Eval & DPO in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/2422725977/swift-sql/blob/main/notebooks/02_eval_and_dpo.ipynb)
[![Open V3 Optional GRPO in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/2422725977/swift-sql/blob/main/notebooks/03_optional_grpo.ipynb)

---

## 核心差异化突破

针对当前开源轻量 Text-to-SQL 模型（Arctic-Text2SQL-R1、OmniSQL、XiYanSQL 等）的常见痛点，SwiftSQL 从训练数据、后训练目标到 API 护栏做了全链路优化：

1. **Auto-Think 自适应短推理（又快又准）**
   * 简单单表查询跳过思维链（`"plan": ""`），极速直出；
   * 复杂多表 JOIN / 子查询 / CTE / 窗口函数仅输出 **1 句精简表字段规划** 再生成 SQL，兼顾推理准确率与极低端到端延迟。
2. **中英双语 + 多方言显式切换（PostgreSQL / MySQL / SQLite）**
   * 基于 `sqlglot` 自动将开源语料转译并校验为三方言对齐样本，直接接收标准 `CREATE TABLE` DDL，无需改造业务 Schema 格式。
3. **单模型三合一能力：生成 + 报错自修复 + 防幻觉拒答**
   * 70% 标准生成 + 20% SQL 报错自修复（`repair_sql`）+ 10% 缺列不可回答拒答（`answerable: false`），大幅减少胡编列名。
4. **执行引导 DPO（V2）+ 轻量 API 确定性护栏（V3）**
   * 利用真实 SQLite 沙箱执行结果筛选 **“对且短” vs “错或啰嗦”** 偏好对做 DPO 对齐；
   * Mac mini 推理前挂 FastAPI + `sqlglot`（<2ms），实现 **只读安全拦截 + 语法预检 + 报错自动触发 1 次模型自修复 + API Key 鉴权与限流**。

---

## Colab Pro（200 积分）省算力指南

| 运行时 | 显存 | 约耗积分/小时 | 推荐用途 |
| :--- | :--- | :--- | :--- |
| **L4 GPU（强烈推荐）** | 24GB | ~2 CU/h | 跑完 V1 SFT + V2 评测/DPO 仅耗 ~3–5 积分，200 积分可迭代几十轮 |
| **A100 GPU** | 40GB / 80GB | ~7–13 CU/h | 需要训练 7B 模型或大步数 GRPO 时再切 A100 |

默认基座为 **`Qwen/Qwen2.5-Coder-3B-Instruct`**（可在 `configs/train_config.yaml` 或 Notebook 第一行一键切换为 `7B`）：
* **3B `Q8_0` 量化** 在 Mac mini 16GB 仅占 **~3.6GB**（几乎无损，推理极快、支持多并发 API）；
* **3B `Q4_K_M` 量化** 仅占 **~2.2GB**。

---

## 项目结构

```text
swift-sql/
├── configs/train_config.yaml         # 模型、数据配比、LoRA/SFT/DPO/导出配置
├── src/swiftsql/
│   ├── dialect.py                    # sqlglot 多方言转译、只读护栏、复杂度分级、删列变异
│   ├── prompts.py                    # 统一 ChatML 提示词与严格 JSON 解析
│   ├── data_pipeline.py              # 公开数据集拉取 + Auto-Think / 多方言 / 修复 / 拒答合成
│   ├── evaluation.py                 # 真实 SQLite 沙箱执行准确率(EX) / 语法率 / 拒答 F1 评测
│   └── dpo_builder.py                # 执行引导 DPO 偏好对自动构建
├── notebooks/
│   ├── 01_data_prep_and_sft.ipynb    # V1: 数据构建 + Unsloth SFT + 导出 GGUF
│   ├── 02_eval_and_dpo.ipynb         # V2: 基准对比评测 + 执行引导 DPO + 导出 GGUF
│   └── 03_optional_grpo.ipynb        # V3(可选): 在线执行奖励 GRPO 进阶实验
├── serve/
│   ├── Modelfile.template            # Ollama 导入模板
│   └── api_gateway.py                # Mac mini 轻量 FastAPI 网关（鉴权+限流+护栏+自动修复）
└── tests/                            # 本地自动化单元测试
```

---

## 快速开始

### 1. 在 Colab Pro 上训练（推荐直接点击顶部徽章）
1. 打开 `notebooks/01_data_prep_and_sft.ipynb`，选择 **L4 GPU** 运行时；
2. 依次运行：挂载 Google Drive → 自动拉取公开数据集并合成 V1 语料 → Unsloth QLoRA 微调 → 自动导出 `q8_0` / `q4_k_m` GGUF 到 Google Drive；
3. 打开 `notebooks/02_eval_and_dpo.ipynb`，自动对比 **基座 3B vs V1 SFT**，生成执行验证偏好对并跑完 **V2 DPO**，再次评测验证提升。

### 2. 在 Mac mini (16GB) 本地部署并分发 API

#### 启动本地推理引擎（二选一）
**方式 A：Ollama（最简单）**
```bash
# 把从 Google Drive 下载的 GGUF 放到 serve/ 目录
ollama create swiftsql-3b -f serve/Modelfile.template
```

**方式 B：llama.cpp（并发吞吐更高）**
```bash
brew install llama.cpp
llama-server -m ./swiftsql-3b-v2-q8_0.gguf \
  --port 11434 --ctx-size 4096 --parallel 4 --flash-attn
```

#### 启动带护栏与自修复的 API 网关
```bash
uv pip install -e ".[serve]"
export SWIFTSQL_API_KEYS="sk-my-secret-key-1,sk-my-secret-key-2"
export SWIFTSQL_BACKEND_URL="http://127.0.0.1:11434/v1/chat/completions"
export SWIFTSQL_MODEL_NAME="swiftsql-3b"
uvicorn serve.api_gateway:app --host 0.0.0.0 --port 8000
```

#### 调用示例
```bash
curl -X POST http://127.0.0.1:8000/v1/text2sql \
  -H "Authorization: Bearer sk-my-secret-key-1" \
  -H "Content-Type: application/json" \
  -d '{
    "dialect": "postgresql",
    "mode": "auto",
    "schema": "CREATE TABLE orders (id INT, user_id INT, amount NUMERIC, status TEXT);",
    "question": "统计每个用户的已完成订单总金额，按总金额降序取前 10 名"
  }'
```

#### 对外安全分发（无需公网 IP）
* 公网 HTTPS 分发：`cloudflared tunnel --url http://127.0.0.1:8000`
* 内部私网访问：通过 Tailscale 暴露局域网地址即可。

---

## 本地运行测试

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -v
```
