# VPS 管理后台部署记录

> 2026-09-20 10:37（北京时间）已升级为完整的自建预约与反馈站点，见 [后端部署与验收记录](backend.md)。
>
> 网站：<https://47.120.64.37/>；预约：<https://47.120.64.37/booking/>；反馈：<https://47.120.64.37/feedback/>；业务工作台：<https://47.120.64.37/_gb-data/>。预约与反馈已开放，旧 54321 地址自动转向 HTTPS。下文为此前版本的历史记录。

2026-09-20 已在 VPS `47.120.64.37` 部署最新页面与管理后台，包含第三页免责声明。

## 访问

- 网站：<https://47.120.64.37/>。
- 免责声明：<https://47.120.64.37/disclaimer/>。
- 原地址继续可用：<http://47.120.64.37:54321/>。
- 管理后台：<https://47.120.64.37/_gb-settings/>。
- 用户名：`admin`；密码为部署时单独设置的管理密码，不记录在仓库中。

原 HTTP 地址上的管理路径会跳到 HTTPS，登录信息通过加密连接传输。IP 地址使用 Let's Encrypt 签发的受信任证书。官网现已在 <https://geekbird.org/> 正式上线；上面的 IP 地址为历史 VPS 部署地址。

## VPS 与 Cloudflare 的区别

VPS 后台无需 Cloudflare KV 或环境变量 `ADMIN_PASSWORD`，通过 Python 标准库服务保存配置。公开页面、管理界面及操作方式与 Cloudflare 版本一致，保存后刷新网页即可看到变化。配置在服务器磁盘持久保存，更新静态网页或重启服务不覆盖设置。

- 服务：`geekbird-admin.service`，以专用低权限用户 `geekbird` 运行，只监听 `127.0.0.1:8765`。
- Nginx 对外提供网页与 HTTPS，管理接口经过密码验证并限制请求频率。
- 配置文件：`/var/lib/geekbird/config.json`，采用临时文件加原子替换写入。
- 密码摘要：`/var/lib/geekbird/credential.sha256`，不保存明文密码。
- 后台配置：`/etc/geekbird/admin.env`，当前 `ADMIN_ORIGIN=https://47.120.64.37`。
- 网站链接：`/var/www/geekbird/public`。
- 服务代码链接：`/var/www/geekbird/current-server`。

以后切换管理域名时，需要同时配置该域名的 HTTPS 证书、Nginx 跳转地址和 `ADMIN_ORIGIN`，然后重启后台服务。

## 本次发布与回滚

2026-09-20 08:27（北京时间）已移除所有页面主导航中的“关于”入口，导航现在为首页、服务、免责声明。

- 当前网站：`/var/www/geekbird/releases/20260920-002710-navigation/public`。
- 当前后台：`/var/www/geekbird/releases/20260920-002320-disclaimer/server`。
- 上一版网站：`/var/www/geekbird/releases/20260920-002320-disclaimer/public`。
- 发布前备份：`/var/backups/geekbird-before-navigation-20260920-002710.tar.gz`。
- 静态发布包 SHA-256：`0421af69d4edd2b3c8083a4514056b51bbb6330f71014e78c156d65f808c11a3`。

本次只切换公开网站目录，后台服务、业务配置与密码保持原样。HTTPS 与原 HTTP 地址下的四个页面均已核对文件哈希及导航内容。回滚此次导航修改，只需将 `public` 链接切回上述上一版网站目录。

### 免责声明与后台升级记录

2026-09-20 08:23（北京时间）发布：

- 发布目录：`/var/www/geekbird/releases/20260920-002320-disclaimer`。
- 上一版网站：`/var/www/geekbird/releases/20260919-121854-admin/public`。
- 上一版后台：`/var/www/geekbird/releases/20260919-121854-admin/server`。
- 发布前备份：`/var/backups/geekbird-before-disclaimer-20260920-002320.tar.gz`，包含网站、后台状态、Nginx 与服务配置，仅 root 可读。
- 发布包 SHA-256：`a72d82b03750e8029afad1a66b9d104d7fc7bf4ddaf171786131bc798dffdd6c`。
- 发布目录保留 `previous-public.txt`、`previous-server.txt`、`previous-nginx.conf`、`manifest.json` 与 `deployment.json`，均位于公开目录之外。

本次同步升级了支持反馈链接的后台，将仍为旧默认公众号地址的预约配置迁移到问卷星预约表单，并为缺少反馈字段的旧配置补充反馈表单。QQ 与管理密码保持原样。

已验证 HTTPS 证书、18 个公开页面与资源的 SHA-256、两种访问地址下的页面和跳转、实时配置、后台认证保护及私有文件隔离；桌面与手机浏览器确认导航、免责声明、阅读锚点和外部表单链接正常。

回滚代码时，将 `public`、`current-server` 链接分别切回两个 `previous-*.txt` 记录的目录，恢复 `previous-nginx.conf`，执行 `nginx -t` 后重载 Nginx，并重启 `geekbird-admin`。页面回滚不会自动回滚业务配置；如需恢复本次迁移前的配置，可从上述备份取回 `/var/lib/geekbird/config.json`，恢复后保留 `geekbird` 用户所有权和原权限。管理密码文件无需变更。

## 证书自动续期

IP 证书为短期证书，不能关闭自动续期或公网 80 端口的验证路径。

- Certbot：`/opt/geekbird-certbot/bin/certbot`。
- 证书：`/etc/letsencrypt/live/geekbird-ip/`。
- 验证目录：`/var/www/geekbird-acme/.well-known/acme-challenge/`。
- 验证站点配置：`/etc/nginx/sites-available/geekbird-acme.conf`。
- 定时器：`geekbird-cert-renew.timer`，每 6 小时检查一次，成功续期后检查并重载 Nginx。

在服务器检查运行状态：

```sh
systemctl status geekbird-admin
systemctl list-timers geekbird-cert-renew.timer
journalctl -u geekbird-cert-renew.service
/opt/geekbird-certbot/bin/certbot renew --dry-run --cert-name geekbird-ip
```

## 后续打包

```sh
python3 -m unittest discover -s tests -p 'test_vps.py'
python3 scripts/vps.py
```

产物 `dist/geekbird-vps.tar.gz` 包含 `public/` 网站文件和私有 `server/` 服务文件。解压到新的发布目录，检查后切换 `public` 和 `current-server` 链接并重启 `geekbird-admin`。Nginx 根目录只指向 `public/`，不要公开 `server/`。后续发布前同时备份网站、Nginx 配置和 `/var/lib/geekbird`，不要重新初始化已有配置或密码。
