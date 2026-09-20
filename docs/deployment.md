# 正式部署与维护

> 官网已在 <https://geekbird.org/> 正式上线。历史 VPS 访问地址和服务维护见 [VPS 部署记录](vps.md)。

> Cloudflare Pages 和浏览器管理后台请使用 [Cloudflare 部署说明](cloudflare.md)。下文保留原 Nginx 静态部署流程，该流程不提供管理后台。

## 当前约定

- 主机：`47.120.64.37`，SSH 用户 `root`，使用已配置的 SSH key。
- 对外端口：TCP `54321`。
- Nginx 网站目录：`/var/www/geekbird/public`，软链接指向某次发布的 `public/`。
- 站点配置：`/etc/nginx/sites-available/geekbird.conf`。
- 预约和反馈入口直达外部表单，地址统一由 `config.js` 管理，HTML 仅声明配置键。无 JavaScript 时显示启用提示。旧 `/booking/` 保留兼容，不自动跳转。

这些是当前环境的实际约定。更换服务器、域名或端口时同步修改 `deploy/nginx.conf`。该文件适用于 Nginx 的 `http` 上下文，主配置需加载标准 `mime.types`。

## 1. 检查并打包（本地）

在项目根目录运行：

```sh
python3 scripts/release.py
```

输出 `dist/geekbird-site.tar.gz`、`dist/manifest.json`、`dist/SHA256SUMS`。压缩包解开后是 `public/`，包含三个主页面、旧预约兼容页与静态资源。每次修改配置、页面或图片后重新打包。新增中文文案时，先运行 `python3 scripts/subset_fonts.py` 更新本地字体子集；字体许可文件随包分发。只有格式整理或文件相同的重复打包会得到相同的校验值。

上传到服务器的临时接收目录：

```sh
ssh root@47.120.64.37 'install -d -m 700 /tmp/geekbird-incoming'
scp dist/geekbird-site.tar.gz dist/manifest.json dist/SHA256SUMS root@47.120.64.37:/tmp/geekbird-incoming/
```

## 2. 备份与解压（服务器）

以下操作在同一个服务器 shell 中执行。发布目录使用新名字，避免覆盖仍在提供服务的文件。

```sh
set -eu
cd /tmp/geekbird-incoming
sha256sum -c SHA256SUMS

release_stamp=$(date -u +%Y%m%d-%H%M%S)
release_dir="/var/www/geekbird/releases/${release_stamp}"
previous_public=$(readlink -f /var/www/geekbird/public)
backup_file="/var/backups/geekbird-before-${release_stamp}.tar.gz"

test -d "$previous_public"
install -d -m 700 /var/backups
(umask 077; tar -czf "$backup_file" -C / var/www/geekbird etc/nginx/sites-available/geekbird.conf)
tar -tzf "$backup_file" >/dev/null

test ! -e "$release_dir"
install -d -m 755 "$release_dir"
tar -xzf geekbird-site.tar.gz -C "$release_dir"
find "$release_dir/public" -type d -exec chmod 755 {} +
find "$release_dir/public" -type f -exec chmod 644 {} +
printf '%s\n' "$previous_public" > "$release_dir/previous-public.txt"
```

`previous-public.txt` 位于 `public/` 外，不能通过网站访问。备份也在网站目录外。

如服务器有 Python 3，可核验解压后的每个文件：

```sh
python3 - "$release_dir" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
manifest = json.loads(pathlib.Path('/tmp/geekbird-incoming/manifest.json').read_text())
actual = {str(p.relative_to(root)) for p in (root / 'public').rglob('*') if p.is_file()}
assert actual == set(manifest), 'File list mismatch'
for name, expected in manifest.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
print('All release files verified')
PY
```

## 3. 切换发布

当前服务器已经监听 54321，更新静态文件不需要重载 Nginx。

```sh
nginx -t
test ! -e /var/www/geekbird/public.next
ln -s "$release_dir/public" /var/www/geekbird/public.next
mv -Tf /var/www/geekbird/public.next /var/www/geekbird/public
```

如需采用本项目整理后的 `deploy/nginx.conf`，先单独备份现有 Nginx 配置，再替换对应站点配置，执行 `nginx -t`，通过后执行 `systemctl reload nginx`。不要将项目的 server 块覆盖成完整的 `/etc/nginx/nginx.conf`。当前环境已启用站点，无需重复创建站点链接。

新服务器需安装并启用 Nginx、将站点文件纳入 `http` 配置，并在服务器防火墙及云安全组开放 TCP 54321。

## 4. 上线验收

```sh
curl -I http://47.120.64.37:54321/
curl -I http://47.120.64.37:54321/service/
curl -I http://47.120.64.37:54321/booking/
curl -I http://47.120.64.37:54321/config.js
curl -I http://47.120.64.37:54321/assets/images/architecture.webp
```

检查返回 200、HTML / JavaScript / WebP 的内容类型正确。未知路径和 `/README.md` 应返回 404。桌面与手机实际打开三页，确认：

- 图片完整显示，页面没有水平溢出。
- 首页和服务页的预约入口直接进入预约表单，服务反馈按钮直接进入反馈表单。
- 旧预约页停留时不跳转；预约和反馈按钮分别直达对应表单。
- 页面没有预约表单；QQ 联系显示正确。

配置与资源采用 `Cache-Control: no-cache`，每次访问重新验证，避免使用旧配置。确认通过后可以清理临时上传文件。旧发布目录和站外备份按自己的保留策略清理，切勿删除 `readlink -f /var/www/geekbird/public` 当前指向的目录。

## 5. 回滚

同一 shell 中若仍保留 `previous_public` 变量，可直接切回。否则从本次发布根目录的 `previous-public.txt` 读取：

```sh
previous_public=$(cat "$release_dir/previous-public.txt")
test -d "$previous_public"
test ! -e /var/www/geekbird/public.rollback
ln -s "$previous_public" /var/www/geekbird/public.rollback
mv -Tf /var/www/geekbird/public.rollback /var/www/geekbird/public
```

如果已删除旧目录，先从站外备份恢复到独立临时位置，确认旧发布文件完整后再恢复该目录并切换链接。不要直接在在线网站目录上覆盖解包。若同时改动过 Nginx，恢复对应备份后执行 `nginx -t` 和 `systemctl reload nginx`。

## 日常维护

根目录 `config.js` 是源项目唯一业务配置。线上对应 `/var/www/geekbird/public/config.js`。线上紧急修改后同步回源项目，避免下次部署覆盖。

图片原件在 `design/originals/`，导出的六张 WebP 在 `assets/images/`，来源映射见 [图片生成指南](image-prompts.md)。网页只使用 WebP，不直接加载 PNG。修改图片构图后复核桌面和手机端，再重新打包。

2026-09-19 已部署文字设计版本。当前发布目录为 `/var/www/geekbird/releases/20260919-075312-typography`，上一版本为 `/var/www/geekbird/releases/20260919-073516-production/public`，站外备份为 `/var/backups/geekbird-before-typography-20260919-075312.tar.gz`。沿用已经验证的 Nginx 配置。

本次部署包 SHA-256：`8b804d6218cecbb14a4397495b7ddf1156dd5e80072c4d9b3a5daf02e7cb2f6b`。
