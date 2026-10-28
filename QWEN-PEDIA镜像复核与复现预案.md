# QWEN-PEDIA r10：镜像复核、社区反馈与复现预案

核验日期：2026-10-26。状态：研究与复现候选，未完整拉取镜像、未构建覆盖层、未运行目标 GPU。与全链条实施待审稿配套。

## 1. 当前结论

**r10 引用的 tag 查询失败，但原镜像可以按 digest 找回。现在有恢复原基础镜像的具体路径，无需先更换 vLLM 版本或重编整个 vLLM。**

此前的 `MANIFEST_UNKNOWN` 结果仍然成立；它仅说明 tag 无法解析。本轮从历史 Docker Hub 页面找到了镜像摘要，再向官方 Registry 查询，补齐了“镜像实体是否仍可获取”的证据。

| 对象 | 本轮结果 |
|---|---|
| 原 tag | `vllm/vllm-openai:nightly-eed1f3d0c6043bd494424a22443ee198dd56f657`，Registry 404 `MANIFEST_UNKNOWN`，Docker CLI 也失败 |
| 原镜像 index digest | `sha256:d0742e7e31b16c85c9e215960604452f5f172a522d35c94ca42b7030cb0afa36`，Registry 200；Docker CLI `manifest inspect` 成功 |
| AMD64 manifest | `sha256:b3862887f9cf239705c7908d9fe5367c0a42f5083b6d0a10ac15d9cea7438bec`，Registry 200 |
| 镜像构建标签 | `ai.vllm.build.commit=eed1f3d0c6043bd494424a22443ee198dd56f657`，与 r10 对应 |
| AMD64 config | `CUDA_VERSION=13.0.2`；created=`2026-09-12T05:22:06.323822817Z` |
| AMD64 镜像层 | 37 层，压缩大小合计 8,714,229,920 bytes，约 8.71 GB / 8.12 GiB；全部 HEAD 返回 200，Content-Length 与 manifest 一致 |
| PEDIA 成品镜像 | README 指示本地 `docker build`；`qwen-pedia/fnext-vllm:r10` 匿名查询返回 401，不能据此断言不存在，但没有查到可直接匿名拉取的公开成品 |

这些检查说明原基础镜像有很强的可获取性证据。完整下载并校验各层、容器内导入、CUDA kernel、模型服务和性能是后续不同层次的验收，不能合并成“已经跑通”。

