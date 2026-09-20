# Cloudflare Pages 部署与后台管理

此版本使用 Cloudflare Pages 的 Worker 和 KV，不需要自己的服务器、SSH 或数据库。官网主页面为首页、服务页与免责声明，旧预约地址保留兼容。

官网已正式上线：<https://geekbird.org/>。正式域名为 `geekbird.org`；新建或迁移 Pages 项目时，在 **Custom domains（自定义域）** 中配置此域名。

## 首次部署（Cloudflare 控制台）

1. 在 **Workers & Pages → KV** 创建一个 KV 命名空间，例如 `geekbird-settings`。
2. 在 **Workers & Pages** 创建 **Pages** 项目，连接 `galiandan/geekbird` 仓库，生产分支选 `main`。框架预设选 `None`，构建命令填 `python3 scripts/cloudflare.py`，构建输出目录填 `dist/cloudflare`，根目录留空（仓库根目录）。不要选择普通 Workers 的部署向导。
3. 在该 Pages 项目的 **Settings → Bindings** 添加 KV 绑定：变量名必须为 `SITE_CONFIG`，选择刚创建的命名空间。
4. 在 **Settings → Variables and Secrets** 添加 **Secret**：名称 `ADMIN_PASSWORD`，值为自己生成的至少 16 位长密码。推荐密码管理器生成 24 位以上随机密码。不要写入源码、`config.js` 或普通公开变量。
5. 保存设置后重新部署，使绑定和密码在新的部署中生效。生产环境与预览环境的设置分别配置；预览环境如需后台，应使用独立的 KV 与密码，避免修改正式配置。

使用 Git 集成构建即可，无需 SSH。若采用其他上传方式，必须支持 Pages advanced mode 的 `_worker.js`；只上传静态 HTML 无法提供管理功能。此构建产物针对 **Pages**，不是普通 Workers 的默认部署配置。

推荐 Git 集成，推送 `main` 后自动构建部署。若项目原先使用 `python3 scripts/release.py` 或将仓库根目录设为输出目录，必须改为上面的 Pages 设置。

## 发布包与文件范围

运行 `python3 scripts/cloudflare.py` 会生成：

- `dist/cloudflare/`：Pages 构建输出，包含三个主页面与旧预约地址兼容页。
- `dist/geekbird-cloudflare-pages.zip`：同一目录内容的压缩包，解压后 `_worker.js` 位于根层。
- `dist/cloudflare-manifest.json`：每个上线文件的 SHA-256。
- `dist/cloudflare-SHA256SUMS`：压缩包和文件清单的校验值。

压缩包供支持 `_worker.js` 的 Pages 上传流程使用；Git 集成只需填写输出目录，无需手动上传 ZIP。不要上传旧的 `geekbird-site.tar.gz` 或 `geekbird-vps.tar.gz`。新包不包含 Python 后台、systemd 配置、管理密码、文档或设计源稿。

`_routes.json` 让配置路径与 `/_*` 保留路径调用 Worker；管理路径要求密码，其他保留路径（含构建控制文件）统一返回 404，其余页面走静态托管。`_headers` 负责静态页面缓存和响应头，Worker 自己为动态响应设置 `no-store`。顶层 `404.html` 确保未知地址返回 404，而非 Pages 的单页应用首页回退。

## 打开后台

- 地址：<https://geekbird.org/_gb-settings/>；域名绑定完成前，可使用 Pages 分配的 `*.pages.dev` 域名访问同一路径。
- 浏览器会弹出身份验证窗口，用户名填 `admin`，密码填上面设置的 `ADMIN_PASSWORD`。
- 页面与读写接口都在服务端校验密码，公开导航没有后台链接；后台响应禁止缓存和搜索收录。
- 只能通过 HTTPS 在线管理。建议在个人浏览器或独立隐私窗口操作；Basic 身份验证由浏览器暂存，使用完关闭整个隐私窗口。更换密码需在 Cloudflare 更新 Secret 并重新部署。

输入 QQ 号与完整的 HTTP(S) 预约、反馈链接，点击“保存设置”。允许留空：QQ 留空时显示“QQ 号暂未公布”，预约或反馈链接留空时暂停对应入口。保存失败会明确提示，不会显示保存成功。

KV 在全球各地区最终一致，通常约 60 秒、部分地区可能更久；保存后稍后刷新公开网站验证。不要多人同时修改：最后一次成功写入覆盖之前的配置。

