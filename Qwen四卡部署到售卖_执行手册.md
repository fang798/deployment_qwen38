# Qwen 四卡部署到售卖：新 agent 执行手册

版本：2026-10-28，按最新漫道云环境和权限边界修订。实际部署以本文件为入口；长篇研究稿按故障需要查阅。**用户没有 kubeconfig，不能随意操作其他应用、容器或镜像；本手册不要求获取 kubeconfig，也不依赖 kubectl。** 采用漫道云网页部署自己的应用，以已核实的只读 Python 接口复核，在自己的容器终端验收。

## 1. 任务、顺序和当前状态

**用户指定顺序：选定 4 张 RTX 5090 → 官方 vLLM 跑通 → New API、API 接入、计费支付、监控和压测全链路通过 → 再回来提升推理效率。** 官方失败时，先定位参数、版本、依赖、资源和通信，再参考其他开源项目或适配补丁。不先做 PEDIA 对比，不让可选优化阻塞商业链路。

当前已完成资料/源码核验，并取得[漫道云环境记录](漫道云部署环境核实记录与后续部署参考.md)，**没有目标 Qwen 的部署结果**。记录确认参考节点有 8 张 RTX 5090；用户进一步明确：**Gemma 后续会停止，再将其中四张卡分配给 Qwen。** 这是资源交接安排，尚非停机或分配已经完成的证据。Gemma 由用户后续关闭（或由其明确安排的现有应用负责人执行），交接四卡后部署独立的 `qwen38`；不覆盖 `gemma4`，不删除其模型数据，不占用其余四卡。下面镜像及参数仍为待实机验收的固定候选。

### 操作边界：先读本段

本次任务是更新文档，未授权执行平台写操作。后续部署工作以 `5090 / my-space` 中新建且确认归本项目的具体资源为范围：

| 对象 | 后续实施方式与边界 |
|---|---|
| Gemma | 用户之后在网页关闭；本手册不给自动停服命令，不编辑或复制覆盖 `gemma4`，不删除其镜像、Service 或模型文件 |
| Qwen 推理 | 新 Deployment/Service `qwen38`，临时下载应用 `qwen38-model-import`；名称如已存在，先核实归属，禁止覆盖同名他人对象 |
| 商业平台 | 新资源统一用 `qwen38-` 前缀，如 `qwen38-new-api`、`qwen38-postgres`、`qwen38-redis`、`qwen38-prometheus`；配置、Secret、卷和测试资源也登记具体名称，不因前缀相同就默认有权修改 |
| 操作通道 | 网页创建/修改已登记的自己的对象；只读 `query_mandao.py` 核对。接口清单里的 POST/PUT/PATCH/DELETE 只是定义，不启用自动写接口；`Master` 角色不扩大用户允许范围 |
| 共享设施 | 不修改 namespace 配额、节点/驱动、设备插件、RuntimeClass、PV/StorageClass、NFS 服务、已有仓库项目策略、共享 Secret 或其他模型；需要时交运维落实一个明确资源项 |
| Pod 内部 | 仅使用自己应用的终端、日志及已授权目录；不利用 ServiceAccount token、宿主 socket/根目录挂载或其他方式绕过平台边界 |

先在本地准备配置，再逐个在网页新建自己的资源；无对应页面权限时，把该资源的名称、配置和检查项交运维创建，继续不依赖它的工作。无需为了这套流程索取集群管理权限。

执行 agent 每完成一阶段，更新本节并保存证据。不得把“计划做”“容器 running”“模型分片加载完”标为通过。参数和代码修复可自主推进；缺四卡分配、平台部署权限、域名、支付账号、商业许可等外部条件时，明确列出缺项，继续不依赖它的本地工作。凭据不写进报告。

| 阶段 | 状态：未开始/进行中/通过/受阻 | 通过日期和报告路径 |
|---|---|---|
| P0 平台核实、Gemma 停服交接与四卡分配 | 进行中 | 已取得环境记录及四卡交接安排；实际停服、资源分配和新 Pod 验证待完成 |
| P1 官方 vLLM 真实推理 | 未开始 | |
| P2 New API 与客户 API 接通 | 未开始 | |
| P3 计费、充值和异常结算 | 未开始 | |
| P4 监控、压测、稳定性及恢复 | 未开始 | |
| P5 受控售卖与交接 | 未开始 | |
| P6 全链路通过后优化推理 | 未开始 | |

项目配置保存在本机/构建机有权限的目录，至少包含 `profiles/`、`reports/`、`logs/`、`platform/k8s/` 和 `tests/`；密钥只放受保护的存储或公司 Secret 系统。GPU Pod 内 `/models`、`/runtime-cache` 是实际挂载目录，容器里新建 `/srv/qwen` 不会自动获得持久性。本机目录、宿主机目录、Pod 内路径必须分别记录。每次汇报写清当前阶段、实际结果、证据路径、阻塞和下一步。

## 2. P0：平台核实、交接并分配四卡

### 2.1 最新证据与原方案变化

依据[环境记录](漫道云部署环境核实记录与后续部署参考.md)及其链接的 2026-10-28 只读响应；参考应用的资源上限不自动成为新 Qwen 的配额。

