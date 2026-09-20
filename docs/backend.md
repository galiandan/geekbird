# 自建后端：运行、验收与切换

本分支已实现 FastAPI + SQLite 业务服务、站内表单、管理工作台、隔离预览环境及部署工具。设计和字段依据见 [方案文档](backend-plan.md)。下文记录实际运行约定，不包含密码。

## 当前部署状态

2026-09-20，VPS 已部署完整站点、配置后台与业务 API。访问 <https://47.120.64.37/> 即可使用站内预约和反馈，数据写入正式 SQLite。Cloudflare 的 `geekbird.org` 仍以原生产部署为准，后续再切换。

本次发布目录为 `/opt/geekbird-api/releases/20260920T010801Z`，上一版为 `20260920T010613Z`。29 项业务 API 测试、25 项前端/Worker 测试、5 项 VPS 配置测试通过；本地和真实远端 HTTPS 的桌面/手机浏览器流程均已验收。IP 证书的 `certbot renew --dry-run` 成功，实际每日备份与完整性检查已执行。

| 项目 | 正式业务 | 隔离预览 |
| --- | --- | --- |
| API | `https://47.120.64.37/api/v1` | `https://47.120.64.37/_gb-preview/api/v1` |
| 工作台 | `https://47.120.64.37/_gb-data/` | `https://47.120.64.37/_gb-preview/_gb-data/` |
| systemd 服务 | `geekbird-api` | `geekbird-api-preview` |
| 回环端口 | 8766 | 8767 |
| 系统用户 | `geekbird-api` | `geekbird-preview` |
| 数据目录 | `/var/lib/geekbird-api` | `/var/lib/geekbird-preview` |
| 配置目录 | `/etc/geekbird-api` | `/etc/geekbird-preview` |
| 接收状态 | 已开放预约和反馈，支持 VPS HTTPS 站点 | 已开放，限虚构测试资料 |

VPS 网站发布目录为 `/var/www/geekbird/releases/20260920T023735Z-self-hosted`，`public` 与 `current-server` 链接已同步切换。`geekbird-admin` 仍使用 8765，已升级为新版 QQ 设置和业务工作台入口。旧 `http://47.120.64.37:54321/` 地址对 GET/HEAD 转向 HTTPS，拒绝明文写入。

数据库文件名均为 `geekbird.sqlite3`，父目录权限 0700。初次部署生成独立的 `admin` 账号密码，保存在各配置目录下的 `credential.password`，仅 root 可读。应用只读取 `credential.json` 中的带盐 scrypt 摘要。密码文件不进 Git，也不在管理页面显示。

登录工作台前，可在自己的终端通过 SSH 读取对应密码文件。妥善保存到密码管理器后，可移除明文文件；应用运行只需要摘要文件。部署脚本不会重新生成已存在的账号摘要。

## 代码与配置

- `server/api/models.py`：公开表单与管理更新的字段约束。
- `server/api/db.py`、`migrations/001_initial.sql`：明确字段、事务、重复提交、版本冲突和操作记录。
- `server/api/app.py`：JSON API、跨域、身份验证、错误处理和 CSV 导出。
- `server/api/admin.html`、`admin.js`：受保护的工作台。
- `server/api/manage.py`：迁移、密码、在线备份与到期清理。
- `scripts/api.py`：只打包私有 API 与部署配置。
- `scripts/deploy_api.py`：校验包、准备虚拟环境、备份、迁移、切换、健康检查；失败时恢复原 Nginx 配置和可用的旧应用版本。

应用从配置目录的 `api.env` 读取：

```text
GB_DATABASE=/var/lib/geekbird-api/geekbird.sqlite3
GB_CREDENTIAL=/etc/geekbird-api/credential.json
GB_ADMIN_ORIGIN=https://47.120.64.37
GB_ALLOWED_ORIGINS=https://geekbird.org,https://47.120.64.37
```

预览环境使用自己的路径和明确的 Pages 分支 origin，正式环境不允许 Pages 预览或本地来源。配置修改后重启相应服务。CORS 的 Nginx map 也需同步更改；不要加入通配域。

API 接收开关保存在数据库，由工作台控制，不从 Cloudflare KV 读取。管理写入需 Basic 身份验证、正确的 `Origin`、`X-GB-Request: records` 和 JSON 正文；管理接口不开放 CORS。API 文档与公开记录查询均关闭。

公开 POST 要求随机 UUID v4 `Idempotency-Key`。同键同内容返回原编号，不重复写入；同键不同内容返回 409。状态/时长更新需要记录版本，旧版本不会覆盖新修改。请求正文最多 32 KiB；Nginx 每 IP 每分钟允许 6 次公开 POST，短时允许 3 次突发，GET 和预检不占此配额。

## 本地验证

```sh
python3 -m venv .venv
.venv/bin/pip install -r server/api/requirements-dev.txt
npm ci
python3 scripts/cloudflare.py
.venv/bin/python -m pytest tests/test_api.py -q
python3 -m unittest discover -s tests -p test_vps.py
npm test
npx playwright install chromium
.venv/bin/python tests/run_browser.py
```

