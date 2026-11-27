<div align="center">

# ⚡ SwiftSQL

**轻量、极速、不瞎编字段的中英双语 Text-to-SQL 模型与开箱即用 API 网关**  
*仅 1.8GB 起步｜Windows / Mac / Linux 都能跑｜原生支持 PostgreSQL / MySQL / SQLite｜直接接入业务库与自动化工作流*

[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Hugging Face GGUF](https://img.shields.io/badge/%F0%9F%A4%97%20下载模型-SwiftSQL--3B--GGUF-yellow)](https://huggingface.co/xiain/SwiftSQL-3B-GGUF)
[![Hugging Face LoRA](https://img.shields.io/badge/%F0%9F%A4%97%20微调权重-SwiftSQL--3B--LoRA-blue)](https://huggingface.co/xiain/SwiftSQL-3B-LoRA)
[![Base Model](https://img.shields.io/badge/Base-Qwen2.5--Coder--3B%2F7B-purple)](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct)

</div>

---

## 💡 SwiftSQL 是什么？能帮你做什么？

简单来说，**SwiftSQL 能把你的中文或英文大白话，快速、准确地翻译成可以直接运行的 SQL 查询语句**。

它不是只能看个热闹的“论文玩具”，而是专门为 **真实开发和日常办公** 打造的轻量方案——**开发者拿过去就能直接接进中小型业务数据库、内部 BI 查数机器人，或者 Dify / n8n / Coze 等自动化工作流**。

### 适用场景
* 📊 **内部自然语言查数**：运营、产品直接用中文问“上个月复购率最高的前 10 个商品”，自动生成可执行 SQL。
* 🤖 **自动化工作流 / Agent 插件**：输出 **100% 严格 JSON**，没有任何多余废话，代码和工作流直接解析不报错。
* 🔒 **私有数据本地离线运行**：体积仅 **1.8GB ～ 3.1GB**，普通笔记本、台式机、公司内网小服务器（Windows / Mac / Linux，有无独立显卡均可）都能流畅离线运行，**数据库结构与业务数据完全不出内网、零 API 费用**。

---

## ✨ 为什么选择 SwiftSQL？（5 大核心优势）

很多开源 SQL 模型在真实接入业务时会遇到 4 个头疼问题：**动辄需要大显卡、回答慢得像写作文、表里没这个字段也硬编、输出一堆废话导致程序解析失败**。SwiftSQL 针对这些痛点做了全套解决：

1. **🛡️ 不瞎编字段，表里没有就老实告诉你（防幻觉拒答率 98.77%）**
   * 真实业务里，用户经常问数据库里根本没存的信息（比如表里只有姓名和城市，却问“查手机号”）。
   * 公开横评中，很多知名 SQL 模型甚至 7B 旗舰模型会 **100% 瞎编一个不存在的列名** 导致查询报错；而 **SwiftSQL 专门训练了拒答能力**，缺字段时明确返回 `"answerable": false` 并指出缺了哪个字段。
2. **⚡ 轻量极速，普通电脑也能跑（比 7B 思考模型快 4.6 倍、省 5.7 倍字数）**
   * 最小量化版仅 **1.8GB**（`Q4_K_M`），近无损版仅 **3.1GB**（`Q8_0`）；**8GB～16GB 内存的 Windows / Mac / Linux 笔记本、消费级显卡（4GB+ 显存）甚至纯 CPU 都能跑**。
   * 简单查询直接秒出 SQL，不写几百字的废话思考过程，并发吞吐比 7B 长思考模型高 **13.8 倍**。
3. **🌍 直接支持主流生产数据库 + 中英双语**
   * 无需把你的建表语句改造成奇怪格式，**直接粘贴标准 `CREATE TABLE` 建表语句**就能用。
   * 显式支持 **PostgreSQL / MySQL / SQLite** 三大主流数据库方言，中文、英文提问都能精准理解。
4. **📦 100% 严格 JSON 输出 + 自带安全护栏 API 网关**
   * 每次回复都是标准 JSON（`sql`、`tables`、`answerable`），程序直接 `json.loads()` 就能拿去用，不用写复杂正则去抠代码。
   * 仓库自带开箱即用的 FastAPI 服务（`serve/api_gateway.py`），内置 **API Key 鉴权、限流、只读安全拦截（严禁 `DROP/DELETE/UPDATE` 删库）**。
5. **🔧 写错语法自动自我修复**
   * 网关内置毫秒级 SQL 语法预检；如果偶尔生成了语法有问题的 SQL，网关会自动把报错信息丢回给同一个模型，**自动触发 1 次自我修复**再返回，大幅提升线上可用率。

---

## 📊 实测效果对比（一看就懂）

### 1. 同模型微调前后对比（300 道中英多方言 + 缺列拒答测试题）

> 指标说明：**执行准确率 (EX)** = 生成的 SQL 放到真实数据库里跑，结果和标准答案完全一致的比例；**防幻觉拒答 (Refusal F1)** = 表里缺字段时准确拒答、不乱编字段的综合得分。

| 指标 | 原始基座 (Base-3B) | SwiftSQL-3B (微调后) | **SwiftSQL-3B + 网关自修复** | 提升幅度 |
| :--- | :---: | :---: | :---: | :---: |
| **执行准确率 (EX)** | 59.42% | 69.15% | **70.15%** | **+10.73%** 🔥 |
| **防幻觉拒答 (Refusal F1)** | 0.00% *(全靠瞎编)* | **90.41%** | **90.41%** | **+90.41%** 🔥 |
| **严格 JSON 合规率** | 100% | **100%** | **100%** | 零废话，直接解析 |
| **多方言语法合法率** | 99.63% | **97.38%** | **97.38%** | 稳健可用 |

### 2. 与业内知名开源 SQL 模型同台横评（相同测试环境）

在单张 L4 GPU 上，使用完全相同的测试条件，与同量级 3B 基座、知名 3B 专用模型（XiYanSQL-3B）以及 7B 强化学习旗舰模型（Arctic-R1-7B）公平对比（对所有竞品均明确提示“缺字段时请拒答不要瞎编”）：

| 评测维度 | **SwiftSQL-3B** | Base-3B | XiYanSQL-3B | Arctic-R1-7B *(7B)* |
| :--- | :---: | :---: | :---: | :---: |
| **防幻觉拒答 F1** *(越高越安全)* | **98.77%** 🏆 | 67.69% | 9.52% | 0.00% *(全瞎编)* |
| **BIRD 截断表 SQLite 执行率\*** | **4.32%** *(3B 第一)* | 3.09% | 3.70% | 8.02% |
| **平均输出 Token 数** *(越少越快)* | **98.9** | 81.5 | 74.0 | 566.3 *(多 5.7 倍)* |
| **单次响应耗时 (ms)** *(越低越快)* | **2,981.7** | 2,364.5 | 2,068.4 | 13,694.1 *(慢 4.6 倍)* |
| **并发吞吐 (QPS)** *(越高越能扛并发)* | **1.10** | 1.48 | 1.53 | 0.08 *(低 13.8 倍)* |

> **\*透明口径说明**：该公开横评统一限制了单题表结构输入不超过 `5,500` 字符（约 2,560 token），而 BIRD 官方企业库带大量注释（常达 15,000～35,000 字符），截断后所有模型都看不到完整表，因此所有模型的绝对执行分都偏低（连 7B 旗舰也仅 8.02%）。在此条件下，SwiftSQL-3B 仍在 3B 梯队排第一，同时展现出断层领先的防幻觉拒答能力和极高的响应速度。完整复现脚本见 [`notebooks/05_public_benchmark.ipynb`](notebooks/05_public_benchmark.ipynb)。

---

## 📦 模型下载（全平台通用 GGUF）

所有模型均已在 Hugging Face 开源并完成 SHA-256 完整性核验：

| 模型版本 | 大小 | 推荐硬件 / 使用场景 | 下载地址 |
| :--- | :---: | :--- | :---: |
| **SwiftSQL-3B `Q8_0`** *(推荐)* | **3.06 GB** | 精度几乎无损；推荐 **16GB+ 内存电脑** 或 **6GB+ 显存显卡** | [🤗 Hugging Face](https://huggingface.co/xiain/SwiftSQL-3B-GGUF) |
| **SwiftSQL-3B `Q4_K_M`** | **1.80 GB** | 极致轻快省空间；**8GB 内存笔记本 / 4GB 显存 / 纯 CPU / 高并发 API** 都能轻松跑 | [🤗 Hugging Face](https://huggingface.co/xiain/SwiftSQL-3B-GGUF) |
| **SwiftSQL-3B LoRA 权重** | 228 MB | 适合开发者结合 `Qwen2.5-Coder-3B-Instruct` 做二次微调 | [🤗 Hugging Face](https://huggingface.co/xiain/SwiftSQL-3B-LoRA) |

---

## 🚀 30 秒快速上手（Windows / Mac / Linux 通用）

### 方式 1：用 Ollama 一行命令直接体验（最简单，推荐新手）

先安装 [Ollama](https://ollama.com/)（支持 Windows / macOS / Linux，会自动调用本机 NVIDIA/AMD/Apple 显卡加速，无显卡则自动走 CPU）：

```bash
# 推荐：运行近无损 Q8_0 版（约 3.1GB，首次会自动从 Hugging Face 下载）
ollama run hf.co/xiain/SwiftSQL-3B-GGUF:Q8_0

# 如果内存或硬盘紧张（比如 8GB 内存电脑），换成 1.8GB 极速版：
ollama run hf.co/xiain/SwiftSQL-3B-GGUF:Q4_K_M
```

---

### 方式 2：用 `llama.cpp` 搭高并发本地引擎（适合做 API 服务）

`llama-server` 是单文件原生推理引擎，内存和硬盘占用极省，而且自带 OpenAI 兼容接口：

```bash
# macOS 安装示例（Windows / Linux 可直接从 llama.cpp Releases 下载预编译包）
brew install llama.cpp

# 启动本地推理服务（自动从 Hugging Face 拉取模型）
# --port 11434      : 推理服务监听端口
# --ctx-size 4096   : 最大上下文长度（足够放下常见中小型业务表结构）
# --parallel 4      : 支持 4 路请求同时并行处理，提升 API 并发吞吐
# --flash-attn      : 开启 Flash Attention 提速并省显存
llama-server -hf xiain/SwiftSQL-3B-GGUF:Q8_0 \
  --port 11434 --ctx-size 4096 --parallel 4 --flash-attn
```

---

### 方式 3：接入生产级 API 网关（鉴权 + 限流 + 防删库 + 自动修复）

如果你想把模型**安全地接入公司内部系统、前端应用或对外分发 API**，直接启动本仓库自带的 FastAPI 网关：

```bash
# 1. 下载代码并进入项目目录
git clone https://github.com/2422725977/swift-sql.git && cd swift-sql

# 2. 创建独立 Python 环境并安装 API 网关依赖（需要 Python 3.10+）
uv venv && source .venv/bin/activate     # Windows PowerShell 用: .venv\Scripts\Activate.ps1
uv pip install -e ".[serve]"

# 3. 配置环境变量并启动 API 服务（端口 8000）
export SWIFTSQL_API_KEYS="sk-my-key-1,sk-my-key-2"                     # 允许访问的 API Key（逗号分隔；留空则免鉴权）
export SWIFTSQL_BACKEND_URL="http://127.0.0.1:11434/v1/chat/completions" # 指向本地 Ollama 或 llama-server 地址
export SWIFTSQL_MODEL_NAME="SwiftSQL-3B-Q8_0"                          # 模型名称标识
uvicorn serve.api_gateway:app --host 0.0.0.0 --port 8000
```

#### 调用示例 1：中文提问 → 生成 PostgreSQL 报表查询
```bash
curl -s http://127.0.0.1:8000/v1/text2sql \
  -H "Authorization: Bearer sk-my-key-1" \
  -H "Content-Type: application/json" \
  -d '{
    "dialect": "postgresql",
    "schema": "CREATE TABLE orders (id INT, user_id INT, amount NUMERIC, status TEXT);",
    "question": "统计每个用户的已完成订单总金额，按总金额降序取前 10 名"
  }'
```
返回结果（干净的标准 JSON，程序直接解析）：
```json
{
  "answerable": true,
  "dialect": "postgresql",
  "sql": "SELECT user_id, SUM(amount) AS total_amount FROM orders WHERE status = 'completed' GROUP BY user_id ORDER BY total_amount DESC LIMIT 10",
  "plan": "",
  "tables": ["orders"],
  "repaired": false,
  "syntax_valid": true
}
```

#### 调用示例 2：表里缺字段 → 自动诚实拒答，不胡编列名
```bash
curl -s http://127.0.0.1:8000/v1/text2sql \
  -H "Authorization: Bearer sk-my-key-1" \
  -H "Content-Type: application/json" \
  -d '{
    "dialect": "mysql",
    "schema": "CREATE TABLE users (id INT, name TEXT, city TEXT);",
    "question": "查询所有北京用户的手机号"
  }'
```
返回结果：
```json
{
  "answerable": false,
  "dialect": "mysql",
  "sql": "",
  "missing": ["phone"],
  "note": "提供的表结构中缺少回答该问题所需的字段：phone。",
  "syntax_valid": true
}
```

#### 想把本地 API 分享给团队或公网调用？（无需公网 IP）
* **公网 HTTPS 分发**：使用免费的 [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)，一行 `cloudflared tunnel --url http://127.0.0.1:8000` 即可获得 HTTPS 域名；
* **团队内网私用**：装上 [Tailscale](https://tailscale.com/) 即可跨设备安全直连。

---

## 🧩 提示词格式（直接调用模型时参考）

如果你不经过 `serve/api_gateway.py`，而是直接通过 Ollama / OpenAI SDK / Dify 调用模型，按下方格式传入即可发挥最佳效果（源码见 [`src/swiftsql/prompts.py`](src/swiftsql/prompts.py)）：

<details>
<summary><b>点击展开完整 System / 生成 / 报错自修复 提示词模板</b></summary>

**System Prompt（系统提示词）**
```text
You are SwiftSQL, a fast and accurate multi-dialect Text-to-SQL engine.
Rules:
1. Respond ONLY with a single valid JSON object. No markdown fences or extra text.
2. Follow the requested SQL dialect strictly (postgresql, mysql, or sqlite) and output read-only SELECT queries only.
3. Auto-Think: leave "plan" empty ("") for simple and single-JOIN queries; only for complex multi-JOIN, subquery, CTE, HAVING, or window queries, write an ultra-brief plan (<= 60 chars) in "plan" before "sql".
4. Never invent tables or columns. If the schema lacks required information to answer the question, set "answerable": false, "sql": "", and list missing fields in "missing".
```

**User Prompt — 生成 SQL（`generate_sql`）**
```text
Task: generate_sql
Dialect: postgresql
Mode: auto
Schema:
<你的 CREATE TABLE 建表语句>

Question:
<你的中文或英文查询问题>
```

**User Prompt — 报错自修复（`repair_sql`）**
```text
Task: repair_sql
Dialect: postgresql
Schema:
<你的 CREATE TABLE 建表语句>

Question:
<原始查询问题>

Failed SQL:
<之前报错的 SQL>

Error:
<数据库或语法校验器返回的报错信息>
```

</details>

---

## 🛠️ 开发者专区：复现训练与自定义微调（Google Colab 一键运行）

如果你希望用自己公司的业务表重新微调一个专属版本，整个训练、沙箱去脏、偏好对齐、公开评测与发布流程都已封装成一键 Colab Notebook（支持 3B 与 7B 两套配置切换）：

| Notebook | 作用 | 一键打开 |
| :--- | :--- | :---: |
| `01_data_prep_and_sft.ipynb` | 公开数据沙箱去脏 + 多方言/修复/拒答合成 + Unsloth 微调 | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/2422725977/swift-sql/blob/main/notebooks/01_data_prep_and_sft.ipynb) |
| `02_eval_and_dpo.ipynb` | 批量评测 + 稳态多轮执行偏好对齐（RPO-DPO）+ 自动择优导出 GGUF | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/2422725977/swift-sql/blob/main/notebooks/02_eval_and_dpo.ipynb) |
| `03_optional_grpo.ipynb` | 可选进阶：高难多表在线执行奖励强化学习（GRPO） | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/2422725977/swift-sql/blob/main/notebooks/03_optional_grpo.ipynb) |
| `04_publish_to_hf.ipynb` | 免费 CPU 直传 Google Drive 权重到 Hugging Face（0 积分） | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/2422725977/swift-sql/blob/main/notebooks/04_publish_to_hf.ipynb) |
| `05_public_benchmark.ipynb` | 官方 BIRD Mini-Dev + 缺列拒答竞品横评 | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/2422725977/swift-sql/blob/main/notebooks/05_public_benchmark.ipynb) |

### 项目目录速览
```text
swift-sql/
├── configs/                 # 3B 高速版 (train_config.yaml) 与 7B 高精度版 (train_config_7b.yaml) 配置
├── src/swiftsql/            # 核心库：多方言校验与护栏、提示词解析、沙箱数据清洗、评测与 DPO 构建
├── notebooks/               # 从训练、评测、横评到发布 Hugging Face 的 5 份完整 Colab Notebook
├── serve/                   # 开箱即用的 FastAPI 护栏网关 (api_gateway.py) 与 Ollama 模板
├── scripts/                 # 实用工具脚本（如 Model Card 秒级同步脚本）
└── tests/                   # 14 项本地自动化单元测试（运行 `pytest -v` 即可全部验证）
```

---

## ⚠️ 使用边界与开源协议

* **最佳适用规模**：中小型业务库（通常 ≤ 10 张表、建表 DDL 在 4,000 字符以内）。如果你的数据库有几十上百张表，建议先用关键词/向量检索筛出最相关的 5～8 张表，再交给 SwiftSQL 生成 SQL，速度和准确率都会达到最佳状态。
* **生产安全建议**：虽然 API 网关内置了 `sqlglot` 只读拦截（禁止写操作和删表），但在生产环境中**务必同时为数据库账号配置只读权限**，做到双重保险。
* **开源协议**：本项目基于 **Apache 2.0** 协议开源，可自由学习、二次开发与商业使用。