| 已确认 | 本项目处理 |
|---|---|
| 当前 API 文档 `http://10.254.127.231/doc.html`；GET 已成功查询 `cluster=5090`、namespace=`my-space`；返回角色 Master | 删除旧“5090 名称被拒、需改名”的前提；GET 成功不证明任何写权限或写操作授权 |
| 节点 `node01`，IP `192.168.79.152`，标签 `kubernetes.io/hostname=node01`；节点 allocatable GPU=8 | 模板绑定已核实标签；8 是可分配总量，非当前空闲量。用户停止 Gemma 后仍要复核四卡交接 |
| 8×5090、SM120；同 NUMA 为 NODE、跨 NUMA 为 SYS，无 NVLink 记录 | 申请四张独占卡，优先同 NUMA；标准数量请求不指定 UUID，也不保证同 NUMA，分配后核对实际结果 |
| 双路 Xeon Gold 6530、128 线程、约 503GiB RAM；Gemma 上限 16 核/256GiB | 新服务首轮申请 16 核、256Gi、四卡，以新 Pod limits/cgroup 为准 |
| 驱动 595.91.07；Gemma vLLM 0.18.2 开发版、Torch cu129 | 继续使用本项目固定官方候选，另验 CUDA/SM120/Qwen；不升级或修改 Gemma 镜像 |
| 模型存于 node01 的 NVMe hostPath；观察可用约 3.2T，系统盘可用约 301G | 优先申请独立 Qwen NVMe 子目录并只挂该目录；不能把共享盘容量或另一块 NVMe 当作项目已获配额 |
| `nfs-sc` 为 Immediate/Delete、archiveOnDelete=false；已有 100Gi PV 绑定 `nfs/nfs-pvc` | 不借用现有 NFS PV，不把 RWX 或存储类名称当作已验证共享/保留能力；本轮不用它作默认模型/账务卷 |
| vLLM、Triton、CUDA、TorchInductor 四类磁盘缓存目前均非持久化；shm 为磁盘型 emptyDir | 新 Qwen 模板先用可重建的临时磁盘缓存，持久化仍待决定；`/dev/shm` 单独改内存型候选，不改 Gemma |
| `gemma4-svc` 已用 NodePort 32003；另两个已有 Service 使用 32001/32002；Ingress/NetworkPolicy 查询为空 | 原 Service 全部保留。Qwen 默认内部 ClusterIP；网页无转发也能在自己的 Pod 内测。空列表不证明全局没有入口/策略 |
| 可查询 7 条仓库记录，包括 `dockerhub.mandao.com` 等 | 尚无本项目 Harbor 项目/push/节点拉取与保留验证，不能仅凭地址直接推送或覆盖仓库内容 |

### 2.2 交接和准备顺序

1. **先准备，后停服。** 本地完成镜像/参数清单、网页字段表和验收脚本；在项目获准后完成独立模型导入。Gemma 的停止由用户之后执行，只有网页/只读状态确认其已停止、旧 Pod 退出且资源释放后，才视作交接完成；只 kill 进程可能触发重启。保存其原配置用于用户需要时恢复，不改动它的数据。
2. 确认四张独占整卡和新应用额度。标准整卡资源为 `nvidia.com/gpu: 4`；时间切分/虚拟资源如有，先核对实际策略，不把四个份额当四张物理卡，不人工覆盖 `NVIDIA_VISIBLE_DEVICES` 绕过分配。
3. 首轮申请候选：CPU request/limit **16/16**，内存 **256Gi/256Gi**，四卡，至少 **500GiB 项目可用工作空间**（权重、缓存及版本余量，节点镜像空间另外核对），shm 上限 **16Gi**。模板另设临时存储 request=16Gi、limit=64Gi 作为待核准候选。256Gi 包含进程、PLE、文件缓存和 tmpfs；这些申请不是已分配事实，不照抄 Gemma 的低 request。
4. 优先由运维在 `node01` 已核实 NVMe 上划定一个项目专属目录，提供**实际宿主路径、权限、容量与开机挂载保证**。没有宿主权限就由运维建立目录，不把 `/root/.cache/modelscope`、`/root/.cache/huggingface` 整体以可写方式挂给自己，不在 Gemma 终端创建目录或下载模型。平台只允许 PVC 时，改为公司供给的项目独立 PVC；不创建/改造共享 PV、StorageClass 或 NFS 服务。
5. 选定一个有授权的 Harbor 项目，在构建机同步固定镜像，创建项目专用拉取凭据引用 `qwen38-imagepull`（若确需认证）。不编辑 `myregistrykey`，也不读取其内容；只有运维明确允许复用时才在自己的应用中引用。原仓库 digest、公司仓库 manifest digest、构建 commit 和实际 Pod imageID 分别记录，imageID 不直接当可拉取 manifest digest。
6. 仅在自己的应用里选择 `node01` 和已允许的运行时选项；若需要标签/taint/设备策略变更，交运维核实，不自行改节点。四卡同 NUMA 为优选，平台不能保证时先记录实配并验通信，不因此扩大权限。

### 2.3 没有 kubeconfig 时怎么检查

**本机只读接口**：运行已核实脚本，输入当前门户同次登录的 token/userId；集群直接填 `5090`，namespace 填 `my-space`。启动 Qwen 后将交互中的 Deployment 从默认 `gemma4` 改为 `qwen38`，查询自己的 Deployment 和对应 Pod；看 Gemma 停服状态时仍只读查询其原名称。

```bash
# 本机终端，交互输入凭据，不写入命令行；此脚本只 GET。
python3 /home/user/xu_fang/work/deployment/query_mandao.py
```

脚本当前默认 14 项 GET，并自动设置网关路由头；它查询了集群级元数据但不会修改集群、不读 Secret 内容。它不支持直接自动发布。配额仅在知道真实对象名时用 `--resourcequota-name`，不猜名、不重复调用已确认不支持的通用 resourcequotas/limitranges/endpointslices。9 项有数据、5 项空列表是观察值，空列表不证明资源全局不存在。凭据错误停止，不能把 HTTP 200 单独当成功。

**网页**：在 `5090 → my-space` 仅打开自己的新应用详情，记录资源、挂载、镜像、Pod、启动日志和就绪情况；页面没有事件详情时保存可见错误并交运维查单个对象。不要搜索并批量操作同 namespace 的所有对象。

**自己的新 Pod 网页终端**：执行下面的只读检查；工具缺失时用容器可用工具或只读接口补证，不为检查去改 Gemma：

