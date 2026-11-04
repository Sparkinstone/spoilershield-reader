# 宝塔面板部署 SpoilerShield

适用环境：**宝塔 Linux 面板 11.4.0（腾讯云专享版）+ OpenCloudOS 9 + 域名 textadventure.top**。

当前目标机器已确认：

- 服务器在中国大陆，域名**已备案**；
- 系统自带 **Python 3.11.6**（直接用 `python3`，不需要另装）；
- **SELinux = Disabled**（跳过所有 SELinux 相关步骤）；
- 模型走官方 `https://api.deepseek.com/v1`，`deepseek-flash` 已用同一把 key 实测可用。

宝塔的 Nginx 已经占用 80/443，所以不要使用 `docker-compose.yml` 里的 Caddy；
应用只监听 `127.0.0.1:8000`，由宝塔 Nginx 反向代理并负责 HTTPS。

## 0. 先确认三件事

1. **服务器地域与备案**
   腾讯云中国大陆地域的域名必须完成 ICP 备案，否则 80/443 会被拦截。香港/新加坡等
   境外地域不需要备案。`textadventure.top` 如果还没备案，先确认服务器地域，否则后面
   SSL 和访问都会卡住。
2. **DNS**：在 DNSPod 把 `@` 和 `www` 的 A 记录指向服务器公网 IP。
3. **Python 版本**：OpenCloudOS 9 默认可能是 Python 3.9，依赖里较新的 numpy/torch 组合
   容易装不上。先执行 `python3 --version`；低于 3.10 就按下面安装 3.11/3.12。

## 1. 目录规划

```
/www/wwwroot/textadventure.top/      代码、.venv、.env
/www/wwwroot/textadventure.top/data/ SQLite + uploads（必须备份）
/www/wwwroot/textadventure.top/models/ 预下载的 embedding 模型
```

## 2. 腾讯云安全组 + 宝塔安全

腾讯云控制台 → 安全组，入站放行：

| 端口 | 来源 | 用途 |
| --- | --- | --- |
| 22 | 你的公网 IP | SSH |
| 80 / 443 | 0.0.0.0/0 | 网站 |
| 8888（或你改的宝塔端口） | 你的公网 IP | 面板，**不要对全网开放** |

宝塔面板 → 安全，做同样的放行；**不要放行 8000**，它只给本机 Nginx 用。

如果系统 firewalld 仍在管理：

```bash
firewall-cmd --permanent --add-service=http --add-service=https
firewall-cmd --reload
```

## 3. DNS

DNSPod 添加：

```
@    A    服务器公网 IP
www  A    服务器公网 IP
```

验证：

```bash
dig +short textadventure.top @119.29.29.29
```

返回服务器 IP 后再继续（证书申请依赖它）。

## 4. 系统依赖

你的机器已经是 Python 3.11.6，不需要再装 Python：

```bash
cat /etc/os-release
python3 --version          # 应为 3.11.x

dnf -y install python3-pip python3-devel \
    gcc gcc-c++ make libgomp rsync bind-utils

# 确认 venv 可用；如果报 ensurepip 缺失，先装 python3-pip 再试
python3 -m venv --help >/dev/null && echo venv-ok
```

## 5. 部署代码

在宝塔「网站」里先添加站点（下一步会详细配），根目录就是
`/www/wwwroot/textadventure.top`。然后上传代码：

```bash
APP=/www/wwwroot/textadventure.top
cd /tmp
git clone <你的仓库地址> spoilershield
rsync -a --exclude '.git' /tmp/spoilershield/ "$APP/"
```

没有仓库就用宝塔文件管理器上传 zip 并解压到 `$APP`。确认存在
`$APP/app/main.py`、`$APP/requirements.txt`。

创建运行用户与数据目录：

```bash
useradd --system --home-dir "$APP" --shell /sbin/nologin spoilershield || true
mkdir -p "$APP/data/uploads" "$APP/models"
chown -R spoilershield:spoilershield "$APP"
```

## 6. 虚拟环境与依赖

```bash
APP=/www/wwwroot/textadventure.top
cd "$APP"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip

# CPU 版 torch（不要装 CUDA 版，否则多几个 GB）
.venv/bin/pip install torch==2.5.1 \
  --index-url https://download.pytorch.org/whl/cpu

# 国内服务器用清华源装其余依赖
.venv/bin/pip install -r requirements.txt \
  -i https://pypi.tuna.tsinghua.edu.cn/simple
```

