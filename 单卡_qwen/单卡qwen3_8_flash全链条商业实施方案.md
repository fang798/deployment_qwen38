退一步用 **单张 RTX 5090（32GB 显存）+ `Qwen/Qwen3.8-27B**` 来跑通全套 Docker 商业链路，是非常明智的工程决策。

不同于前文体量庞大、需要多卡切分与跨节点卸载的 `Qwen3.8-Flash-Next (180B)`，**`Qwen3.8-27B` 是一个 27.78B 参数的纯稠密（Dense）原生多模态模型，采用完全开源的 Apache-2.0 许可证（100% 免费商用，无任何月活或营收限制）**。更关键的是，它无需挂载任何第三方补丁，直接用 **vLLM 官方 Docker 镜像** 就能在单张 RTX 5090 上原生调用 Blackwell 硬件级 `NVFP4` Tensor Core，跑出 **54 ms 的首字延迟（TTFT）** 与 **90–300+ Tokens/s 的生成速度**。

以下为你整理的 **版本选型、纯 Docker 商业全链路部署、三种 Offload 实操，以及 `Tokens/s` 与 `TTFT` 极限调优指南**。

---

### 一、 版本选型：单卡 RTX 5090 (32GB) 该下哪个 `Qwen3.8-27B`？

`Qwen3.8-27B` 共 64 层，采用了 **48 层 Gated DeltaNet（线性注意力，状态体积恒定）+ 16 层 Gated Attention（全注意力，僅 4 个 KV 头）** 的 3:1 混合架构。由于只有 1/4 的层会产生随长度增长的 KV 缓存，它在 FP8 KV 精度下**每 Token 仅消耗约 35–37 KB 显存**！