```bash
nvidia-smi
nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.used,driver_version,pci.bus_id --format=csv
nvidia-smi topo -m
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/memory.max
ulimit -l
findmnt -T /models
findmnt -T /runtime-cache
findmnt -T /dev/shm
df -h /models /runtime-cache /dev/shm
```

以上沿用已观察的 cgroup v2。Pod 内输出可能看不到其他容器进程；CPU/内存预算以本 Pod cgroup 为准，Gemma 释放由平台状态和必要的运维节点证据交叉确认。不读取 Pod 的 ServiceAccount token 或将其转换为 kubeconfig。

**通过：** 用户已停 Gemma，四卡交接完成；自己 Pod 可见四个不同 UUID，运行资源和目录符合已获分配；镜像可拉取、驱动能运行其 CUDA。资源或目录仍缺时列明具体依赖，继续本地准备，不假装 P0 通过。

## 3. P1：先用官方 vLLM 跑通

### 3.1 固定版本和准备

| 对象 | 首轮候选 |
|---|---|
| 镜像 | `vllm/vllm-openai@sha256:76a9614ed4ed20694914c87e82a0344bd73e1c6e081459a2467175ab903657e4` |
| 该镜像 AMD64 构建 commit | `00b6c4c565a8732c131e1f452d4a17803bb0842b` |
| 权重 | `nvidia/Qwen3.8-Flash-Next-NVFP4` |
| 权重 revision | `fc694b54fb0174e0913e6adf86691ef85a4ead47` |

先重新验证镜像可拉取。拉取后记录容器内 vLLM、Torch、FlashInfer、CUDA 版本和 `vllm serve --help`，检查命令兼容。若候选失效或有明确问题，可选择另一官方固定版本，记录原因和新 digest；不使用浮动 `latest/nightly` 当作可复现版本。

在本机/构建机同步镜像至**本项目有权限的 Harbor 项目**，不碰其他镜像 tag/清理策略；必要补丁做新 tag/digest 的派生镜像，不原地覆盖 `gemma4`。发布前记录公司仓库实际 manifest digest。只读查询到仓库地址不等于已有推送权限；若平台允许且节点可直连，也可直接引用表中官方 digest，不假定旧镜像代理适用于新仓库。

权重放 `node01` 上**已授权的独立 NVMe 模型目录**，由自己的临时导入应用 `qwen38-model-import` 挂为 `/models` 并仅写此处。导入应用 GPU=0，不借 Gemma 终端；其固定镜像提供 HF CLI，资源足以校验文件且不抢推理四卡，实际创建能力由网页核实。平台不支持临时应用/无下载网络时，交运维把在构建机核验过的文件导入同一目录，不绕过权限。

```bash
# 仅在自己的模型导入应用终端执行，目录已获授权且挂载正确。
hf download nvidia/Qwen3.8-Flash-Next-NVFP4 \
  --revision fc694b54fb0174e0913e6adf86691ef85a4ead47 \
  --local-dir /models/nvidia-fc694b54
```

核实不是 LFS pointer，索引引用分片齐全；本 revision 共 11 个 safetensors，合计 132,680,249,378 bytes，保存 hash。导入完成停止自己的导入应用并结束写入，再以只读模型目录启动推理。若改用 PVC，额外核对供给、访问模式、节点及删除保留规则；当前已有 100Gi NFS PV 既被占用，容量也小于本模型权重文件总量，不能直接当作本项目模型卷。

PLE 约 47.68GiB 是 FP8 文件表的量级，仍需核实实际加载/复制和主机内存峰值。网页创建自己的 Secret `qwen38-vllm`，含随机 `api-key`，从受保护输入传入；后端 Key、客户 New API Key 和平台 token 是不同凭据。模型只读持久存储与编译缓存是否持久化分别决定：本模板先使用临时磁盘缓存，持久化并非用户已作出的决定，见 3.2。

### 3.2 首次启动：漫道云 Deployment 与内部 Service

下列为**供漫道云网页逐项填写或在页面支持时导入的候选配置**，本地保存为 `platform/k8s/qwen38.yaml`；YAML 是配置载体，不要求 CLI 提交。平台是否支持多对象导入尚未验证；不支持时把 Deployment 和 Service 分别创建，不能假设存在某个按钮或批量 apply 功能。

创建前先确认新名称未被他人使用、独立宿主模型目录已存在且装好权重、资源额度获准、Secret 创建/引用方式可用。替换公司镜像地址和宿主目录占位符。`node01` 标签来自已读节点响应，发布时再核对；模板不创建 Namespace、PV、StorageClass、RBAC 或其他全局对象。平台禁止 hostPath 时改用经公司验证的项目 PVC，不自行放宽策略。

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: qwen38
  namespace: my-space
