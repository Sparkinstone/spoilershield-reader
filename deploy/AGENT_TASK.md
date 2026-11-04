# 服务器 Agent 任务单（textadventure.top）

这份文件是给**服务器上的 Agent** 执行的最小任务单。完整的宝塔建站、SSL、DNS 仍由人完成；
Agent 只负责“把应用装好并跑起来”，不要自由发挥成 Docker/Caddy 方案。

## 环境事实

- OpenCloudOS 9，root，宝塔面板 11.4（Nginx 已监听 80/443）；
- 系统 Python **3.11.6**，**不需要安装 Python**；
- SELinux **Disabled**，不要执行 `setsebool`；
- 大陆服务器，域名已备案；
- 项目根目录必须是 `/www/wwwroot/textadventure.top`，不能是它的子目录。

## 禁止事项

1. 不要运行 `docker compose`、Dockerfile、Caddy，不要改动 80/443 监听；
2. 不要安装 Python 3.11/3.12（已有 3.11.6）；
3. 不要执行任何 SELinux 命令；
4. 不要修改 DNS、备案、宝塔面板设置；
5. 不要打印、复制、提交 `.env` 的内容；
6. 不要自行编造 `LLM_API_KEY`、`ADMIN_PASSWORD`；
7. 不要动 `/www/server/panel/vhost/nginx/` 下的宝塔站点配置（由人通过面板操作）。

## 前置检查（任一失败就停下并报告）

```bash
python3 --version                 # 必须是 3.11.x
test -f /www/wwwroot/textadventure.top/app/main.py && echo code-ok
free -h                           # 建议 >= 3.5G 可用
df -h /www                        # 建议 >= 10G 可用
ss -lntp | grep ':8000 ' || true  # 8000 不能被占用
```

## 执行步骤

```bash
set -euo pipefail
APP=/www/wwwroot/textadventure.top

# 1. 系统依赖（不装 Python）
dnf -y install python3-pip python3-devel gcc gcc-c++ make libgomp rsync bind-utils

# 2. 运行用户与数据目录
useradd --system --home-dir "$APP" --shell /sbin/nologin spoilershield || true
mkdir -p "$APP/data/uploads" "$APP/models"
chown -R spoilershield:spoilershield "$APP"

# 3. venv + 依赖
cd "$APP"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4. 预下载 embedding 模型（国内镜像）
HF_ENDPOINT=https://hf-mirror.com HF_HOME="$APP/models" \
  .venv/bin/python -c \
  "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# 5. .env 必须由人准备好；Agent 只检查存在性和权限
test -f "$APP/.env" || { echo "MISSING .env: human must create it"; exit 2; }
chown spoilershield:spoilershield "$APP/.env"
chmod 600 "$APP/.env"

# 6. systemd
cp "$APP/deploy/baota/spoilershield.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now spoilershield

# 7. 等就绪并验证
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/healthz >/tmp/healthz.json 2>/dev/null; then break; fi
  sleep 1
done
cat /tmp/healthz.json
systemctl --no-pager --full status spoilershield | head -n 20
```

## 人工必须完成的部分（Agent 不要代做）

1. 宝塔 → 网站 → 添加站点 `textadventure.top` / `www.textadventure.top`，纯静态；
2. 宝塔 → SSL → Let's Encrypt → 强制 HTTPS；
3. 宝塔 → 反向代理 → `http://127.0.0.1:8000`，发送域名 `$host`，缓存关闭；
4. 站点配置里确认 `client_max_body_size 25m`、`proxy_read_timeout 300s`、
   `X-Forwarded-For` / `X-Forwarded-Proto` / `Host` 三个 header；
5. 在 `.env` 填入 LLM key、`ADMIN_PASSWORD`，以及：
   ```ini
   DATABASE_URL=sqlite:////www/wwwroot/textadventure.top/data/spoiler_shield.db
   UPLOAD_DIR=/www/wwwroot/textadventure.top/data/uploads
   HF_HOME=/www/wwwroot/textadventure.top/models
   ALLOW_UPLOADS=true
   ```
6. 上传一本样书后，把 `ALLOW_UPLOADS=false` 并重启服务。

## Agent 完成后必须报告

```text
python3 --version
.venv/bin/python -c "import torch, sentence_transformers, fastapi; print(torch.__version__, fastapi.__version__)"
systemctl is-enabled spoilershield; systemctl is-active spoilershield
curl -fsS http://127.0.0.1:8000/healthz
ls -ld data data/uploads models
journalctl -u spoilershield -n 30 --no-pager
```

如果模型下载、pip 安装或 `healthz` 失败，报告具体命令和错误，不要继续改端口/换方案。
