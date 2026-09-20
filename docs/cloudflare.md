# Cloudflare Pages 构建与迁移

本分支静态页面仍在 Cloudflare Pages，预约和反馈通过 HTTPS 直接提交到自建 API。现有 Pages Worker / KV 只维护联系 QQ 等公开配置。业务记录、接收开关与密码位于 VPS，详见 [后端部署说明](backend.md)。

## Pages 设置

| 项目 | 值 |
| --- | --- |
| 框架 | `None` |
| 构建命令 | `python3 scripts/cloudflare.py` |
| 输出目录 | `dist/cloudflare` |
| 生产分支 | `main` |
| 正式域名 | `geekbird.org` |
| KV 绑定 | `SITE_CONFIG`，预览使用独立命名空间 |
| 配置后台 Secret | `ADMIN_PASSWORD`，至少 16 位；与 VPS 业务后台密码独立 |
| 可选构建变量 | `GEEKBIRD_API_BASE_URL` |

必须使用 **Pages** 的构建或 advanced-mode 上传流程。普通 Workers Builds 中存在另一个项目，并不代表 `geekbird` Pages 已配置 Git 预览；以 Pages 控制台的实际连接和部署状态为准。

产物为 `dist/cloudflare/`、`dist/geekbird-cloudflare-pages.zip`、`dist/cloudflare-manifest.json` 和 `dist/cloudflare-SHA256SUMS`。包内有五个公开页面、资源、`_worker.js`、`_routes.json`、`_headers` 和 404 页面，没有后端代码或数据库。

## 生产与预览

构建脚本读取 `CF_PAGES_BRANCH`：`main` 默认使用 `https://47.120.64.37/api/v1`；其他分支默认使用 `https://47.120.64.37/_gb-preview/api/v1`，同时显示测试提示。非 Pages 手动构建默认视为 `main`，制作预览包时需明确设置分支。

```sh
CF_PAGES_BRANCH=feat/self-hosted-booking-backend python3 scripts/cloudflare.py
```

`GEEKBIRD_API_BASE_URL` 可以指定其他测试地址，必须以 `/api/v1` 结尾；公网只允许 HTTPS，本地回环地址可使用 HTTP。设为空可禁用提交。API 和工作台地址由构建确定，不接受 KV 或网页查询参数覆盖。

每个允许使用的 Pages 预览 origin 都要同时加入服务器预览服务的 `GB_ALLOWED_ORIGINS` 和 Nginx 的 `geekbird_preview_origin` map，然后重启预览服务、检查并重载 Nginx。使用准确的分支别名即可，不开放任意 `*.pages.dev`。测试页面只使用虚构资料。

## 新配置后台

`/_gb-settings/` 保留 HTTP Basic 身份验证，用户名 `admin`，密码为 Cloudflare 的 `ADMIN_PASSWORD` Secret。设置页现在只保存 QQ，并提供业务工作台入口。

KV 的新版写入格式为 `{"schemaVersion":2,"emergencyQQ":"…"}`。旧记录读取时只取有效 QQ；旧问卷 URL、额外属性、API 地址和私有备注都不会输出。新版 Worker 固定输出 `/booking/`、`/feedback/`，接收状态由表单请求 API 的 `/meta` 获取并在服务器提交事务中再次检查。

未绑定 KV 时公开页面使用构建配置，设置后台返回清晰错误；KV 已绑定但读取失败时返回 503，不悄悄恢复过时配置。后台响应与动态配置禁止缓存。不要为这些路径开启强制缓存。

## 从旧外部问卷切换

1. 保留当前 Pages 部署和 `site-config` 备份，核对 QQ、原预约/反馈入口是否为空。原来关闭的入口应在新业务后台继续关闭。
2. 完成服务器部署与预览验收。确认真实 HTTPS、CORS、管理鉴权、重试、备份恢复和两个接收开关。
3. 核对 Pages 的生产分支、构建设置与生产 API 地址。在业务后台按实际安排开放接收，发布新版静态页面。
4. 检查所有主页面按钮均进入站内表单；旧 `/booking/` 变为实际申请页。测试一条明确标记的预约和反馈，核对后台记录。
5. 历史问卷答卷仍在原平台，不会自动导入。代码回滚和 KV 回滚是两件事；如回到旧页面，必须同时恢复兼容的 KV 配置，避免旧 Worker 无法读取新结构。

提交说明版本发生变化时，前端与 API 必须一起发布；旧表单会提示刷新阅读，不能把旧确认当作新版本确认。

## 检查

```sh
python3 scripts/cloudflare.py
node --test tests/*.test.mjs
```

测试覆盖旧 KV 兼容、新配置写入、私有路径保护、站内入口、非法输入与故障情况。完整浏览器验收与服务器操作见 [后端部署说明](backend.md)。