spec:
  replicas: 1
  strategy:
    type: Recreate
  progressDeadlineSeconds: 2400
  revisionHistoryLimit: 3
  selector:
    matchLabels:
      app: qwen38
  template:
    metadata:
      labels:
        app: qwen38
    spec:
      nodeSelector:
        kubernetes.io/hostname: node01
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 120
      imagePullSecrets:
        - name: qwen38-imagepull
      containers:
        - name: vllm
          image: COMPANY_REGISTRY/PROJECT/vllm@sha256:REPLACE_WITH_VERIFIED_DIGEST
          imagePullPolicy: IfNotPresent
          command: ["vllm", "serve"]
          args:
            - /models/nvidia-fc694b54
            - --served-model-name
            - qwen3.8-flash-next-nvfp4
            - --host
            - "0.0.0.0"
            - --port
            - "8000"
            - --tensor-parallel-size
            - "4"
            - --enable-expert-parallel
            - --distributed-executor-backend
            - mp
            - --quantization
            - modelopt
            - --moe-backend
            - marlin
            - --engram-config
            - '{"cpu_offload":true}'
            - --language-model-only
            - --gpu-memory-utilization
            - "0.90"
            - --max-model-len
            - "32768"
            - --max-num-seqs
            - "16"
            - --max-num-batched-tokens
            - "2048"
            - --kv-cache-dtype
            - fp8
            - --attention-config.indexer_kv_dtype
            - fp8
            - --enable-prefix-caching
            - --enable-prompt-tokens-details
            - --reasoning-parser
            - qwen3
            - --enable-auto-tool-choice
            - --tool-call-parser
            - qwen3_coder
            - --enable-force-include-usage
            - --disable-custom-all-reduce
            - --enforce-eager
          env:
            - name: VLLM_API_KEY
              valueFrom:
                secretKeyRef:
                  name: qwen38-vllm
                  key: api-key
            - name: VLLM_CACHE_ROOT
              value: /runtime-cache/vllm
            - name: TRITON_CACHE_DIR
              value: /runtime-cache/triton
            - name: CUDA_CACHE_PATH
              value: /runtime-cache/cuda
            - name: TORCHINDUCTOR_CACHE_DIR
              value: /runtime-cache/inductor
          ports:
            - name: http
              containerPort: 8000
          resources:
            requests:
              cpu: "16"
              memory: 256Gi
              ephemeral-storage: 16Gi
              nvidia.com/gpu: 4
            limits:
              cpu: "16"
              memory: 256Gi
              ephemeral-storage: 64Gi
              nvidia.com/gpu: 4
          volumeMounts:
            - name: model
              mountPath: /models
              readOnly: true
            - name: runtime-cache
              mountPath: /runtime-cache
            - name: shm
              mountPath: /dev/shm
          startupProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 180
          readinessProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 30
            timeoutSeconds: 10
            failureThreshold: 5
      volumes:
        - name: model
          hostPath:
            path: /REPLACE_WITH_APPROVED_QWEN_NVME_DIRECTORY
            type: Directory
        - name: runtime-cache
          emptyDir:
            sizeLimit: 32Gi
        - name: shm
          emptyDir:
            medium: Memory
            sizeLimit: 16Gi
---
apiVersion: v1
kind: Service
metadata:
  name: qwen38
  namespace: my-space
spec:
  type: ClusterIP
  selector:
    app: qwen38
  ports:
    - name: http
      port: 8000
      targetPort: http
```

网页填写和复核顺序：

1. 在 `5090 / my-space` 新建自己的 `qwen38` 无状态应用，核对名称无冲突；填固定镜像、`vllm serve`、args、环境变量、node01、资源、挂载、探针与 Recreate。发布前复查只涉及这个新应用；平台把 command/args 合并为单个启动字段时保持参数语义，不能保留 Gemma 的启动命令。
2. 为新应用引用项目自己的 `qwen38-vllm` 和必要的 `qwen38-imagepull`；若网页无 Secret/节点约束/挂载/探针等字段，把缺少的**单项配置**交运维落实到本项目应用，不靠扩大权限补齐。无认证拉取时可以删除 imagePullSecrets 项；不读取共享 Secret 内容。
3. 新建内部 Service `qwen38`，selector 仅匹配 `app=qwen38`，port/targetPort=8000。既有 `gemma4-svc`、`qwen3-vl-32b-*`、`mimo-v2-flash-*` 原样保留，不把它们改指自己的 Pod。ClusterIP 地址由平台分配，不手填旧服务 IP。
4. 网页查看新 Pod、启动日志和就绪状态；用 2.3 的 GET 脚本核对 `qwen38`，保存 actual imageID、nodeName、volumes、resources；确认四卡不同 UUID。页面能力缺失/Pod Pending 时先查资源、目录、拉取和平台注入，不把它们当 kernel 错误。
5. 在**自己的 qwen38 Pod 网页终端**先测 localhost 和内部 Service，见 3.3。此时不需要外网入口、本机直连 Pod IP 或命令行转发；外部 SDK 走 P2 建好的 New API HTTPS 入口。

模板使用标准整卡插件；平台资源名不同则核实后改。模型 hostPath 只挂**已授权的独立目录**，`type: Directory` 要求其存在，不用 DirectoryOrCreate 在未知盘上自动建空目录。不能用容器中的 NVMe 子目录名推定宿主路径，也不授予宿主根目录/整个共享缓存的访问。替代 PVC 时仅引用项目独立卷；不借用 `nfs-server-local-pv`，不修改 `nfs-sc` 的 Delete 或 archive 设置。

**缓存暂存方案不是已决定持久化。** 四类缓存通过候选环境变量指向 `/runtime-cache` 下不同目录；在固定镜像中核实变量和 worker 日志实际路径。[vLLM 缓存路径变量](https://docs.vllm.ai/en/latest/configuration/env_vars/)仅证明相应版本机制，不能替代固定镜像核对。临时磁盘 emptyDir 上限先取 32Gi，计入节点临时存储；同 Pod 容器重启可保留，Pod 删除/重建会丢失并重新编译。新 Pod 首轮临时存储 request/limit=16Gi/64Gi 也需平台核准，留出日志/overlay 余量；上限不是独占预留，不能依赖它避免节点磁盘不足。后续用户选持久化时再把缓存卷换成自己的独立 NVMe 目录/合格 PVC，按模型、运行时和硬件隔离，并重测冷启动；不因此修改 Gemma 四类缓存。

`/dev/shm` 独立用 16Gi 上限内存型 emptyDir，计入 256Gi 内存而非上述磁盘额度；它不是 PLE 配额。模板关闭自动挂载 ServiceAccount 凭据，推理不需要 Kubernetes API 权限；不申请 hostIPC、特权模式或宿主 Docker socket。检查 memlock；旧 Docker 的 `--ulimit` 没有同名 Pod 字段，确有分配错误时由运维按工作负载配置解决，不擅自加集群权限。

先在自己的镜像中核对 `vllm serve --help`。startupProbe 首轮容许约 30 分钟初始化、进度期限 40 分钟均为候选，按含缓存重建的冷启动实测收紧；`/health` 的返回和鉴权行为先确认，探针不硬编码服务密钥。探针成功不等于真实推理成功。本阶段不开 MTP、YaRN、PEDIA 或通信专项优化；保留实际 backend 日志，不因 Gemma 的非致命提示就叠环境变量。

更新只在自己 `qwen38` 的网页配置中进行，保留旧镜像 digest、参数和模型 revision。Recreate 会中断唯一副本，维护前由自己的网关停止新准入、排空请求并处理账务；120 秒终止宽限不保证所有长请求完成。未有可用备用四卡时，不改滚动策略来假装实现无中断；回滚也仅操作本项目应用。停服/重建验收不涉及其他应用或共享宿主重启。

### 3.3 怎么测、何时进入 P2

建立 `tests/smoke.py`，从受保护环境读取 Key，记录响应/usage/耗时和断言结果，只用合成测试内容。先在自己的 qwen38 网页终端测试 `http://127.0.0.1:8000/health`、带认证的 `/v1/models`，再发真实请求；curl 不存在时使用该镜像的 python3 标准库做等价请求。以下读取自己 Pod 已注入的后端 Key，不打印：

