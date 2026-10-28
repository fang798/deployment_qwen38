#!/usr/bin/env python3
"""漫道云当前 OpenAPI 查询工具（本机终端运行）。

全部默认查询：
    python3 /home/user/xu_fang/work/deployment/query_mandao.py
仅查询集群，确认认证：
    python3 /home/user/xu_fang/work/deployment/query_mandao.py --clusters-only
已知真实配额对象名时（将 实际配额对象名 替换为查询到的名称）：
    python3 /home/user/xu_fang/work/deployment/query_mandao.py --resourcequota-name 实际配额对象名
查看命令参数：
    python3 /home/user/xu_fang/work/deployment/query_mandao.py --help

交互提示默认值：API=http://10.254.127.231，cluster=5090，namespace=my-space，
Deployment=gemma4。使用当前门户返回的配对 token/userId，不把令牌写在命令中。
默认14项仅GET，认证失败停止；不会重启/创建/修改/删除资源，不查询Secret内容。
结果默认存入当前脚本旁的 mandao-query-current-时间/；这些是实际查询结果。
完整接口定义及容器、kubectl补查命令统一见同目录：
    漫道云部署环境核实记录与后续部署参考.md
"""
import getpass
import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode


def resource_summary(label, value):
    """Describe actual resource data, keeping Kubernetes status separate from errors."""
    if isinstance(value, dict) and value.get('kind') in ('Deployment', 'Namespace'):
        meta = value.get('metadata', {})
        status = value.get('status', {})
        if label == 'deployment':
            return f'Deployment {meta.get("name")}，ready={status.get("readyReplicas", 0)}，replicas={status.get("replicas", 0)}'
        return f'Namespace {meta.get("name")}，phase={status.get("phase")}'
    if isinstance(value, list):
        return f'返回 {len(value)} 条' if value else '返回空列表 []（当前查询范围没有返回条目，不是接口报错）'
    if isinstance(value, dict) and isinstance(value.get('items'), list):
        return f'本页 {len(value["items"])} 条，总数 {value.get("total", "未提供")}'
    return '响应结构未识别，请检查保存的 JSON；不自动判定为查询成功'


def curl_get(base, path, headers):
    # Keep authentication headers off the process command line and out of files.
    for value in headers.values():
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('请求头含控制字符，拒绝发送')
    config = '\n'.join('header = ' + json.dumps(k + ': ' + v, ensure_ascii=False)
                       for k, v in headers.items()) + '\n'
    result = subprocess.run([
        'curl', '--noproxy', '*', '--silent', '--show-error',
        '--connect-timeout', '5', '--max-time', '30', '--request', 'GET',
        '--config', '-', '--write-out', '\n%{http_code}', base + path,
    ], input=config, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'curl 退出码 {result.returncode}')
    body, _, status = result.stdout.rpartition('\n')
    return status, body