预下载 embedding 模型（国内访问 HuggingFace 常常超时，用镜像）：

```bash
HF_ENDPOINT=https://hf-mirror.com \
HF_HOME="$APP/models" \
"$APP/.venv/bin/python" -c \
  "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

看到模型下载完成、没有报错即可。运行时是缓存优先，不再依赖 HuggingFace。

## 7. 配置 .env

```bash
cd "$APP"
cp .env.example .env
chmod 600 .env
```

编辑成至少这样（`DATABASE_URL` 是 4 个斜杠）：

```ini
# 与 DSH 使用同一把 DeepSeek key；官方端点已实测 deepseek-flash 可用
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-flash

ADMIN_USER=admin
ADMIN_PASSWORD=<openssl rand -base64 24 生成一个>

DATABASE_URL=sqlite:////www/wwwroot/textadventure.top/data/spoiler_shield.db
UPLOAD_DIR=/www/wwwroot/textadventure.top/data/uploads
HF_HOME=/www/wwwroot/textadventure.top/models

ALLOW_UPLOADS=true
SPOILER_CONFIDENCE_THRESHOLD=0.7
```

最后把属主改回运行用户：

```bash
chown -R spoilershield:spoilershield "$APP"
```

## 8. 启动 systemd 服务

```bash
cp "$APP/deploy/baota/spoilershield.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now spoilershield
systemctl status spoilershield --no-pager
curl -fsS http://127.0.0.1:8000/healthz
```

`healthz` 返回 `{"status":"ok",...}` 才算成功。看日志：

```bash
journalctl -u spoilershield -f
```

### SELinux

你的机器 `getenforce` 是 **Disabled**，这一节可以跳过。

如果换到 SELinux 为 Enforcing 的机器，Nginx 连 127.0.0.1 会被拦，表现为 **502**：

```bash
getenforce
setsebool -P httpd_can_network_connect 1
```

## 9. 宝塔建站、SSL、反向代理

### 9.1 建站

宝塔 → 网站 → 添加站点：

- 域名：`textadventure.top` 和 `www.textadventure.top`
- 根目录：`/www/wwwroot/textadventure.top`
- PHP 版本：**纯静态**
- 不创建数据库、不创建 FTP

### 9.2 SSL

网站 → 设置 → SSL → Let's Encrypt → 申请（文件验证）→ 开启「强制 HTTPS」。

如果申请失败：先确认 DNS 已生效、80 端口放行、域名已备案（大陆地域），
也可以改用 DNS 验证或上传已有证书。

### 9.3 反向代理

网站 → 设置 → 反向代理 → 添加反向代理：

- 名称：`spoilershield`
- 目标 URL：`http://127.0.0.1:8000`
- 发送域名：`$host`
- 缓存：关闭

保存后点该代理右侧「配置文件」，确认存在（可参考
[nginx-proxy.conf](nginx-proxy.conf)）：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

再在站点「配置文件」的 `server { }` 里补：

```nginx
client_max_body_size 25m;
proxy_read_timeout 300s;
proxy_send_timeout 300s;
```

`X-Forwarded-For` 很重要：应用会据此识别“请求经过反代”，没有 `ADMIN_PASSWORD`
时会直接拒绝后台访问。

保存后重载 Nginx：

```bash
/www/server/nginx/sbin/nginx -t && systemctl reload nginx
```

## 10. 验证

```bash
curl -I https://textadventure.top
curl -I https://textadventure.top/static/app.css
curl -fsS https://textadventure.top/healthz
```

浏览器打开 `https://textadventure.top`：

1. 上传一本样书（此时 `ALLOW_UPLOADS=true`）；
2. 进入阅读页，点段落发一条评论，确认弹窗/审核状态正常；
3. 打开 `https://textadventure.top/admin`，用 `ADMIN_USER` / `ADMIN_PASSWORD` 登录。

### 关闭上传（建议）

公开作品集预置一本书后，把 `.env` 改成：

```ini
ALLOW_UPLOADS=false
```

然后：

```bash
systemctl restart spoilershield
```

首页会隐藏上传表单，`POST /upload` 返回 403；阅读和评论不受影响。

## 11. 备份

