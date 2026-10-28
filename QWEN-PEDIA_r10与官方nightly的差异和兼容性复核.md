# QWEN-PEDIA r10 与官方 nightly：后续改进、替代路径与兼容性复核

核验日期：2026-10-26。本文补充商业实施待审稿，仍未在 4×5090 上运行，不构成最终路线选择。

**官方也有 r10 没有的后续优化和修复；把 r10 整包覆盖到新官方，会丢失这些变化，并存在已经能够从源码确定的接口不匹配。** “官方的 skinny GEMM 计划表没有 SM120”仅指一个具体实现，不能理解成“官方没有 SM120 优化”，更不能把 r10 当成当前官方的功能超集。

## 1. 固定比较对象

| 对象 | 本次版本 |
|---|---|
| QWEN-PEDIA recipe | `ed7901322730a79473a1022de3d7a2496b70c63e`，r10 |
| r10 官方基础版本 | `eed1f3d0c6043bd494424a22443ee198dd56f657`，2026-09-12 |
| 本稿官方基线 | `00b6c4c565a8732c131e1f452d4a17803bb0842b`，2026-10-26 镜像所标构建 commit |
| 本稿官方镜像 index | `sha256:76a9614ed4ed20694914c87e82a0344bd73e1c6e081459a2467175ab903657e4` |

