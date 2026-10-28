# Recovery candidate reviewed 2026-10-26; not built or GPU-tested in this workspace.
# Use QWEN-PEDIA/recipes/qwen3.8-flash-next at commit
# ed7901322730a79473a1022de3d7a2496b70c63e as the Docker build context.
# The base digest resolves to the original eed1f3d0 CUDA 13 image;
# runtime instructions are otherwise the same as the inspected r10 Dockerfile.
FROM vllm/vllm-openai@sha256:d0742e7e31b16c85c9e215960604452f5f172a522d35c94ca42b7030cb0afa36
COPY image/vllm/ /usr/local/lib/python3.12/dist-packages/vllm/