```bash
QWEN_INTERNAL_KEY="${VLLM_API_KEY:?本应用必须已注入后端密钥}"
curl --fail-with-body http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer $QWEN_INTERNAL_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-flash-next-nvfp4","messages":[{"role":"user","content":"只回答19乘23的结果"}],"chat_template_kwargs":{"enable_thinking":false},"max_tokens":128,"temperature":0}'
```

`QWEN_INTERNAL_KEY` 仅在自己的 Pod 中从环境安全加载；curl JSON 中不包 SDK 的 `extra_body`。然后使用 `http://qwen38.my-space.svc:8000` 在自己的测试应用/New API 容器复测服务路由与非流式/SSE；容器 localhost 只证明本 Pod 监听。初始可在 Qwen 自己的终端复测 Service，跨 Pod 连通在 P2 再验。

默认不为推理暴露 NodePort。若后续本机确需直连压测且平台没有可用私网代理，申请**自己的独立 NodePort Service**，让平台分配端口并只开放给测试机/网关；必须先有访问控制，不能直接把后端暴露给客户。不得复用 32001/32002/32003 或修改既有 Service；节点 IP 上可达性要实际验证，无需该入口时不创建。正式客户始终走 New API。

| 测试 | P1 通过标准 |
|---|---|
| 中文、英文、代码、固定答案 | 合计至少 20 个预设用例全部通过；固定答案 437，代码案例有实际可执行断言，不只看返回 200 |
| 非流式、SSE 流式 | 都能完成；流有增量、终止事件及可信最终 usage；拼接内容符合用例 |
| 快速/思考 | 快速显式 `enable_thinking=false`；思考显式 `reasoning_effort=medium`；结构正常，无反复重复至截断；不能把模板默认当 medium |
| 工具调用 | 至少 3 个确定性用例返回可解析名称/JSON 参数，并接回合成工具结果完成下一轮 |
| 鉴权及边界 | 错 Key 的推理请求被拒；超长、无效模型/参数返回明确错误且后端仍健康 |
| 重复运行 | 至少连续 30 次合成请求无崩溃/OOM；记录每卡显存、主机内存峰值、实际模型及配置 |

**满足上表就进入 P2，不先追求最高 tok/s。** 此时记录基础延迟供后续比较，但不承诺售卖容量。P4 前可继续使用 eager 基线。

### 3.4 官方失败时的处理顺序

保存完整错误、首次出错阶段、版本和资源峰值；每次只改一个主要变量，报告改动和结果。

| 症状 | 先排查与行动 |
|---|---|
| Pod Pending/挂载/拉取失败 | 先看自己应用网页中的错误/事件及只读响应，核对四卡额度、独立宿主目录/PVC、node01约束、允许的运行时选项、仓库和拉取Secret；页面无诊断时交运维查这个对象；这些不是 vLLM kernel 错误 |
| CLI/配置不识别 | 检查固定镜像实际 help、模型类型和参数位置；修订整份 profile，不胡乱叠环境变量 |
| 模型加载失败 | 核对 revision、分片完整性、ModelOpt/FP8 PLE loader、宿主内存及 PLE offload |
| OOM | 区分主机、权重、MoE workspace、KV、graph 阶段；先降并发、批 token 和上下文，再合理调内存预算，不无限抬显存利用率 |
| 后端/kernel 不支持 | 按 SM120、量化格式、TP4/EP 形状核实可用后端；留在 eager、无 MTP 条件下缩小问题 |
| 跨卡卡住/报错 | 核对四卡 UUID、拓扑、P2P 和实际 backend；逐项验证回退 NCCL 等配置。不要默认禁用 P2P，也不安装来历不明驱动 |
| 能生成但工具/输出异常 | 核对 chat template、parser、thinking、缓存及采样；不能把“有输出”当作模型正确 |

官方仍无法通过时，查对应版本上游 issue/修复，再考虑匹配版本的补丁或完整社区运行时。参考顺序为明确修复 → 最小适配 → 原版 PEDIA 等独立组合。不得把 r10 原文件整包覆盖当前官方；已有明确接口不匹配。每种修复都要重跑 P1。PEDIA 细节仅此时查[镜像恢复预案](QWEN-PEDIA镜像复核与复现预案.md)和[兼容性复核](QWEN-PEDIA_r10与官方nightly的差异和兼容性复核.md)。无明确诊断的重复试跑不能代替排障。