r10 的 Dockerfile 使用 `COPY image/vllm/ .../vllm/` 覆盖上游文件，没有执行能够保留新版本上下文的补丁合并。覆盖范围为 11 个已有 Python 文件，外加一个 tuner。11 个文件与本轮官方版本均不同；差异数本身不能证明谁更好。[原 Dockerfile](https://github.com/abtraore/QWEN-PEDIA/blob/ed7901322730a79473a1022de3d7a2496b70c63e/recipes/qwen3.8-flash-next/Dockerfile)

## 2. 官方有哪些独立能力或后续改进

### 2.1 通信：官方已有 PCIe IPC 方案，不能只看 CUSTOM 的限制

官方 [#53576](https://github.com/vllm-project/vllm/pull/53576) 于 2026-09-01 合入独立的 FlashInfer PCIe IPC all-reduce 路径，由 `VLLM_ALLREDUCE_USE_FLASHINFER_PCIE_IPC=1` 选择，默认关闭。该 PR 报告了 4×RTX PRO 6000、另一模型的端到端验证，不能直接当作本项目四卡 Qwen 的通过记录。

这条路径在 r10 基础版本及其覆盖的 `cuda_communicator.py` 中其实已经存在。因此应说“r10 默认没有启用”，不能说“r10 完全没有”。r10 的启动脚本未设置 PCIe IPC 开关，并将普通 FlashInfer all-reduce 的 `VLLM_ALLREDUCE_USE_FLASHINFER` 设为 0，启用自己的 PCIe custom AR 放开逻辑和小消息 all-gather 路由。这两个 FlashInfer 开关相互独立，不能用其中一个推断另一个的状态。[r10 启动脚本](https://github.com/abtraore/QWEN-PEDIA/blob/ed7901322730a79473a1022de3d7a2496b70c63e/recipes/qwen3.8-flash-next/launch.sh)

当前官方通信层还包含 r10 基础版本之后的 backend 选择、输出缓冲生命周期及 CUDA graph 内存适配。例如 [#58154](https://github.com/vllm-project/vllm/pull/58154) 修正 symmetric collective 返回值被后续 scratch 复用覆盖的问题；[#59160](https://github.com/vllm-project/vllm/pull/59160) 引入 cuMem graph pool 相关适配。它们各有生效条件，不能据此断言原 r10 默认配置必有这些问题。

**这些方案不是把速度加起来的插件。** 当前 `all_reduce` 会按输入、配置及设备条件选择一条路径；满足某个上游分支后，就可能先于 r10 的 CUSTOM 分支返回。多个开关同时打开可能使某个优化未被选中，也可能多分配 workspace。是否冲突、是否有收益，需要核对实际 dispatch 和内存，不能仅数启用了多少个环境变量。[当前通信实现](https://github.com/vllm-project/vllm/blob/00b6c4c565a8732c131e1f452d4a17803bb0842b/vllm/distributed/device_communicators/cuda_communicator.py)

之前提到的“超过两张 PCIe-only GPU 时关闭 custom all-reduce”，只限制其中一条实现，不能外推为“官方没有四卡 PCIe 优化”。同样，官方存在 MNNVL/NVLS 代码，也不能证明没有相应互联能力的机器能用它。

### 2.2 SM120：官方 QSA 有专用调优表，与 skinny GEMM 是不同部件

当前官方 `ops/qsa.py` 明确定义 `_select_sm120_config`，分别为 BF16、FP8 KV 和不同规模选择 QSA sparse attention 的执行配置。源码注释注明调优设备为 RTX PRO 6000 Blackwell。git 历史定位到 2026-09-16 的 [#55557](https://github.com/vllm-project/vllm/pull/55557)；r10 的旧 `ops/qsa.py` 没有这个函数。[当前源码](https://github.com/vllm-project/vllm/blob/00b6c4c565a8732c131e1f452d4a17803bb0842b/vllm/models/qwen4_exp/nvidia/ops/qsa.py)

该分支按 SM120 识别设备，5090 也可能走到它，但原调优设备与 5090 的频率、带宽、容量不同，不能承诺收益相同。若整文件覆盖回 r10，会丢失当前表及相关选择逻辑。

与之分别比较：本轮官方 `low_latency_gemm.py` 的设备计划映射仍未列 `(12, 0)`；r10 的 SM120 skinny GEMM 计划确有研究价值。两项结论可以同时成立。[当前 GEMM 实现](https://github.com/vllm-project/vllm/blob/00b6c4c565a8732c131e1f452d4a17803bb0842b/vllm/models/qwen4_exp/nvidia/low_latency_gemm.py)

### 2.3 官方改变了计算结构，旧 GEMM 表需要重新适配

2026-10-05 合入的 [#59533](https://github.com/vllm-project/vllm/pull/59533) 将 QSA QKVG 和 indexer QK 合并到一个投影中。源码的 TP4 计划形状由分开的 `3584×2560`、`640×2560` 变成 `4224×2560`；r10 固定的 SM120 JSON 没有 `4224x2560` 项。

因此，只带入旧计划表，不能覆盖这个新形状的调优；按现有查表逻辑可能回退普通 linear。若覆盖旧 QSA 文件来强行保留旧形状，则会撤掉新的融合，并可能与其余未覆盖文件不兼容。正确的移植方法是保留当前结构，为当前实际形状重新调优和验证。

其他已核实的后续变化包括：

| 合入日期 | 官方变化 | 与 r10 的关系 |
|---|---|---|
| 2026-09-14 | [PLE residual 与 QSA output gate 融合 #55309](https://github.com/vllm-project/vllm/pull/55309) | 在 r10 基础版本之后，不是 r10 原覆盖文件自动拥有的优化 |
| 2026-09-28 | [HC down projection 与 SiLU 融合 #58957](https://github.com/vllm-project/vllm/pull/58957) | 同上；收益仍需目标配置测量 |
| 2026-10-01 | [QSA pre-indexer 融合 #57097](https://github.com/vllm-project/vllm/pull/57097) | 将主 QK norm、RoPE、gate 和 KV 写入等合并；同时改变调用约定 |
| 2026-10-08 | [hybrid Mamba 前缀缓存边界一致性修复 #60533](https://github.com/vllm-project/vllm/pull/60533) | 涉及 coordinator 等多个文件；仅替换其中旧文件可能拆散成套变更 |
| 2026-10-20 | [PLE short conv 内部 prefill checkpoints #61601](https://github.com/vllm-project/vllm/pull/61601) | 涉及 PLE、GDN 及缓存配套代码；不能只依据“是否能启动”评估升级 |

这些事实支持“需要双向比较”。它们不能证明官方在所有负载下都比 r10 快，也不能把只有新路径才出现、后来才修复的问题倒推为旧路径本来就有。

## 3. 已确定的接口不匹配，而非泛泛提醒

### 3.1 整包覆盖：r10 QSA 调用与新官方 indexer 不匹配

r10 覆盖 `qsa.py`，没有覆盖 `indexer_qsa.py`。旧调用传入三个位置参数，按单个 selection 结果处理；当前官方 `QSAIndexer.forward` 增加必填的 keyword-only 参数 `attn`，返回 selection 和 main outputs 两项。

本轮用 AST 提取签名和调用，进行 Python 参数绑定，得到：

```text
missing a required keyword-only argument: 'attn'
```

这是静态接口验证，不是实际 vLLM 启动日志；它已经说明“新官方 FROM＋r10 原样 COPY”存在明确不兼容。原始 r10 在旧基础镜像上的调用双方是配套的，这个结论不否定原组合。[r10 调用方](https://github.com/abtraore/QWEN-PEDIA/blob/ed7901322730a79473a1022de3d7a2496b70c63e/recipes/qwen3.8-flash-next/image/vllm/models/qwen4_exp/nvidia/qsa.py)、[当前官方被调用方](https://github.com/vllm-project/vllm/blob/00b6c4c565a8732c131e1f452d4a17803bb0842b/vllm/models/qwen4_exp/nvidia/indexer_qsa.py)

### 3.2 只替换一个通信文件，也可能不兼容

当前官方 `CudaCommunicator` 构造 `CustomAllreduce` 时传入 `register_graph_buffers`；r10 的旧 `CustomAllreduce.__init__` 不接受这个参数。如果只替换旧 `custom_all_reduce.py`、保留当前调用方，参数绑定得到：

```text
got an unexpected keyword argument 'register_graph_buffers'
```

同时覆盖两个旧文件可以绕过这一个接口差异，但会撤回新版本的其他改进，且未解决 QSA 等文件之间的问题。因此“小范围移植”指移植少量经过适配的代码差异，仍然需要核对接口；不等于随意挑一个旧文件覆盖。[当前调用方](https://github.com/vllm-project/vllm/blob/00b6c4c565a8732c131e1f452d4a17803bb0842b/vllm/distributed/device_communicators/cuda_communicator.py)、[r10 旧类](https://github.com/abtraore/QWEN-PEDIA/blob/ed7901322730a79473a1022de3d7a2496b70c63e/recipes/qwen3.8-flash-next/image/vllm/distributed/device_communicators/custom_all_reduce.py)

机器可读的文件 hash、接口绑定与范围限制见[本轮记录](核验资料/r10_与官方差异及接口复核_2026-10-26.json)。未下载模型执行，也未构建混合镜像；不会把上述静态结论包装成四卡实测。

## 4. 实施顺序的具体调整

1. 先验收固定官方基线，再启用其原生优化。通信实验应包含独立的 FlashInfer PCIe IPC 候选，实际核对依赖、P2P、dispatch、graph 与 workspace；默认不开启，遇到不支持则记录回退路径。
2. 如果需要和原 r10 比较，按其原基础镜像 digest、原覆盖文件和固定权重恢复完整组合，分别调参，在相同质量、SLO 和稳定性条件下比较。
3. 只有观察到明确瓶颈，才考虑把 r10 剩余有价值的代码差异适配到新官方。SM120 skinny GEMM 应覆盖新融合形状；通信修改应保留当前接口与缓冲生命周期处理，逐项验证。
4. 不把“当前官方＋所有 r10 旧文件”列为可直接采用的组合。移植后的组合是新实验版本，不能沿用 r10 历史性能数字，也不能只以成功回答一次作为正确性验收。

当前推荐顺序仍是官方优先，r10 保留候选。理由包括后续融合、缓存修复和维护成本；最终性能选择由目标机测试决定。