`tests/run_browser.py` 使用临时数据库与测试密码，在 `127.0.0.1:8790`、`127.0.0.1:8800` 启动接口和静态站；结束后停止服务并清理数据。测试前确保两个端口空闲。截图默认保存到 `/tmp/geekbird-browser-results/`。

如果 Node 或 Playwright 使用其他安装路径，可以设置 `GEEKBIRD_NODE`、`GEEKBIRD_PLAYWRIGHT_MODULE`，必要时用 `GB_BROWSER_EXECUTABLE` 指向现有 Chromium。这些是本地工具选项，不进入构建配置。

已覆盖的关键行为包括：

- 预约和反馈字段校验，旧说明版本、未来日期、非整数评分、异常时长与额外管理字段的拒绝。
- 8 个并发相同请求只产生一条记录；丢失回执后的浏览器重试返回同一编号。
- 暂停接收、重新开放、接口故障与超时保留输入；已经成功入库的请求仍能取得原回执。
- 管理员鉴权、跨站写入拦截、状态流转、并发修改冲突和操作日志。
- 原始填报时长与确认时长分开保存；CSV 导出处理公式注入。
- 备份完整性、恢复后能读取记录、到期清理及个人字段移除。
- 桌面和手机表单、后台处理、时长核实、下载和暂停提示。

`tests/browser-smoke.mjs` 也支持连接隔离的远端预览 API。设置 `GB_BROWSER_ASSETS` 时，它在浏览器内提供本地构建资源，以验证真实 HTTPS 和跨域提交；这种验收不是 Cloudflare 发布，不能把该测试 origin 宣称为已上线预览地址。

## VPS 完整站点部署

已有 API 时，在本地执行：

```sh
python3 scripts/deploy_vps.py
```

脚本校验发布包和所有上线静态文件的哈希，备份旧网站、配置服务、Nginx 与业务数据库，同步切换网站和配置服务；失败时恢复原链接、配置与接收开关。首次迁移根据旧外部入口是否开放来初始化业务开关，保存 v2 站点配置；后续发布保留管理员设置，不重新开放已暂停的入口。

本次站点备份：`/var/backups/geekbird-before-vps-20260920T023735Z.tar.gz`。数据库迁移前快照：`/var/backups/geekbird-api/before-deploy/geekbird-20260920T023735636180Z.sqlite3`。原公开目录与配置服务目录分别为 `20260920-002710-navigation/public`、`20260920-002320-disclaimer/server`，均位于 `/var/www/geekbird/releases/` 下。

已在真实 VPS 页面完成桌面预约、手机反馈、丢失回执重试、工作台状态更新、确认时长和 CSV 下载验收。五个页面与发布清单哈希一致，私有文件返回 404，两个后台均要求登录；原 QQ 与配置后台密码保留。本次创建的两条明确标记的验收记录已按编号清理。

完整站点验收显式设置 `GB_BROWSER_LIVE_VPS=1`，直接访问真实 VPS 页面。它只新增带“验收测试”标记的记录，不暂停正式接收；验收后按返回编号清理这些测试记录。默认浏览器测试仍只允许本地或隔离预览。

## 后端部署

本地执行：

```sh
python3 scripts/deploy_api.py
```

默认目标为 `root@47.120.64.37`。部署使用新目录 `/opt/geekbird-api/releases/<UTC 时间>/`，每个目录包含自己的虚拟环境与依赖；`/opt/geekbird-api/current` 指向当前版本。`previous-release.txt`、`previous-nginx.conf` 位于私有发布目录，可用于核对回滚。

Nginx 新配置位于 `/etc/nginx/conf.d/geekbird-api.conf` 与 `/etc/nginx/snippets/geekbird-api-*.conf`，只在现有 HTTPS server 中新增代理路由，保留原 ACME 验证与网站路由。公开 API 的 413、429、502/504 错误会返回 JSON，并保留匹配来源的跨域响应头。

已有数据库在迁移前备份到 `/var/backups/<环境目录>/before-deploy/`。初次建库两个接收开关都为关闭；重复部署不会覆盖原数据、接收开关或密码。当前只有初始 schema 迁移，后续破坏性结构变更必须单独设计兼容与停写步骤。

部署后在服务器检查：

```sh
systemctl status geekbird-api geekbird-api-preview
systemctl list-timers geekbird-api-backup.timer geekbird-cert-renew.timer
nginx -t
curl -fsS https://47.120.64.37/api/v1/health
curl -fsS https://47.120.64.37/api/v1/meta
```

修改密码在服务器交互式执行，不把密码放进命令参数：

```sh
cd /opt/geekbird-api/current
venv/bin/python -m api.manage set-password --output /etc/geekbird-api/credential.json
chown root:geekbird-api /etc/geekbird-api/credential.json
chmod 640 /etc/geekbird-api/credential.json
systemctl restart geekbird-api
```

轮换后删除或替换旧的 `credential.password`，避免将初始密码误当成新密码。预览密码使用其独立目录和服务。