## 4. P2：接通 New API、HTTPS 和客户 SDK

目标拓扑：**客户 → HTTPS → New API → qwen38 四卡实例**；New API 配 PostgreSQL、Redis，增加 Prometheus/Grafana 和告警。首版不加 LiteLLM/Dynamo，不开放未经验证的视觉、Responses/Anthropic 转换。

执行步骤：

1. 经漫道云网页分别新建登记的本项目组件，New API Deployment/Service 使用 `qwen38-new-api`，Redis 使用 `qwen38-redis`；全部不申请 GPU。选择并固定 New API 发布及镜像 digest；以该发布官方 Compose 的配置项为参考，转成 `platform/k8s/` 下独立 Deployment、ClusterIP Service、Secret/ConfigMap 和持久卷；不在推理容器里启动 Compose。数据库优先接公司为本项目提供的独立库/账号；没有现成服务时在网页允许范围内新建 `qwen38-postgres` 及独立持久数据卷，缺少创建能力则交运维创建这个组件并完成备份恢复。不能把临时磁盘缓存策略用于订单/余额数据库，也不默认将 Delete 型 `nfs-sc` 用于账务。Redis、入口、监控同样固定版本、独立资源。初始化管理员，随机 secrets、健康检查、持久数据和备份目录齐全，数据库/Redis 不对公网开放。
2. New API 上游指向 `http://qwen38.my-space.svc:8000`（DNS 实际解析需验证，同 namespace 可用 `http://qwen38:8000`），不能使用临时 Pod IP 或本机调试地址。核实所选版本 Base URL 的 `/v1` 拼接规则。若网关部署在集群外，另用公司批准的私网访问入口，不假定集群 DNS 在外部可用。
3. 后端 Key 仅由网关使用；客户获得独立 New API Key。首发外部 alias 用 `qwen-flash`，映射到内部 served-model-name；默认快速档、`n=1`，先限制总上下文 32K、最大输出 4096、每 Key 并发 1。限流值由 P4 收紧或放宽。
4. 在服务端强制模型、长度及 thinking 策略；客户不能靠参数绕过。首发仅开放已验收快速档；思考档独立通过功能和账务测试后再开放。平台不支持必要策略时补最小适配或缩小产品范围。
5. 当前 Ingress 查询为空，不假设已有入口控制器。优先由公司为自己的 `qwen38-new-api` 提供 HTTPS 域名/反代；若平台采用 NodePort，则为此新网关创建自己的 NodePort 并登记平台分配端口，再由公司私网入口/TLS 反代转发；不改现有 Service/Ingress，也不自行修改共享负载均衡。按实际控制器落实 SSE 不缓冲、读写超时、取消传递和出流后不透明重试，不直接照搬宿主 Nginx 指令。vLLM 仅设 ClusterIP。仅创建 selector 指向本项目 Pod 的 NetworkPolicy（页面允许且 CNI 支持时）或由运维提供等价访问控制，不对整个 my-space 下发默认拒绝；允许 New API 访问推理、Prometheus 访问指标及必要的健康检查，限制其他来源；ClusterIP 本身不是鉴权或网络隔离。验证 CNI 的策略支持，验证受限客户端不能绕过 New API；管理页面限制访问。
6. 建立 `tests/gateway.py`，将 P1 用例走客户 HTTPS 入口再测一次；用实际 OpenAI SDK 分别调用非流式和流式，验证模型 alias、tools、usage 和错误码。

**通过：** 新账号取得客户 Key 后可经 HTTPS 真实调用 Qwen；无 Key/错 Key/越权模型被拒；SSE 持续输出；参数限制不可绕过；SDK 样例可直接执行；能用 request_id 串起入口、网关及可获得的后端记录。后端未提供同 ID 时维护明确映射，不声称仅加 Header 就完成追踪。

## 5. P3：计费、充值和异常结算

先在沙箱和测试账户做闭环，再接生产支付。New API 是唯一客户余额账本，Redis 不能代替账本。内部压测账号和流量单独标记。

操作：核对所选 New API 实际预扣/结算实现，配置固定价格版本及舍入规则；输出含 reasoning 时避免重复相加，MTP 被拒 draft 不额外收费。首发缓存 usage 未验证前使用统一输入价。不得假定默认配置已防并发透支或已正确处理断流。

建立 `tests/billing.*` 和可重放的支付测试，逐项自动断言：

| 场景 | 必须达到的结果 |
|---|---|
| 正常、流式、工具、思考 | 手算费用、最终 usage、请求账单、余额差额一致；每笔记录价格版本及计量来源 |
| 金额校准 | 测试价输入 1 元/百万、输出 4 元/百万时，用实际 usage 计算 `(I×1+O×4)/1e6`；舍入符合约定。固定 usage 的模拟测试只验证账务，不替代真实 Qwen 验收 |
| 余额不足与并发争抢 | 拒绝超额请求；无未经允许透支、重复扣款和永久冻结。限制并发不能替代原子账务检查 |
| 客户断流/超时/后端退出 | 尽快取消；有可信 usage 按公布规则结算，无可信最终 usage 时首发免收不确定部分并释放相应预留，留下异常记录；不永久按 max_tokens 扣费 |
| 支付成功 | 服务端验签，核对订单、金额、币种、商户和状态；充值只入账一次，前端跳转不能作为入账依据 |
| 重复、乱序、伪造支付回调 | 不重复充值，不凭无效回调增加余额，订单状态正确 |
| 退款和撤销 Key | 退款关联原订单和未消费可退金额，赠送额度不错误退现；撤销 Key 后新请求被拒 |

完成注册→充值→余额到账→创建限额 Key→真实调用→查账→退款测试；订单、充值、消费、释放、退款可审计。每日生成支付/订单、余额/账单、请求/usage 三组对账报告，差异有原因和处置。

