import getpass
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

base = input('API 地址 [http://10.254.175.93]: ').strip() or 'http://10.254.175.93'
token = getpass.getpass('accessToken（输入不显示）: ').strip()
user_id = input('userId: ').strip()

if not token or not user_id:
    raise SystemExit('accessToken 和 userId 不能为空')

# 输出可能含应用配置或敏感字段，仅保存到当前用户可读的本地目录。
out = Path.cwd() / (
    'mandao-inspect-' + datetime.now().strftime('%Y%m%d-%H%M%S')
)
out.mkdir(mode=0o700)

def query(label, endpoint, fields):
    payload = {
        'accessToken': token,
        'userId': user_id,
        **{k: v for k, v in fields.items() if v},
    }
    request = urllib.request.Request(
        base.rstrip('/') + endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    print(f'\n===== {label} =====')
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode('utf-8', errors='replace')
        try:
            text = json.dumps(
                json.loads(raw), ensure_ascii=False, indent=2
            )
        except json.JSONDecodeError:
            text = raw

        # 防止响应回显本次提交的访问令牌。
        text = text.replace(token, '<ACCESS_TOKEN 已隐藏>')
        path = out / f'{label}.json'
        with path.open('x', encoding='utf-8') as f:
            path.chmod(0o600)
            f.write(text)

        print(text)
        print(f'\n已保存: {path}')
    except urllib.error.HTTPError as exc:
        print(f'HTTP 错误: {exc.code}')
    except Exception as exc:
        print(f'查询失败: {type(exc).__name__}: {exc}')

cluster = input('集群名称（不知道可先留空）: ').strip()
namespace = input('命名空间 [my-space]: ').strip() or 'my-space'

query('deployments', '/api/v3/deployment/query', {
    'cluster': cluster,
    'namespace': namespace,
})

print('\n请根据以上返回确认集群和 Deployment 名称。')
cluster = input('集群名称（后续查询必填）: ').strip() or cluster
deployment = input('Deployment 名称（按返回填写）: ').strip()

if not cluster:
    raise SystemExit(
        '尚未确认集群名称；请从控制台确认后重新运行。'
    )

if deployment:
    query('deployment-detail', '/api/v3/deployment/query', {
        'cluster': cluster,
        'namespace': namespace,
        'deployment': deployment,
    })

pod = input(
    'Pod 名称 [gemma4-5484c98d45-bp6sh，按当前页面核实]: '
).strip() or 'gemma4-5484c98d45-bp6sh'

query('pods', '/api/v3/pod/query', {
    'cluster': cluster,
    'namespace': namespace,
    'pod': pod,
})

node = input(
    '节点名称（从 Pod 的 spec.nodeName 获取；留空跳过节点查询）: '
).strip()

if node:
    query('node', '/api/v3/node/query', {
        'cluster': cluster,
        'name': node,
    })

query('quota', '/api/v3/resourcequota/query', {
    'cluster': cluster,
    'namespace': namespace,
})

query('services', '/api/v3/service/query', {
    'cluster': cluster,
    'namespace': namespace,
})

print(f'\n查询结束。结果目录: {out}')
print('响应中可能包含应用敏感配置，分享前请脱敏。')