在单张 RTX 5090（Linux 下实际可用显存为 **31.4 GiB**）上，根据 vLLM 官方配置库（[recipes.vllm.ai/Qwen/Qwen3.8-27B](https://recipes.vllm.ai/Qwen/Qwen3.8-27B)）的实测对比，共有 3 个主流官方/社区版本可供选择：

| 候选模型仓库 (Hugging Face) | 量化格式与权重占用 | 单卡 5090 剩余 KV 缓存池容量 | 内置 MTP 投机接受率 | 适用场景与选型建议 |
| --- | --- | --- | --- | --- |
| **`unsloth/Qwen3.8-27B-NVFP4`**<br>

<br>*(或同源镜像 `RedHatAI/Qwen3.8-27B-NVFP4`)*

 | **混合 NVFP4 (~21.3 GiB)**<br>

<br>通道级 FP8 + 4-bit 权重组

 | **最大（可容纳 ~19.7万–30万+ KV Tokens）**<br>

<br>单卡即可开满 131K–191K 上下文并跑多并发

 | **78.8%**

 | **【商业卖 Token 首选】**<br>

<br>比纯 W4A4 版省出近 3.3 GiB 显存，无需关 CUDA Graph 即可跑高并发

 |
| **`Inferact/Qwen3.8-27B-NVFP4`**<br>

<br>*(或官方 `nvidia/Qwen3.8-27B-NVFP4`)*

 | **纯正 NVFP4 (24.6 GiB)**<br>

<br>全均匀 W4A4 量化

 | **中等（32K 窗口下约 9.1万–15.2万 KV Tokens）**<br>

<br>因权重占 24.6 GiB，需加 `--enforce-eager` 或限制 Graph 尺寸防 OOM

 | **89.7%（最高）**

 | **【vLLM 官方 Recipe 默认推荐】**<br>

<br>MTP 投机采样命中率最高，适合低并发、追求极致单流质量与速度的场景

 |
| **`Qwen/Qwen3.8-27B-FP8`**

 | **官方 FP8 (~28.5–30.9 GB)**

 | **极小（在 32GB 单卡上仅剩 ~1–2 GiB）**<br>

<br>不开启 CPU 卸载时难以支撑长上下文与并发

 | **77.1%**

 | 适合双卡 5090 (`TP=2`)，或在单卡 5090 上专门用来练习 `--cpu-offload-gb` 卸载

 |

> **选型结论**：在单卡 RTX 5090 上跑商业全链路，**强烈建议优先下载 `unsloth/Qwen3.8-27B-NVFP4`（约 21.3 GiB）**。在 RTX 5090 (`sm120`) 上，vLLM 会自动为它和 `Inferact` 版调用原生的 `FlashInferCutlassNvFp4LinearKernel` 硬件加速内核（绝非软件模拟回退），且多出来的 3.3 GiB 显存能让你在单卡上从容开启 CUDA Graph 与大并发。
> 
> 

---

### 二、 纯 Docker 全链路部署实战（vLLM + New API + MySQL + Redis）

为了让你彻底掌握 Docker 化企业部署，我们将 **模型下载、vLLM 推理容器、New API 计费网关、MySQL 数据库、Redis 缓存** 全部封装进一套标准的 Docker 流程中。宿主机除了安装好 NVIDIA 驱动和 `nvidia-container-toolkit` 外，**不需要安装任何 Python 环境或依赖包**。

#### 第 1 步：创建工作目录并用 Docker 容器下载模型权重

不要在宿主机装 `pip`，直接用一个临时 Docker 容器把 `unsloth/Qwen3.8-27B-NVFP4` 下载到宿主机的 `/data/models` 目录中：

```bash
# 1. 创建统一的项目目录与数据持久化目录
mkdir -p /opt/llm-cloud/{models,new-api,mysql,redis}
cd /opt/llm-cloud

# 2. 使用纯 Docker 一键拉取 unsloth/Qwen3.8-27B-NVFP4 权重（约 23.4 GB，下载完容器自动销毁）
docker run --rm -it \
    -v /opt/llm-cloud/models:/models \
    -e HF_HUB_ENABLE_HF_TRANSFER=1 \
    python:3.11-slim \
    bash -c "pip install -U 'huggingface_hub[cli]' hf_transfer && huggingface-cli download unsloth/Qwen3.8-27B-NVFP4 --local-dir /models/Qwen3.8-27B-NVFP4"

```

(注：如果你想顺便体验 vLLM 官方 Recipe 默认的 `Inferact/Qwen3.8-27B-NVFP4`，只需把上面命令最后的仓库名换成 `Inferact/Qwen3.8-27B-NVFP4` 即可。)

#### 第 2 步：编写全链路 `docker-compose.yml`（推理 + 计费网关一体编排）

在 `/opt/llm-cloud/docker-compose.yml` 中写入以下配置。所有的服务都在同一个名为 `ai-tier-net` 的 Docker 内部虚拟网桥中，New API 可以直接通过容器名 `http://vllm-engine:8000` 访问你的 5090 推理引擎，无需将 vLLM 端口暴露给公网：

```yaml
version: '3.8'

services:
  # ====================================================================
  # 1. 核心推理层：官方 vLLM 容器（驱动单卡 RTX 5090 跑 Qwen3.8-27B-NVFP4）
  # ====================================================================
  vllm-engine:
    image: vllm/vllm-openai:nightly
    container_name: vllm-qwen38-27b
    restart: unless-stopped
    ipc: host
    shm_size: '16g'
    ports:
      - "127.0.0.1:8000:8000"   # 仅绑定本机回环地址供调试，公网流量一律走 3000 端口的 New API
    volumes:
      - /opt/llm-cloud/models:/models:ro
      - ~/.cache/vllm:/root/.cache/vllm   # 持久化 FlashInfer JIT 编译缓存，避免每次重启重新编译
    environment:
      - NVIDIA_VISIBLE_DEVICES=0          # 指定使用第 0 号 RTX 5090
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0']
              capabilities: [gpu]
    command: >
      --model /models/Qwen3.8-27B-NVFP4
      --served-model-name qwen3.8-27b
      --tensor-parallel-size 1
      --gpu-memory-utilization 0.92
      --max-model-len 131072
      --max-num-seqs 32
      --max-num-batched-tokens 8192
      --long-prefill-token-threshold 1024
      --kv-cache-dtype fp8
      --enable-prefix-caching
      --enable-chunked-prefill
      --async-scheduling
      --speculative-config '{"method":"mtp","num_speculative_tokens":3}'
      --cudagraph-capture-sizes 1 2 4 8 16 32
      --default-chat-template-kwargs '{"reasoning_effort":"medium","preserve_thinking":true}'
      --reasoning-parser qwen3
      --enable-auto-tool-choice
      --tool-call-parser qwen3_coder
      --enable-prompt-tokens-details
      --enable-force-include-usage
    networks:
      - ai-tier-net

  # ====================================================================
  # 2. 商业网关与发卡计费层：New API（对外暴露 3000 端口）
  # ====================================================================
  new-api:
    image: CalciumIon/new-api:latest
    container_name: token-gateway-newapi
    restart: always
    ports:
      - "3000:3000"
    environment:
      - SQL_DSN=root:TokenPass2026!@tcp(mysql:3306)/newapi
      - REDIS_CONN_STRING=redis://redis:6379
      - TZ=Asia/Shanghai
      - ERROR_LOG_ENABLED=true
    volumes:
      - /opt/llm-cloud/new-api:/data
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_started
    networks:
      - ai-tier-net

  # ====================================================================
  # 3. 账单与用户数据库：MySQL 8.0
  # ====================================================================
  mysql:
    image: mysql:8.0
    container_name: token-mysql
    restart: always
    environment:
      - MYSQL_ROOT_PASSWORD=TokenPass2026!
      - MYSQL_DATABASE=newapi
    volumes:
      - /opt/llm-cloud/mysql:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-pTokenPass2026!"]
      interval: 5s
      timeout: 5s
      retries: 10
    networks:
      - ai-tier-net

  # ====================================================================
  # 4. 高速限流与缓存队列：Redis 7
  # ====================================================================
  redis:
    image: redis:7-alpine
    container_name: token-redis
    restart: always
    volumes:
      - /opt/llm-cloud/redis:/data
    networks:
      - ai-tier-net

networks:
  ai-tier-net:
    driver: bridge

```

> **针对 `Inferact/Qwen3.8-27B-NVFP4` 的特别排坑提示**：如果你下载的是 24.6 GiB 的 `Inferact` 权重，vLLM 官方 Recipe 明确警告：在单卡 5090 (31.4 GiB) 上直接捕获全尺寸 CUDA Graph 会在启动末尾报 `torch.OutOfMemoryError: Tried to allocate 784.00 MiB`。此时只需将上面 `command` 中的 `--cudagraph-capture-sizes 1 2 4 8 16 32` 替换为 **`--enforce-eager`**（或加上 `--language-model-only` 卸载视觉塔），即可 100% 顺利启动！
> 
> 

#### 第 3 步：掌握 Docker 常用运维命令并拉起全链路

```bash
# 1. 后台一键拉起整套商业集群（vLLM + New API + MySQL + Redis）
docker compose up -d

# 2. 实时查看单卡 5090 上 vLLM 的加载与编译进度（首次启动需 JIT 编译算子，约耗时 3~4 分钟）
docker logs -f vllm-qwen38-27b

# 3. 查看容器显存占用与健康状态
docker ps
nvidia-smi

```

当你看到 `docker logs -f vllm-qwen38-27b` 输出以下两行信息时，说明单卡 5090 推理引擎已经就绪：

* `GPU KV cache size: ~220,000 tokens`（或更高）
* `Application startup complete.`

#### 第 4 步：在 New API 后台完成渠道对接与商业发卡（3 分钟走通）

1. **登录后台**：浏览器打开 `http://你的服务器IP:3000`，默认管理员账号 `root`，密码 `123456`（登录后弹窗修改密码）。
2. **添加你的 5090 渠道**：
* 点击左侧【渠道】$\rightarrow$【添加渠道】：
* **类型**：选择 `OpenAI`
* **名称**：`Local-5090-Qwen3.8-27B`
* **代理地址（Base URL）**：直接填 Docker 内部容器地址 **`http://vllm-engine:8000`**（因为它们都在 `ai-tier-net` 网络内，连宿主机网卡都不用绕，零延迟！注意末尾不要加 `/v1`）
* **模型**：手动输入并添加 `qwen3.8-27b`
* **密钥**：随便填一个字符串（如 `sk-local-5090`），点击【提交】，然后在渠道列表点击【测试】，看到“测试成功，耗时 0.xx 秒”即代表内部链路打通！


3. **设置价格（模型倍率）**：
* 点击【运营设置】$\rightarrow$【模型倍率设置】，参考 OpenRouter 上 `qwen/qwen3.8-27b` 的真实行情（输入约 `$0.20 / 1M`，输出约 `$2.20 / 1M`，缓存命中约 `$0.035 / 1M`），填入对应的模型单价或倍率，并开启“提示缓存计费”。




4. **生成客户 Token 并测试扣费**：
* 点击左侧【令牌】$\rightarrow$【添加令牌】，设置额度（例如 `$10.00`），生成一把 `sk-xxxxxx` 密钥。
* 在任意终端用这把 `sk-xxxxxx` 请求 **New API 的 3000 端口**：


```bash
curl http://127.0.0.1:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-你的NewAPI令牌" \
  -d '{
    "model": "qwen3.8-27b",
    "messages": [{"role": "user", "content": "用Python写一个快速排序，并简述时间复杂度。"}],
    "max_tokens": 2048,
    "stream": true
  }'

```


* 请求完成后，去 New API 后台点击【日志】，你会清晰看到这一笔请求的 **提示 Token、补全 Token（含 `<think>` 思考 Token）、首字耗时（TTFT）、生成速度以及扣减金额**——至此，你的全套 Docker 商业卖 Token 闭环已经 100% 跑通！



---

### 三、 后续进阶 1：在单卡 5090 上怎么做 Offload（3 种卸载实操）

当你熟悉了基础部署后，如果想在单张 32GB 的 5090 上把上下文开到满血 **262K 甚至 1M（100万）Token**，或者想强行在单卡上跑 **29GB 的官方 `Qwen/Qwen3.8-27B-FP8**`，vLLM 提供了 3 种立竿见影的 Offload 手段（只需修改 `docker-compose.yml` 中的 `command` 参数并执行 `docker compose up -d` 即可生效）：

#### 1. 视觉编码器卸载（`--language-model-only`）：白嫖 +50% 显存 KV 缓存池

* **原理**：`Qwen3.8-27B` 内置了一个 27 层的原生多模态视觉编码器（Vision Tower），在启动时会常驻显存并吃掉大量激活缓冲区。如果你的客户主要用它跑代码 Agent（如 Claude Code、OpenCode、Cursor 纯文本接口）而不需要看图/看视频，加上 `--language-model-only` 可以直接跳过加载视觉塔。


* **实测效果**：根据 vLLM 官方 Recipe 在单张 RTX 5090 上的实测，加上 `--language-model-only` 后，可用 KV 缓存池直接从 **91,022 Tokens 暴涨至 135,926–152,917 Tokens（扩容 +50% 以上）**！



#### 2. 模型权重 CPU 内存卸载（`--cpu-offload-gb`）：让 32GB 单卡跑动 FP8 大权重

* **原理**：如果你想在单张 5090 上测试官方 8-bit 的 `Qwen/Qwen3.8-27B-FP8`（权重约 29 GB），全放显存会导致没有空间留给 KV Cache。此时利用 vLLM 的 UVA（统一虚拟寻址）卸载器，通过 `--cpu-offload-gb 6` 将约 6 GB 的模型层权重卸载到宿主机 DDR5 内存中。


* **Docker 参数写法**：
```yaml
# 在 docker-compose.yml 的 command 中加入：
--cpu-offload-gb 6

```


* **代价与权衡**：开启权重 CPU Offload 后，每生成一个 Token 都需要通过 PCIe 5.0 总线读取那 6 GB 在内存里的层，单流生成速度（Tokens/s）会下降，因此仅在显存装不下模型权重（如跑 FP8）或追求超巨型 KV 池（如社区 `adrienbrault/qwen3.8-27b-rtx5090` 仓库用 `--cpu-offload-gb 1` 挤出 140 万 KV 池）时使用；跑 `NVFP4` 时无需开启。



#### 3. KV 缓存二级内存卸载（`--kv-offloading-backend native`）：把多轮对话历史缓存到 DDR5

* **原理**：卖 Token 给编程 Agent 客户时，客户经常有几十个会话同时挂着，每个会话都有几万 Token 的历史上下文。当单卡 5090 显存里的 KV 池满了之后，与其丢弃缓存重新计算（Recompute），不如将暂时不活跃的 KV 缓存块卸载到宿主机的 DDR5 内存中！


* **Docker 参数写法**（例如划拨 32 GB 系统内存作为二级 KV 缓存池）：


```yaml
--kv-offloading-backend native
--kv-offloading-size 32

```


* **真实踩坑预警**：社区开发者（`noonghunna/club-3090#1327`）在实测 `Qwen3.8-27B` 时发现，由于该模型包含 48 层 Mamba（Gated DeltaNet）线性注意力，其混合缓存块会被强制对齐为 **784 Tokens** 的大页；在部分旧版 vLLM（如 0.29）中同时开启外部投机器与 `native` KV Offload 会遇到“只写不命中”的限制，因此务必使用最新 `nightly` 镜像并通过 `/metrics` 监控命中率。



---

### 四、 后续进阶 2：如何把单卡 5090 的 `Tokens/s` 与 `TTFT` 优化到极致？

在单张 RTX 5090 上，不同参数配置下的 `Qwen3.8-27B` 性能差距可达 **3 到 5 倍**。以下是经过 Hugging Face 社区（`Discussion #132` 单卡 5090 深度调优帖）与 GitHub 实测（`fentz26/Qwen3.8-27B-5090`）验证的调优手册：

#### 1. 怎么优化 `Tokens/s`（生成速度：从 56 tok/s 冲刺到 123–304 tok/s）

| 优化阶梯 | 具体参数配置 | 单卡 5090 实测 Decode 速度 | 核心原理与注意事项 |
| --- | --- | --- | --- |
| **阶段 0：基础基线** | 无投机采样、`bf16` KV Cache | **~56.7–67.0 tok/s**

 | 受限于 27B 稠密模型每次迭代读取 ~22GB 权重的显存带宽

 |
| **阶段 1：开启 FP8 KV 缓存** | `--kv-cache-dtype fp8` | **~76.3 tok/s (+34%)**

 | 将 KV 读写带宽需求减半，且贪婪解码输出与 `bf16` 字节级一致

 |
| **阶段 2：激活内置 MTP 投机头**<br>

<br>*(已在上方 Compose 中默认为你开启)* | `--speculative-config '{"method":"mtp","num_speculative_tokens":3}'` | **~90.0–123.0 tok/s**

 | `Qwen3.8-27B` 权重自带训练好的多步 MTP 头（无需额外下载草稿模型）。**切记 `num_speculative_tokens` 设为 `3` 是甜点值**（设成 `8` 反而因验证开销导致降速）

 |
| **阶段 3：挂载外部 `DFlash2` 或 `DSpark` 扩散投机器（终极杀器）** | `--speculative-config '{"method":"dflash","model":"incoai/Qwen3.8-27B-DFlash2","num_speculative_tokens":6}'`<br>

<br>*(或使用 `RedHatAI/Qwen3.8-27B-speculator.dspark`)*

 | **单流 221–304 tok/s**<br>

<br>**16 并发总吞吐 579 tok/s**

 | `DFlash2` 是专为 `Qwen3.8-27B` 训练的 2.12 GB 块扩散草稿模型，在代码与工具调用上的接受率高达 **86%–95%**，比内置 MTP 再快 **45%–68%**，单 Token 耗电量直接减半！

 |
| **阶段 4：开启 SM120 专属线性层内核与精细 CUDA Graph** | `--linear-backend auto` (或 `flashinfer_b12x`) + `--cudagraph-capture-sizes 1 2 4 8 16 32`

 | **额外 +6% Decode 提速**

 | 启用 Blackwell `SM120` 线程束级 MMA FP4 GEMM；同时只捕获 `1~32` 常用并发尺寸的 CUDA Graph，既避免了 `--enforce-eager` 的降速，又省下了近 1GB 显存防 OOM

 |

(验证投机采样是否生效的方法：在宿主机执行 `curl -s [http://127.0.0.1:8000/metrics](http://127.0.0.1:8000/metrics) | grep spec_decode_num`，用 `accepted_tokens_total` 除以 `draft_tokens_total` 即可算出真实接受率，正常应在 0.75–0.90 之间。)

#### 2. 怎么优化 `TTFT`（首字延迟：压至 54 ms，消除长文卡顿）

在卖 Token 时，客户最敏感的体感指标就是 **TTFT（发出请求到吐出第一个字的时间）**。在单卡 RTX 5090 上将 TTFT 压到 **54 ms**，靠的是以下 4 项配置：

1. **开启前缀缓存并切换为 `xxhash` 极速哈希算法**：
* 在启动参数中加入 `--enable-prefix-caching --prefix-caching-hash-algo xxhash`。`xxhash` 比默认的 `sha256` 块哈希计算快得多（注：若镜像内未预装 `xxhash` 库，去掉 `--prefix-caching-hash-algo xxhash` 即可回退默认）。


* **必知的“784 Tokens 零命中陷阱”**：实测发现，因为 `Qwen3.8-27B` 的混合 Mamba 架构会将注意力缓存块大小填充对齐至 Mamba 页大小（**784 Tokens**），**如果你用来测试的前缀（System Prompt）短于 784 个 Token，前缀缓存命中率永远是 0%**！只有当共享前缀长度 $\ge 784$ Tokens（例如 1,000+ Tokens 的 Agent 系统提示词或多轮对话）时，缓存才会瞬间命中，让 60K 长文的 Prefill 速度达到 **6,260–12,500 Tokens/s**！


* **如何查看真实命中率**：不要看控制台周期打印的日志（低频测试下会被重置为 0），直接执行 `curl -s [http://127.0.0.1:8000/metrics](http://127.0.0.1:8000/metrics) | grep prefix_cache_hits_total` 查看累计命中 Token 数。




2. **调大单步预填充批次并设置长文分片阈值**：
* 默认的 `--max-num-batched-tokens` 只有 `2048`，遇到客户发来一个 10K Token 的代码文件时，需要分 5 个调度周期才能完成 Prefill。将其调大为 **`--max-num-batched-tokens 8192`**，同时配合 **`--long-prefill-token-threshold 1024`** 和 **`--enable-chunked-prefill`**，既能让中等长度 Prompt 一步算完，又能防止超长 Prompt 阻塞正在流式输出的并发客户。




3. **利用多模态图像缓存（Vision Cache）**：
* 当客户在多轮对话中反复携带同一张图片提问时，vLLM 会自动命中多模态编码缓存，跳过 27 层 Vision Tower 计算，单图预填充耗时直接从冷启动的 **1.01 秒降至 0.16 秒（提速 6.3 倍）**。




4. **治本之策：通过模板参数控制“体感 TTFT”（`reasoning_effort` 与 `preserve_thinking`）**：
* `Qwen3.8-27B` 出厂默认开启 `reasoning_effort: "xhigh"`（最高思考深度）。如果不加干预，用户问一句简单的话，模型先在后台默默思考几千个 Token，不仅把 `max_tokens` 预算吃光导致正文为空（`finish_reason=length`），还会让不支持展示思考流的客户端感觉“卡了十几秒才出第一个字”。


* 我们在上面的 `docker-compose.yml` 中加入了 **`--default-chat-template-kwargs '{"reasoning_effort":"medium","preserve_thinking":true}'`**：


* 将默认思考深度从 `xhigh` 下调为 `medium`（或 `low`），大幅缩短思考耗时；


* 保持 `preserve_thinking: true`，让模型在多轮 Agent 工具调用中复用上一轮的思考轨迹，避免每一轮都从头重复思考，从而同时提升 KV 缓存命中率与响应速度。







---

### 五、 附：用纯 Docker 一键对你的新服务跑压力测试

当你用 `docker compose up -d` 启动好整套服务后，同样**不需要在宿主机装任何测试工具**，直接运行下面这条 Docker 命令，拉起官方 `GuideLLM` 压测容器，对你本机的 `vllm-engine`（或 `new-api`）做一次全自动并发摸底，并在当前目录生成可视化网页报告 `benchmarks.html`：

```bash
docker run --rm -it \
    --network llm-cloud_ai-tier-net \
    -v $(pwd):/results \
    ghcr.io/vllm-project/guidellm:latest \
    guidellm benchmark run \
    --target "http://vllm-engine:8000" \
    --model "qwen3.8-27b" \
    --profile "sweep" \
    --max-seconds 60 \
    --data '{"prompt_tokens": 1024, "output_tokens": 512}' \
    --outputs "/results/benchmarks.json,/results/benchmarks.html"

```

*(注：`--network llm-cloud_ai-tier-net` 会让压测容器直接接入你刚才创建的 Docker Compose 内网，你也可以把 `--target` 改成 `"http://new-api:3000"` 并加上 `-H "Authorization: Bearer sk-xxx"` 来直接压测带网关计费的完整商业链路！)*