**通过：** 上表全部通过，无无法解释的余额差额；实际平台缺能力则补实现并回归。没有支付账号时可完成沙箱，但状态必须写“生产支付待接入”，不能标记可正式售卖。

## 6. P4：监控、压测、稳定性和恢复

### 6.1 监控先接好，再压测

参考平台页面提示尚未安装 kube-prometheus，不能假定已有采集与告警。先核对公司是否提供可复用监控；没有则首版自建项目范围的 Prometheus/Grafana/告警，不因无法安装集群级插件推迟监控。Prometheus 经内部 Service 抓 vLLM `/metrics`；本版采用项目自己的固定 Service 抓取目标，不依赖 ServiceMonitor、Operator 或授予 Prometheus 集群发现权限。网关无现成指标时补请求/账务统计；GPU 用可用的 NVML 或已验证 exporter，节点指标由运维提供或经批准采集，同时观测 Pod cgroup 内存、CPU throttling、重启、Pending/驱逐和卷余量。共享节点上不部署自己的全节点 DaemonSet、不读取 ServiceAccount token 来扩大查询。已有监控可由公司提供；否则为本项目创建 `qwen38-prometheus`、`qwen38-grafana` 和告警组件，用静态内部地址采集自己的服务。GPU 指标由运维已允许的 exporter 或自己推理容器内的 NVML 采集提供，只看获配四卡；不保证普通未分配 GPU 的 sidecar 自动可见设备。节点级故障由平台状态/运维补证，缺少字段要如实标明，不声称已具备未部署的集群监控。Grafana 至少显示：可用性、活动/排队请求、TTFT、TPOT/ITL、完成率、5xx/429、tokens、每卡显存/温度/功耗、RAM、重启、usage 缺失和结算异常。先核实 5090 支持哪些字段。

告警至少覆盖服务不可用、队列持续增长、OOM/重启、SLO 超标、磁盘不足、账务和备份失败；用可控测试实际触发和恢复。密钥、prompt、request_id 不作 Prometheus 标签；默认不记录真实客户正文。

### 6.2 压测方法和“满意”的标准

创建固定合成测试集，保存 tokenizer 计算后的真实输入/输出长度、thinking 策略、采样、缓存状态和工具版本。选固定版本 `vllm bench serve` 或其他支持 OpenAI API 的工具，按其实际 `--help` 生成 `tests/load.sh`，不能照抄跨版本 CLI。

| 负载 | 测法 | 首轮验收标准（项目起始目标，不是已达到的成绩） |
|---|---|---|
| 短对话 | 输入约 1K、输出约 256；并发 1/2/4/8 递增，每档至少 200 请求，明确输出长度分布 | 在声明的可售负载下，成功率≥99%，p95 TTFT≤2s，p95 请求平均 TPOT≤80ms；另报 ITL/最大停顿，不能用平均值掩盖卡顿 |
| 代码/工具 | 输入约 8K、输出上限 2K，含合成工具往返 | 功能用例通过；报告延迟和通过 SLO 的吞吐；性能报告不得混用不同实际输出长度 |
| 长输入 | 约 24K 输入＋1K 输出，确保模板和输出仍在 32K 内 | 请求完成、检索用例正确、无 OOM，分别报长请求延迟和对短请求的影响；不套用短对话 TTFT 门槛 |
| 排队/突发 | 在候选负载下至少 30 分钟固定到达率，再做限流与过载 | 队列无持续增长；过载明确 429/受控排队，余额无异常；记录 offered/accepted/completed/rejected，不隐藏拒绝请求 |

先直连后端，再走客户 HTTPS，区分开销。达到 SLO 的最高稳定完成负载作为测得上限，首发按其 70%–80% 设置总准入，再做一次客户入口验证。记录可售并发、RPM/TPM、输入/输出分布及测试环境；`max-num-seqs=16` 不等于能卖 16 并发。

若 eager 配置不达标，先完成所有可独立验证的商业功能，标记容量未通过；这时才允许提前进入 P6，解决阻塞上线的性能问题，改后回到 P4。不得降低门槛后偷偷宣称原目标达成；用户未确认的性能目标也不能当作对外 SLA。

### 6.3 稳定性和恢复

- 混合负载连续运行至少 24 小时，覆盖取消、工具、短长请求；按上述已选准入保持 SLO。无 OOM 循环、死锁、持续 RAM/显存泄漏、未解释账务差额。合法限流与实际错误分别统计。
- 通过网页仅对自己的测试 Deployment 做至少 3 次停启，覆盖容器重启、同节点 Pod 重建和缓存丢失后的等价冷启动；共享宿主不为本项目直接重启。每次确认模型文件/hash 保留、固定 imageID/版本、挂载、四卡分配及真实推理，记录就绪时间和 cgroup 峰值；临时缓存重建是预期行为，不判作模型数据丢失。停止自己的测试应用也要核对对象名称与归属，不编辑 Gemma。节点本地卷不宣称跨节点自动恢复；实际需要迁移时另验数据导入、目标节点四卡和调度。
- 在隔离测试环境验证后端退出、网关重启、数据库短暂不可用及恢复；不主动制造硬件错误，不在客户业务中随意 kill 进程。
- 将数据库备份恢复到独立实例，核对订单、余额、账单、价格和 Key；保存恢复时间。模型配置及镜像可重建，旧版本保留可回滚路径。

**通过：** 功能、账务、SLO、24h 稳定性、告警和恢复报告齐全。任何一项失败都不能标记“全链路验收通过”。

## 7. P5：受控售卖和交接