## 配置与更新

- 第一次保存前沿用根目录 `config.js` 的默认值。
- 第一次保存后，KV 中的配置优先；重新发布页面不会覆盖后台设置。
- `/config.js` 动态输出 QQ、预约和反馈链接供公开页面使用，管理密码不会输出到页面中。
- 未绑定 KV 时公开网站仍使用原始静态配置，后台提示尚未配置。KV 读取故障时返回错误，不悄悄恢复可能已停用的旧预约链接。
- 不要为 `/config.js` 或 `/_gb-settings*` 设置“缓存所有内容”等强制缓存规则。
- 如果要重置为源码默认值，在 Cloudflare 的 KV 控制台删除 `site-config` 键即可。

## 常见问题

| 现象 | 处理方式 |
| --- | --- |
| 提示设置 `ADMIN_PASSWORD` | 在当前部署环境新增同名 **Secret**，至少 16 位，然后重新部署。 |
| 浏览器一直要求登录 | 用户名为 `admin`；检查密码是否为当前环境的值。修改 Secret 后重新部署，用新的隐私窗口重试。 |
| 提示绑定 `SITE_CONFIG` | 创建 KV 后还要绑定到 Pages；变量名必须为 `SITE_CONFIG`，保存后重新部署。 |
| 后台 404 或显示首页 | 检查输出目录是否为 `dist/cloudflare`，且产物包含 `_worker.js` 和 `_routes.json`。 |
| 预览正常、正式地址报错（或相反） | 生产与预览的 Secret 和 KV 绑定分别配置；两者使用独立 KV。 |
| 保存后部分地区仍显示旧值 | 等待 KV 同步，并检查是否设置了强制缓存规则。不要连续快速重复保存。 |

## 从 VPS 切换与上线验收

1. 在 `*.pages.dev` 地址确认首页、服务页、免责声明、旧预约地址和图片正常；预约和服务反馈按钮直接进入对应外部表单。
2. 核对原 VPS 的 QQ 和预约链接。在 Pages 后台填写并保存，稍后刷新公开页面验证。VPS 的磁盘配置、密码不会自动导入 Cloudflare；源码默认值仅在 KV 尚未保存时使用。
3. 用未登录的隐私窗口检查 `/_gb-settings/` 和 `/_gb-settings/api` 均要求身份验证。`/README.md`、`/server/admin.py` 和随机未知路径应返回 404。
4. 在 Pages **Custom domains** 添加 `geekbird.org`。若域名原有指向 VPS 的记录，按 Pages 提示替换对应记录；等待域名验证及 HTTPS 完成。
5. 在 `https://geekbird.org` 再次检查页面、后台登录与保存。初次切换可能需要在新域名重新登录。
6. 验收完成前保留原 VPS。回滚 Pages 部署只回滚代码，不回滚 KV；如需恢复旧配置，在后台重新填写。

源码 canonical 和站点地图使用 `https://geekbird.org`。后台地址不出现在公开导航、`robots.txt` 或站点地图中，通过密码验证和 `noindex` 响应保护。

## 本地检查

```sh
python3 scripts/cloudflare.py
node --test tests/*.test.mjs
```

构建仅依赖 Python 3；接口测试需要 Node.js 22 或以上。测试覆盖预约和反馈链接、构建文件保护、密码保护、配置保存与读取、非法输入、跨站写入拦截、KV 故障和损坏配置。后台 HTML 内嵌于 Worker，不单独公开。

可使用 Wrangler 在本地 Cloudflare 运行环境启动，下面的密码仅用于本地测试：

```sh
npx wrangler@4.135.0 pages dev dist/cloudflare --ip 127.0.0.1 --port 8788 --compatibility-date 2026-09-01 --kv SITE_CONFIG --binding ADMIN_PASSWORD=local-test-password-only
```

访问 `http://127.0.0.1:8788`，后台路径与正式版本一致。另开终端运行 `node tests/cloudflare-smoke.mjs`，可检查真实 Pages 路由、静态文件、404、密码保护和 KV 保存。该脚本只访问上述本地端口，写入后恢复测试配置。

这里的 KV 是本地模拟存储，不连接生产 KV。不要把真实密码写入命令或提交到仓库；本地 `.dev.vars` 与 `.wrangler/` 已被 Git 忽略。真实 Cloudflare 绑定、域名和全球同步仍需首次部署后验收。
