# 极客鸟 GeekBird

极客鸟官网：**<https://geekbird.org/>**。让设备多用一天，让热爱多走一程。

本分支 `feat/self-hosted-booking-backend` 实现站内预约、服务反馈与自建业务后台。静态网页继续部署在 Cloudflare Pages；表单通过 HTTPS 提交到 `47.120.64.37` 上的 FastAPI 服务，数据保存在本机 SQLite。目前完整站点已部署在 **<https://47.120.64.37/>**，预约与反馈接收已开放；Cloudflare 正式页面后续单独切换。

## 页面与管理

| 路径 | 用途 |
| --- | --- |
| `/`、`/service/`、`/disclaimer/` | 首页、服务与信息使用说明 |
| `/booking/` | 站内维修申请，提交后给出编号，等待志愿者联系 |
| `/feedback/` | 服务反馈、三个维度评分及志愿时长填报 |
| `https://geekbird.org/_gb-settings/` | Cloudflare 配置后台，维护公开联系 QQ |
| `https://47.120.64.37/_gb-data/` | 独立业务后台：查看记录、跟进状态、核实时长、导出 CSV、控制接收 |

业务后台用户名为 `admin`，密码与 Cloudflare 设置后台独立。部署生成的密码保存在服务器 `/etc/geekbird-api/credential.password`，仅 root 可读。密码和数据库不会进入源码或静态发布包。

预约代表服务申请，具体安排需联系确认。反馈保留用户填报时长，由管理员另行核实确认；不自动给多人重复计时。首版不含账号注册、自动排班、图片上传或自动通知。

## 本地检查

需要 Python 3.11+、Node.js 22+；静态构建本身只需 Python 标准库。

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

浏览器验收脚本自动启动临时数据库、接口和静态服务器，验证桌面、手机、丢失回执后的重试、后台处理、时长核实、导出及暂停接收；结束后清理临时数据。截图默认在 `/tmp/geekbird-browser-results/`。CI 使用相同流程。

只预览页面可运行 `python3 -m http.server 8080 --bind 127.0.0.1`；完整提交测试应使用上面的隔离验收脚本。新增中文文案后运行 `python3 scripts/subset_fonts.py` 更新本地字体。

## 构建与部署

```sh
# Cloudflare 静态页面、Worker 和校验清单
python3 scripts/cloudflare.py

# 独立的私有 API 发布包
python3 scripts/api.py

# 通过 SSH 部署 API、预览 API 和每日备份任务
python3 scripts/deploy_api.py

# 部署 VPS 的完整页面与配置后台（已有 API 后运行）
python3 scripts/deploy_vps.py
```

Pages 构建命令为 `python3 scripts/cloudflare.py`，输出目录 `dist/cloudflare`。`main` 默认连接正式 API；其他 Pages 分支连接独立预览 API，页面显示测试提示。可以通过构建环境变量 `GEEKBIRD_API_BASE_URL` 覆盖，设为空可禁用提交。

后端初装默认关闭正式接收；VPS 完整站点首次迁移按旧入口状态开放，后续发布保留后台开关。预览库与正式库使用不同用户、密码和数据目录。

旧 KV 中的预约/反馈外部链接在新版不再决定入口；站内路径由代码确定，接收开关以服务器数据库为准。联系 QQ 继续从 KV 读取。旧设置页面保存会提示刷新，避免旧结构覆盖新配置。

## 文档

- [后端设计方案](docs/backend-plan.md)：业务字段、架构与实施约定。
- [后端部署与验收记录](docs/backend.md)：地址、配置、测试、密码管理、备份恢复与回滚。
- [Cloudflare 构建和迁移](docs/cloudflare.md)：生产/预览分离及旧 KV 迁移。
- [历史 VPS 部署记录](docs/vps.md)：原网站和配置服务，独立于新业务 API。

项目的 `server/api/`、`deploy/`、测试和文档不属于公开静态资源。不要把整个仓库直接作为网站根目录；使用构建输出。