摘要线索来自 [Docker Hub 历史镜像详情](https://hub.docker.com/layers/vllm/vllm-openai/nightly-eed1f3d0c6043bd494424a22443ee198dd56f657/images/sha256-9b61ee15612efed2b44bb38a8d83b19630162c975515d904b3449b09d16b3f14)。该页面展示 ARM64 的详情，但同时给出多架构 index；本轮通过 index 独立找出 AMD64 分支，没有把 ARM 镜像当作 x86 镜像。

原始 Registry 记录保存在 [核验资料/pedia_镜像恢复复核_2026-10-26.json](核验资料/pedia_镜像恢复复核_2026-10-26.json)，包含 index、AMD64 manifest/config 和所有层的 HEAD 结果。

## 2. 社区有没有反馈

**检索到了同一 commit 的相关反馈，没有找到 PEDIA 仓库直接讨论这个 tag 错误的 issue。** 仓库 issues 页面本轮显示 0，且限制创建 issue，因此没有 issue 不能解释为没人遇到问题。[PEDIA issues](https://github.com/abtraore/QWEN-PEDIA/issues)

在一篇单张 RTX PRO 6000 的实测帖中：

- 2026-10-03，有用户报告 Docker build 失败。
- 10-04，该用户进一步说明找不到镜像，认为 tag 改了，并给出 `cu129-nightly-eed1f3d0c6043bd494424a22443ee198dd56f657`。
- 该单卡项目的作者同日回复，相关改动已经合入，自己转用官方 nightly，并更新了 FP8 KV 等配置；这里的作者不是 QWEN-PEDIA 作者。

这是第一手讨论，可以证明当时有人遇到镜像解析问题并采用了另一条路线；它不是 PEDIA 作者的正式修复，也不是 4×5090 的等价替代验证。[原帖及评论](https://www.reddit.com/r/BlackwellPerformance/comments/1weapzh/qwen38flashnext_on_a_single_rtx_pro_6000_why/)

该作者的当前 [项目 README](https://github.com/WombatSoftware/vllm-qwen3.8-flash-next-rtx-pro-6000-sharp-monitoring#why-a-nightly) 明确说明：早期自定义镜像只覆盖 `kv_cache_utils.py` 中一个函数，用于解决跨请求前缀缓存复用被静默禁用的问题；上游 [#55390](https://github.com/vllm-project/vllm/pull/55390) 于 2026-09-22 合入后，这个覆盖已无必要，因此移除了 Dockerfile。这解释了该单卡项目为何能转回官方，不能据此推断 PEDIA r10 全部补丁已经合入。单卡还不涉及本项目 TP4 的跨卡通信问题。

该项目固定的官方 nightly 为 `18f8f960…`，本轮该 tag 同样返回 404，因此不能把“网上有人用过”写成“今天仍可按 tag 拉取”。对本商业项目，仍建议先使用本稿已固定的官方版本建立基线；若要复现原 r10，则优先使用已找回的原 digest，而不是随意更换基础镜像。当前官方与 r10 的逐项差异见[主稿 4.2](qwen3_8_flash全链条商业实施方案_待审稿.md#42-哪些优势现在可以吸收哪些仍要维护补丁)。

## 3. 替代版本如何选

补充复核已确定：把 r10 原覆盖层直接复制到本轮新官方版本存在 QSA 接口不匹配；只挑旧通信文件也有构造参数差异。原镜像 digest 恢复与向新版本移植是两件不同的工作，详见[差异和兼容性复核](QWEN-PEDIA_r10与官方nightly的差异和兼容性复核.md)。

| 路线 | 可获取性核验 | 适用判断 |
|---|---|---|
| **原 r10 的 CUDA 13 镜像，改用 digest** | 原 commit、AMD64 config、37 个 layer 均已核验 | **最优先的 r10 复现候选**；只修基础镜像寻址方式，最大程度保留原组合 |
| 同 commit 的 CUDA 12.9 版 | tag 404；历史 index `sha256:2ebb5d599fabc4874d41463a55308e9415751514546c7c1d6ee67ac02a9099d7`、AMD64 `sha256:5232080cca0e120d74eaf47a179e51b2ea62a79868f1c5b500455248bfed564b` 均返回 200；config 为 CUDA 12.9.1 | 只能作为独立候选；r10 的 SM12x FlashInfer GDN 分支要求 CUDA ≥13，换成 cu129 可能丢失关键 prefill 路径，不能承诺同速 |
| 2026-09-25 的 `29468dde…` | 社区 3090 recipe 固定 `sha256:c718e2d7402c7e0c3449e76b6c43a3c595406fbcba8da87de0fa17742b00aad5`；本轮该 digest 返回 200，而 tag 404 | 有另一套权重/硬件的服务证据，适合研究升级；旧 PEDIA 文件需逐项移植，不能整包覆盖后借用原成绩 |
| 本轮官方 `00b6c4c5…` | digest `sha256:76a9614ed4ed20694914c87e82a0344bd73e1c6e081459a2467175ab903657e4` 可查询 | 作为商业项目的官方基线 A，按现有原生功能调优；与恢复 r10 做同机对比 |

29468 来源：[另一作者的固定 Dockerfile](https://github.com/todiadiyatmo/rtx-3090-vllm-recipe-qwen-flash-next/blob/main/recipe/patch/Dockerfile)。此处只借用镜像身份和已有实验线索，不将 3090 的 TP2×PP2 与 W4A16 权重当成 5090 NVFP4 TP4 方案。

## 4. 具体恢复步骤——尚未执行的候选命令

先在目标服务器完整拉取原镜像；成功后记录本地 digest、平台和版本，再构建覆盖层：

```bash
docker pull --platform linux/amd64 \
  vllm/vllm-openai@sha256:d0742e7e31b16c85c9e215960604452f5f172a522d35c94ca42b7030cb0afa36
```

固定 PEDIA 源码：

```bash
git clone https://github.com/abtraore/QWEN-PEDIA.git
git -C QWEN-PEDIA checkout --detach ed7901322730a79473a1022de3d7a2496b70c63e
```

本项目已准备 [复现候选/PEDIA-r10.Dockerfile](复现候选/PEDIA-r10.Dockerfile)。它保留原 recipe 的 `COPY` 行，只把运行相关指令中的 `FROM` 改为已核验的原镜像 digest。以下命令从本文档所在目录执行，要求刚克隆的 QWEN-PEDIA 也位于当前目录：

```bash
docker build --platform linux/amd64 \
  -f ./复现候选/PEDIA-r10.Dockerfile \
  -t qwen-pedia/fnext-vllm:r10-recovered \
  ./QWEN-PEDIA/recipes/qwen3.8-flash-next
```

这是构建派生镜像，不是重编 vLLM 的 CUDA 二进制。构建完成后先检查 Python 实际包目录、依赖和覆盖文件 hash；原 recipe 把包目录写死为 Python 3.12 的 dist-packages，必须确认覆盖的是运行时实际导入的位置。

```bash
docker run --rm --entrypoint python3 \
  qwen-pedia/fnext-vllm:r10-recovered \
  -c 'import importlib.util, importlib.metadata as m; print(importlib.util.find_spec("vllm").origin); print({n:m.version(n) for n in ["vllm","torch","flashinfer-python"]})'

docker run --rm --entrypoint python3 \
  qwen-pedia/fnext-vllm:r10-recovered -m pip check
```

用单独的启动脚本副本引用 `r10-recovered`，不覆盖已有服务。先用本机私网/本地端口进行测试，保留权重 revision、计划表、环境和日志。最初先验证原生上下文内的较小请求；复现作者性能时再使用其完整 CTX、MTP、graph、KV、缓存和采样条件。减少上下文的冒烟成绩不能与作者 393216 配置直接比较。

生产环境还需接入鉴权与商业入口；原 launch 直接映射端口，不能把它原样当作已完成的收费部署。

## 5. 如果原 digest 后续也不可取

按以下顺序恢复，不默认把 FROM 改为当天 nightly：

1. 从可信的现成缓存/镜像归档恢复，核验原 commit、平台、config 和覆盖文件 hash。
2. 使用原 commit 的官方 x86_64 wheel 组装匹配环境。本轮 [固定 commit wheel 索引](https://wheels.vllm.ai/eed1f3d0c6043bd494424a22443ee198dd56f657/vllm/) 可读取；其 `vllm-0.1.1.dev50+geed1f3d0c` x86_64 wheel 的 HEAD 返回 200、309,840,435 bytes。只检查了索引/HEAD，没有下载或导入该 wheel。
3. 从 vLLM 原 commit 重建基础镜像，再应用 r10 overlay。原 commit 的 `docker/Dockerfile`、requirements 和 versions 文件本轮均可读取，并通过 Git 对象再次核对了 Dockerfile 与 CUDA requirements。
4. 若选择较新构建，按具体改动移植并重新验收，把它标为新的 profile。

仅固定 vLLM commit 不保证与原镜像逐字节相同：基础系统镜像、CUDA 构建参数、Torch/FlashInfer、依赖上下限和下载源都可能不同。例如本轮读取的该 commit Dockerfile 默认 CUDA 为 13.0.3，而找回的实际历史镜像 config 是 13.0.2。这也解释了为什么本轮优先用实际镜像 digest，而不是先源码重建。

## 6. 能否复现 GitHub 上的效果

**具备继续复现的具体条件；尚不能承诺作者的吞吐数字。** 找回原基础镜像使“同版本运行环境”的恢复明显更可行，但还缺目标机和完整测试。

需要分别通过三个层次：

| 层次 | 通过条件 |
|---|---|
| 环境恢复 | 原镜像完整拉取、overlay 确实生效、依赖与模型加载成功 |
| 功能复现 | 真实生成、thinking、工具、FP8 KV、MTP、长输入和多并发正确，启动/重启可重复 |
| 性能复现 | 同权重 revision、CPU/RAM/NUMA、PCIe/P2P、驱动、功耗、上下文、缓存、采样与负载，记录多轮 goodput 和延迟 |

尤其要验证 r10 的 custom AR/all-gather 在本机实际走哪条路径。作者代码注释明确依赖其机器已测得的 driver-level P2P；开一个环境变量不能让另一台机器自动得到相同通信能力。

作者公开记录的代码解码 319–331 tok/s 与 prefill 约 7800 tok/s，仍然是其环境的自报结果。较完整的软件恢复不等于速度保证；若本机结果不同，应保留日志、MTP 接受统计和 kernel/通信选择，定位差异，不以“启动成功”冒充复现成绩。

## 7. 新增 Gemini 建议为什么出现另一套数字

进一步搜索找到 [4×5060 Ti 的 hybrid-vmm-lru 项目](https://github.com/johnmosesventura06/qwen38-hybrid-vmm-lru)。它公开使用 `FN_EXT_DIR`、VMM/LRU 专家卸载、另一套权重及修改版 P2P 驱动，并报告 1745–2053 tok/s prefill、约 55–61 tok/s decode 和 33%–37% 的比较收益；还将一个可选 GDN 文件指向 PEDIA。

这说明新增 Gemini 建议把该项目的挂载机制、硬件和测试数字归到了 PEDIA r10 整套方案上。可以研究它的个别思路，但不能把这两个项目当成同一个实现，也不能把那组提升直接套到当前官方 vLLM 或你的 4×5090。