使用 [backup.sh](backup.sh)，或在宝塔「计划任务」添加 Shell 脚本（每天 03:20）：

```bash
bash /www/wwwroot/textadventure.top/deploy/baota/backup.sh
```

备份输出在 `/www/backup/spoilershield/`：SQLite 在线备份 + uploads 压缩包，保留 14 天。
再把该目录同步到腾讯云 COS（宝塔有 COS 插件）或另一台机器。

恢复：停服务 → 替换 `data/spoiler_shield.db` 和 `data/uploads/` → 启动。

## 12. 更新

```bash
APP=/www/wwwroot/textadventure.top
cd "$APP"
# 先备份
bash deploy/baota/backup.sh

git pull        # 或重新上传代码
.venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
systemctl restart spoilershield
journalctl -u spoilershield -n 50 --no-pager
```

项目没有 Alembic；如果表结构变化，先备份数据库再升级。

## 13. 排错

| 现象 | 排查 |
| --- | --- |
| 502 Bad Gateway | `systemctl status spoilershield`；SELinux `httpd_can_network_connect`；`curl 127.0.0.1:8000/healthz` |
| 504 / 评论很久失败 | Nginx `proxy_read_timeout`、`LLM_TIMEOUT`、服务器到 LLM 网关的网络 |
| 413 | Nginx `client_max_body_size` 与 `.env` 的 `MAX_UPLOAD_MB` |
| `/admin` 401/403 | 代理后必须设 `ADMIN_PASSWORD`；Basic Auth 用户名密码；确认有 `X-Forwarded-For` |
| 上传卡住几分钟 | 正常：整本书逐段 embedding，看 `top` 的 CPU |
| 模型加载失败 | 第 6 步预下载是否成功；`HF_HOME` 是否指向 `$APP/models` |
| SSL 申请失败 | DNS、80 端口、备案、Let's Encrypt 速率限制 |
| 域名打不开但 IP 能访问 | 备案 / 安全组 / DNS 未生效 |

## 14. 资源与安全

- 2C4G 起步；模型常驻约 1 GB RSS。2G 内存建议加 2G swap：
  ```bash
  fallocate -l 2G /swapfile && chmod 600 /swapfile
  mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  ```
- 宝塔面板：改默认端口、限制 IP 访问、强密码、开启面板 SSL；
- 只放行 22/80/443，8000 不对外；
- `.env` 权限 600，不进 git；
- 公开演示建议 `ALLOW_UPLOADS=false`，避免上传把 CPU 打满；
- LLM key 设置额度告警；评论没有用户体系，无法按用户限流，必要时在宝塔 Nginx
  里对 `/comment` 做 `limit_req`。

## 附：Python 装不上时的 Docker 备选

如果 `dnf` 里没有 Python 3.11/3.12，或者不想在宿主机装 torch：

1. 宝塔 → 软件商店 → Docker（或 `dnf install docker`）安装并启动；
2. 项目根目录准备好 `.env`（同上）；
3. 只启动应用容器（80/443 仍由宝塔 Nginx 占用）：

```bash
cd /www/wwwroot/textadventure.top
docker compose -f deploy/baota/docker-compose.app.yml up -d --build
docker compose -f deploy/baota/docker-compose.app.yml logs -f app
curl -fsS http://127.0.0.1:8000/healthz
```

该 compose 文件只发布 `127.0.0.1:8000`，数据存 Docker 卷 `spoilershield-baota_app-data`。
宝塔反向代理配置与第 9.3 节完全相同。备份时从容器里导出：

```bash
docker compose -f deploy/baota/docker-compose.app.yml exec app \
  python -c "import sqlite3; s=sqlite3.connect('/data/spoiler_shield.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
docker compose -f deploy/baota/docker-compose.app.yml cp app:/data/backup.db /www/backup/
```

首次构建同样要下载 torch 和模型，网络受限时先在本地构建并推送到腾讯云 TCR。

## 15. 已知限制（不影响上线，但要知道）

- 单 worker + SQLite：适合演示和小流量，不适合高并发写；
- 上传是同步的，一本大书会占住 worker，期间其他请求变慢；
- 没有任务队列，失败上传需要重试；
- 没有用户登录，评论公开、不可归属；
- 默认 embedding 是英文模型，中文语义召回偏弱；
- 98.8% 的评测指标来自合成评论，不要当线上效果宣传。