1. 落实经营主体、客户/服务器地区和适用上线要求。该 Qwen 许可证对 MaaS 经营者有单独许可条款，向第三方售卖 API 前取得覆盖本业务的书面授权；未完成时继续内部技术验收，暂不收费上线。核对所用 New API 版本许可与署名要求。许可原文按需查长稿第 1 节，不凭模型卡“可商用”一句判断。
2. 测墙上整机耗电，计入硬件/租金、带宽、运维、许可、支付手续费、退款及闲置成本。用实测负载和现实利用率定价，保留价格版本；不按社区 tok/s 承诺利润。
3. 交付客户文档：HTTPS Base URL、注册充值、Key 获取/撤销、SDK/curl、模型 alias、长度和限流、thinking/tools、usage/收费、断流/退款、数据留存和支持方式。四卡 TP4 是一个副本，按实测恢复能力约定维护，不承诺不存在的高可用。
4. 所有前提完成后，在总准入内开通少量受控客户，完成至少一笔真实小额支付和真实调用，核对账单、费率及退款流程；每日对账和观察实际质量，再逐步放量。

**最终满意：** 客户可独立完成充值→创建 Key→SDK 调用→查看正确账单；真实模型质量达标，声明负载满足 SLO，错误/断流不乱扣费，监控告警及恢复可用，商业许可和经营前提落实，交接人可以按保存配置重建和处理故障。任何缺项必须列入未完成清单。

最终交付一个 `reports/验收总表.md`：P0–P5 状态、集群/namespace/节点、最终四卡 UUID、实际 requests/limits/cgroup、上游及公司仓库镜像身份与 Pod imageID、模型 revision/hash、Deployment/Service/卷/入口及监控清单路径、测试入口和命令、各报告、实测容量与限流、价格口径、备份恢复、外部依赖及已知限制。凭据只交受保护的存储位置。

## 8. P6：全链路通过后，再优化效率

不改动正在收费的唯一实例做破坏性实验；使用维护窗口或隔离资源。若另有 4 张闲卡，先确认分配，再用于独立实验，不能自动占用。

依次比较：① eager→正常 CUDA graph；② MTP 关/1/3；③ 原生 local argmax（符合条件时）；④ 官方 FlashInfer PCIe IPC；⑤ 批 token/并发；⑥ 确有瓶颈再考虑 PEDIA、局部补丁或其他权重。通信项用 `VLLM_ALLREDUCE_USE_FLASHINFER_PCIE_IPC=1` 独立实验，确认实际采用和 workspace，而非只看环境变量。

每次保留原配置、只改主要变量；相同权重、任务、长度、采样、缓存和负载做至少 3 轮交错对比，检查质量、goodput、p95 延迟、内存/功耗。收益明确且质量/账务不退化再进入回归；采用前重跑相关 P1–P4。建议收益约 10% 或关键延迟明显改善才承担额外补丁维护成本；这是投入判断参考，不是上游保证。

**结束条件：** 可以选择继续使用已经验收的官方配置；不以装齐补丁或跑到社区峰值作为项目完成条件。


## 9. 当前待补信息、最小协助与交付

这些信息分阶段补齐；**不把 kubeconfig 或集群管理员权限列为缺项**。已有 `5090` GET、node01、参考 Service/卷及七条仓库记录不再重复当未知。

| 待落实 | 用于哪一步 | 能在现有边界怎样推进 |
|---|---|---|
| 用户实际停 Gemma、四卡独占交接和新资源额度 | P0/P1 | 用户操作网页停 Gemma；只读核对，Qwen 发布后记 UUID/cgroup；不代停其他应用 |
| 网页允许新建自己的 Deployment、Service、Secret 和挂载/探针字段 | P1/P2 | 先准备逐项字段或单对象 YAML；缺项交运维创建指定新对象，不以 Master 身份启用写 API |
| 公司镜像项目、推送/拉取权限、保留期限 | P1 | 从已知仓库记录中落实一个项目，新镜像新版本；节点验证固定 digest 可拉取 |
| node01 的专属 NVMe 模型目录、权限及持久挂载 | 模型导入/P1 | 运维只需提供一个隔离目录和对应挂载；或公司提供合格的独立 PVC，不动现有 NFS 资源 |
| 四类编译缓存是否持久化 | 冷启动/后续优化 | 模板先用临时缓存，可重建；用户未决定永久卷，不阻塞模型验证 |
| 独立数据库、网关 HTTPS、访问控制、项目监控及压测通道 | P2/P4 | 网页建自己组件或接公司指定服务；不修改共享设施、不把后端 NodePort 当最终产品入口 |
| 支付、经营许可、客户负载与预算 | P3/P5 | 继续沙箱/合成负载；真实条件具备后完成生产验收 |

如果网页不能自行落实，交给运维的最小任务是：**为 node01 提供项目专属模型目录和配额、一个可拉取的镜像项目/凭据，并代建本项目缺少页面权限的具体应用/Service/Secret，随后提供网关域名/TLS及持久数据库。** 不需要交出 kubeconfig；不要一并要求停止其他应用、改全局 NFS/驱动/设备插件或清理磁盘。

最终交付除 P0–P5 验收外，增加一份资源登记：cluster/namespace、类型/名称、归属与用途、网页操作位置（实测后填）、镜像源与 manifest digest、Pod imageID、模型宿主路径与 hash、卷保留/缓存重建策略、Service selector/port 与实际新 NodePort（若有）、旧版本恢复步骤。仅列自己资源，凭据只交存储位置。

本次仅修订文档，未请求/使用 kubeconfig、未执行任何平台写接口、未停止 Gemma、未部署应用或推送镜像。平台能力以环境记录和实际页面为准，不把 API 定义或 Kubernetes 通用机制当作漫道云账号写权限证明。

机制参考：[GPU 申请](https://kubernetes.io/docs/tasks/manage-gpus/scheduling-gpus/)、[卷与 emptyDir](https://kubernetes.io/docs/concepts/storage/volumes/)、[Service/NodePort](https://kubernetes.io/docs/concepts/services-networking/service/)、[关闭 Pod 凭据自动挂载](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)。