def main():
    parser = argparse.ArgumentParser(description='新版漫道云 GET 查询；遇 LOGIN_TIMEOUT 停止')
    parser.add_argument('--resourcequota-name', help='已知配额对象名称时使用专用配额详情接口')
    parser.add_argument('--clusters-only', action='store_true', help='仅查询集群列表，核对认证')
    options = parser.parse_args()
    if not shutil.which('curl'):
        raise SystemExit('需要本机 curl')
    base = (input('新版 API 地址 [http://10.254.127.231]: ').strip()
            or 'http://10.254.127.231').rstrip('/')
    # Gateway route identifiers are public routing metadata, not login tokens.
    status, body = curl_get(base, '/swagger-resources', {})
    if status != '200':
        raise SystemExit(f'读取网关分组失败 HTTP {status}')
    groups = {g['name']: g['header'] for g in json.loads(body)}
    if not {'容器管理', '镜像管理'} <= groups.keys():
        raise SystemExit('未找到当前网关的容器管理/镜像管理分组，未发送凭据。')
    cluster = input('集群名称 [5090]: ').strip() or '5090'
    namespace = input('namespace [my-space]: ').strip() or 'my-space'
    deployment = input('Deployment [gemma4]: ').strip() or 'gemma4'
    token = getpass.getpass('新 OpenAPI 门户登录返回的 token（隐藏输入）: ').strip()
    user_id = input('userId: ').strip()
    if not token or not user_id:
        raise SystemExit('凭据不能为空')
    folder = Path(__file__).resolve().parent / ('mandao-query-current-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir(mode=0o700)
    c, n, d = (quote(x, safe='') for x in (cluster, namespace, deployment))
    root = f'/apis/k8s/v1/clusters/{c}'
    nsroot = root + f'/namespaces/{n}'
    generic = f'/apis/k8s/v2/clusters/{c}/namespaces/{n}'
    queries = [
        ('clusters', '容器管理', '/apis/k8s/v1/clusters'),
        ('deployment', '容器管理', nsroot + '/deployments/' + d),
        ('pods', '容器管理', nsroot + '/pods?' + urlencode({'labels': 'app:' + deployment})),
        ('namespace', '容器管理', nsroot),
        ('services', '容器管理', nsroot + '/services'),
    ]
    # The gateway explicitly rejected these plural names on 2026-10-28:
    # resourcequotas, limitranges, endpointslices. Do not repeat them.
    if options.resourcequota_name:
        queries.append(('quota', '容器管理', nsroot + '/resourcequota/' + quote(options.resourcequota_name, safe='')))
    for label, resource in [('pvc', 'persistentvolumeclaims'), ('networkpolicies', 'networkpolicies'),
                            ('ingresses', 'ingresses')]:
        queries.append((label, '容器管理', generic + '/' + resource))
    for label, resource in [('nodes', 'nodes'), ('pv', 'persistentvolumes'), ('storageclasses', 'storageclasses')]:
        queries.append((label, '容器管理', root + '/' + resource))
    queries += [('repositories', '镜像管理', '/apis/repository/v1/repositories?page=1&pageSize=20'),
                ('images', '镜像管理', '/apis/image/v1/images'),
                ('groups', '镜像管理', '/apis/group/v1/groups')]
    if options.clusters_only:
        queries = queries[:1]
    print(f'仅 GET 查询 cluster={cluster}, namespace={namespace}；通用资源可能受服务支持范围和权限限制。')
    for label, group, path in queries:
        headers = {'token': token, 'userId': user_id,
                   'knife4j-Gateway-Request': groups[group], 'knife4j-gateway-code': 'ROOT'}
        try:
            status, body = curl_get(base, path, headers)
            try:
                parsed = json.loads(body)
                body = json.dumps(parsed, ensure_ascii=False, indent=2)
            except ValueError:
                parsed = None
            fd = os.open(folder / (label + '.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as out:
                out.write(body.replace(token, '<TOKEN_REDACTED>'))
            print(f'{label}: GET {path} → HTTP {status}，保存 {folder / (label + ".json")}')
            if isinstance(parsed, dict):
                summary = {k: parsed[k] for k in ('success', 'code', 'message', 'msg', 'error') if k in parsed}
                if isinstance(parsed.get('status'), (str, int)):
                    summary['status'] = parsed['status']
                if summary:
                    print('  摘要: ' + json.dumps(summary, ensure_ascii=False).replace(token, '<TOKEN_REDACTED>'))
            error = parsed.get('error') if isinstance(parsed, dict) else None
            code = error.get('code') if isinstance(error, dict) else (parsed.get('code') if isinstance(parsed, dict) else None)
            if code == 'LOGIN_TIMEOUT' or status == '401':
                print('  认证失败：请登录当前新 OpenAPI 门户，使用该门户返回的 token/userId；未查询到资源。')
                print('  已停止后续请求。结果目录：' + str(folder))
                return
            failed = not status.startswith('2') or bool(error) or parsed is None or (isinstance(parsed, dict) and parsed.get('success') is False)
            if failed:
                print('  查询失败：保存的是错误响应，不能作为资源配置证据。')
            else:
                print('  ' + resource_summary(label, parsed))
                if label == 'clusters':
                    if isinstance(parsed, list):
                        rows = parsed
                    elif isinstance(parsed, dict):
                        rows = parsed.get('data', parsed.get('items', []))
                    else:
                        rows = []
                    if isinstance(rows, list):
                        for row in rows:
                            if isinstance(row, dict):
                                print('  集群: ' + json.dumps({k: row.get(k) for k in ('cluster','role','enable','status')}, ensure_ascii=False))
        except (RuntimeError, ValueError, OSError) as exc:
            print(label + ': ' + str(exc).replace(token, '<TOKEN_REDACTED>'))
    print('结束：未执行写操作，未查询 Secret/ConfigMap 内容。仓库仅第 1 页。')
    print('通用接口查 PVC/PV 等为按 resourcePlural 的尝试；错误/空结果不证明资源不存在。')
    print('响应中其他敏感配置未自动脱敏，分享前检查。使用当前门户登录返回的配对 token/userId。')


if __name__ == '__main__':
    main()