## 每日备份与到期清理

`geekbird-api-backup.timer` 每天北京时间 03:00 左右运行。先使用 SQLite backup API 生成完整副本，执行 `integrity_check`，保留 14 份日常备份，并清理 `daily`、`manual`、`before-deploy` 中超过 14 天的副本；成功后清理完成/取消或核实/无效超过 180 天的个人信息。清理记录保留已使用幂等键标记，旧请求不会被当作新申请。

备份目录为 `/var/backups/geekbird-api/daily/`，不属于网站目录。预览库只用于测试，不启用正式每日备份任务；部署前仍保留独立快照。日志保留 14 天，访问日志不包含请求正文和查询字符串，应用不记录密码或提交内容。

手动备份与查看清理数量：

```sh
cd /opt/geekbird-api/current
venv/bin/python -m api.manage backup --directory /var/backups/geekbird-api/manual
venv/bin/python -m api.manage purge
```

`purge` 默认只统计，传入 `--apply` 才执行。日常备份任务执行失败时不会继续清理，需从 `journalctl -u geekbird-api-backup` 查看并处理。IP 短期证书仍由原 `geekbird-cert-renew.timer` 自动续期，不能关闭 ACME 验证路径。

这些备份在同一台服务器，尚无异机容灾或自动通知渠道。整机丢失不在本机备份保护范围内；离机备份目的地需要另行配置。

## 恢复与回滚

恢复数据库前先关闭接收并停止业务服务，在私有目录保留当前数据库及同名 WAL/SHM 文件。把选定备份复制到新的临时文件，执行 SQLite `integrity_check`，确认迁移版本，再恢复为状态目录中的 `geekbird.sqlite3`；所有者为对应服务用户，权限 0600，父目录 0700。不要让旧 WAL 文件与恢复文件混用。

启动服务后先检查记录数、关联和到期信息清理，再开放接收。旧备份可能包含已经到期的资料，恢复后应重新执行相应清理。恢复数据库可能回退最近的业务数据，应保留故障现场以便补回。

程序回滚可把 `current` 切回 `previous-release.txt` 所指版本，然后重启 API；必须确认该代码兼容当前 schema。不要为回滚代码直接覆盖数据库。涉及 Nginx 变更时恢复对应备份并 `nginx -t` 后重载。

前端与数据库独立部署。Pages 回滚不会回滚 KV；旧页面依赖旧配置结构，需要同时恢复对应 `site-config` 备份。具体生产切换步骤见 [Cloudflare 迁移说明](cloudflare.md)。

## 生产前端切换条件

1. 在 Pages 中核实 `geekbird` 项目的 Git 连接、生产分支和构建输出。仓库另有 `geektest` Workers Builds 检查，不能据此判断 Pages 已自动部署。
2. 核对旧 KV 中原本关闭的入口，在正式业务工作台保持相应关闭；其余按实际接收安排开放。
3. 用独立预览验收后发布本分支前端，确认其 `apiBaseUrl` 指向正式 API，页面没有测试提示。
4. 在官网提交明确标记的测试记录并核对后台，检查所有旧外链入口、页面说明与失败提示。历史问卷答卷单独保留或另行导入。

VPS 完整站点已正常接收预约和反馈；Cloudflare 正式页面仍需按上述步骤单独切换。Git 分支 push 与 Pages 正式发布是两个独立结果。

## 后台界面更新（2026-09-20）

服务工作台与站点设置统一使用浅色、绿色强调的管理界面。工作台提供预约/反馈侧边导航、当前筛选结果数量、实时接收状态卡片、状态标签、空列表提示、筛选与导出工具栏，以及独立的详情和处理表单。手机端导航移到顶部，记录表格在容器内横向滚动，详情改为单列。

顶部数量为当前筛选结果总数，不是全站累计或待办数；接收状态来自业务接口，保存开关后同步更新。站点设置继续负责公开 QQ，业务工作台负责接收开关和服务记录。

密码设置工具最低接受 6 个字符，自动生成密码仍采用原有随机方式。按站点所有者要求，VPS 上两个正式后台统一使用 `admin` 用户及同一密码；密码不写入仓库。业务端保留 scrypt 摘要，站点设置保留原有摘要认证，预览环境凭据保持独立。正式业务端的 root 专用密码文件已同步更新；后续若要继续保持两个后台密码一致，需要同时轮换两个摘要，并重启 `geekbird-api`、`geekbird-admin`。浏览器缓存旧 Basic 凭据时，用新隐私窗口重新登录。

部署记录：API `/opt/geekbird-api/releases/20260920T070338Z`，站点 `/var/www/geekbird/releases/20260920T070417Z-self-hosted`。部署前已备份数据库与站点，保留原接收状态和业务记录。验证包括 30 项 API 测试、25 项前端/Worker 测试、5 项设置服务测试、本地浏览器业务流程，以及真实 VPS 两个后台登录、导航、接收状态读取和桌面/手机布局检查。Cloudflare 正式站点尚未切换。
