# 极客鸟 GeekBird

极客鸟官网已正式上线：**<https://geekbird.org/>**。

一个志愿电脑维修组织的网站。让设备多用一天，让热爱多走一程。

网站使用原生 HTML、CSS 与 JavaScript，部署于 Cloudflare Pages。预约与服务反馈直接打开外部问卷星表单；联系 QQ、预约和反馈链接可通过密码保护的后台维护，配置保存在 Cloudflare KV。

## 页面与入口

| 页面 | 地址 | 内容 |
| --- | --- | --- |
| 首页 | <https://geekbird.org/> | 黑色羽毛主视觉、组织故事与服务入口 |
| 维修服务 | <https://geekbird.org/service/> | 服务范围、维修理念与预约入口 |
| 免责声明 | <https://geekbird.org/disclaimer/> | 建筑光井主视觉；服务范围、备份、维修风险、授权、隐私与责任说明 |

免责声明是第三个主页面，可从各页导航及页脚进入。预约按钮直接打开配置的外部表单，无需经过站内中转页；旧 `/booking/` 地址仅保留兼容，不出现在主导航或站点地图中，也不参与搜索收录。本站没有预约表单或提交接口。

默认外部入口：

- 预约维修：<https://www.wjx.top/m/93277562.aspx>。
- 服务反馈：<https://www.wjx.top/m/93298004.aspx>。

## 日常管理

管理后台：<https://geekbird.org/_gb-settings/>。后台不出现在公开导航中，页面与接口均需要身份验证。用户名为 `admin`，密码为 Cloudflare 中设置的 `ADMIN_PASSWORD` Secret。

| 配置 | 用途 |
| --- | --- |
| `emergencyQQ` | 联系 QQ，5–15 位数字；留空显示“QQ 号暂未公布” |
| `bookingUrl` | 外部预约平台的完整 HTTP(S) 地址；留空暂停预约入口 |
| `feedbackUrl` | 外部反馈表单的完整 HTTP(S) 地址；留空暂停反馈入口 |

首次保存前使用 [config.js](config.js) 中的默认值；保存后以 KV 配置为准，重新部署不会覆盖。保存后稍后刷新网站验证，KV 全球同步通常需要约 1 分钟，部分地区可能更久。

若后台仍保存旧公众号链接，需要在后台将预约地址更新为实际表单。旧记录仅缺少 `feedbackUrl` 时，会读取源码默认反馈地址；已保存的自定义值或空字符串不会被覆盖。旧管理页需刷新后再保存全部三个字段。

QQ 与表单链接是公开配置；管理密码不写入源码。HTML 通过 `data-config-link` 声明配置键，由 `assets/app.js` 统一绑定地址；未配置或无效时禁用对应入口并提示。未启用 JavaScript 时显示启用提示。

## 本地预览与检查

本地预览公开页面：

```sh
python3 -m http.server 8080 --bind 127.0.0.1
```

打开 <http://127.0.0.1:8080/>。静态预览使用源码配置，不运行后台或 KV。

修改中文文案后，先更新本地字体子集：

```sh
python3 scripts/subset_fonts.py
```

字体更新需要联网；网页使用本地字体文件，访客无需连接外部字体服务。

发布前检查与构建：

```sh
python3 scripts/cloudflare.py
node --test tests/*.test.mjs
```

构建仅需 Python 3，测试需要 Node.js 22 或以上。构建会检查页面链接、锚点、图片与配置，并生成 `dist/cloudflare/`、`dist/geekbird-cloudflare-pages.zip` 和 SHA-256 清单。产物包含公开页面、旧地址兼容页及 Pages Worker，不包含密码、VPS 服务、文档或设计源稿。

## Cloudflare 部署与维护

仓库：`galiandan/geekbird`，生产分支：`main`。Pages 项目使用以下构建配置：

| 设置 | 值 |
| --- | --- |
| 框架预设 | `None` |
| 构建命令 | `python3 scripts/cloudflare.py` |
| 构建输出目录 | `dist/cloudflare` |
| 根目录 | 仓库根目录（留空） |
| 正式自定义域 | `geekbird.org` |
| Secret | `ADMIN_PASSWORD`，至少 16 位 |
| KV 绑定 | `SITE_CONFIG`，绑定保存站点配置的命名空间 |

使用 Pages 的 Git 集成时，推送 `main` 会触发构建部署。密码、绑定或环境设置变更后需重新部署；预览环境使用独立 KV，避免影响正式配置。

正式页面 canonical、`robots.txt` 和站点地图均使用 `https://geekbird.org`；站点地图只包含三个主页面。后台响应禁止缓存和搜索收录。回滚 Pages 部署只回滚代码，不会回滚 KV 中保存的配置。

首次配置、`SITE_CONFIG` 未绑定等故障排查，以及本地 Wrangler 验收步骤，见 [Cloudflare 部署说明](docs/cloudflare.md)。历史部署资料见 [VPS 部署记录](docs/vps.md) 与 [Nginx 部署说明](docs/deployment.md)，VPS 与 Cloudflare 的配置和密码互不同步。

## 项目结构

```text
geekbird/
├── index.html                 首页
├── service/index.html         服务页
├── disclaimer/index.html      免责声明（第三页）
├── booking/index.html         旧预约地址兼容页
├── config.js                  初始业务配置
├── assets/                    统一样式、交互、本地字体、Logo 与背景图
├── cloudflare/                Pages Worker、管理页、响应头与站点地图
├── scripts/                   构建、校验、图片导出与字体子集工具
├── tests/                     预约链接及后台配置测试
├── docs/                      部署、文案与图片维护说明
├── design/                    原始设计稿与参考图，不部署
├── deploy/                    历史 Nginx / systemd 配置
├── server/                    历史 VPS 配置服务
└── dist/                      生成的发布产物，不纳入版本管理
```
