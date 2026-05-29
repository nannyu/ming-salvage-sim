# 部署指南

推荐架构：**Supabase（认证+元数据）+ Railway（后端 API）+ Vercel（前端 CDN）**

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│   Vercel    │────▶│    Railway       │────▶│  Supabase   │
│  (前端 SPA) │     │  (FastAPI 后端)   │     │ (Auth + DB) │
│  静态文件CDN │     │  SQLite 存档     │     │  profiles   │
└─────────────┘     │  LLM 调用        │     │  audit_logs │
                    └──────────────────┘     └─────────────┘
```

## 第一步：Supabase 配置

1. 登录 [supabase.com](https://supabase.com)，创建新项目
2. 进入 SQL Editor，执行 `docs/supabase-multi-user.sql` 建表
3. 记录以下信息（Settings → API）：
   - Project URL（如 `https://xxxxx.supabase.co`）
   - `anon` public key
   - `service_role` key（保密！）
4. （可选）关闭邮箱验证：Authentication → Providers → Email → 关闭 "Confirm email"

## 第二步：Railway 部署后端

1. 登录 [railway.app](https://railway.app)
2. New Project → Deploy from GitHub repo → 选择 `ming-salvage-sim`
3. 添加持久卷（Volume）：
   - 点击服务 → Settings → Volumes → Add Volume
   - Mount Path: `/data`
   - 这是用户存档的持久化存储，删除卷 = 丢失所有存档
4. 设置环境变量（Settings → Variables）：

   ```
   PORT=8010
   MING_SIM_DATA_DIR=/data
   SUPABASE_URL=https://xxxxx.supabase.co
   SUPABASE_ANON_KEY=eyJ...（anon key）
   SUPABASE_SERVICE_ROLE_KEY=eyJ...（service_role key）
   ```

   可选（如果想给没配 API key 的用户提供默认模型）：
   ```
   OPENAI_API_KEY=（留空，让用户自己配）
   OPENAI_BASE_URL=https://api.deepseek.com
   OPENAI_MODEL=deepseek-chat
   ```

5. 设置端口：Settings → Networking → Port: `8010`
6. 部署完成后记录 Railway 分配的域名（如 `https://ming-salvage-sim-production.up.railway.app`）

### Railway 注意事项

- **持久卷是必须的**：用户的游戏存档（SQLite）存在卷里，没有卷每次部署都会丢失
- **超时设置**：LLM 调用可能耗时 30-180 秒，Railway 默认支持长连接
- **内存**：建议至少 512MB，多用户同时在线时每个 WebGame 实例约占 50-100MB

## 第三步：Vercel 部署前端

1. 登录 [vercel.com](https://vercel.com)
2. Import Git Repository → 选择 `ming-salvage-sim`
3. 配置：
   - **Framework Preset**: Other
   - **Root Directory**: `web`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. 设置环境变量：

   ```
   VITE_SUPABASE_URL=https://xxxxx.supabase.co
   VITE_SUPABASE_ANON_KEY=eyJ...（anon key，和 Railway 一样）
   BACKEND_URL=https://你的railway域名.up.railway.app
   ```

5. 部署

### Vercel rewrites 说明

`web/vercel.json` 配置了 URL 重写规则：
- `/api/*` → 转发到 Railway 后端
- `/portraits/*` → 转发到 Railway（自定义立绘）
- 其他路径 → `index.html`（SPA 路由）

## 第四步：验证

1. 打开 Vercel 分配的域名
2. 应该看到登录页面
3. 注册账号 → 登录 → 设置 API Key → 开始新游戏

## 可选：自定义域名

- Vercel：Settings → Domains → 添加你的域名
- Railway：Settings → Networking → Custom Domain
- 如果前端用自定义域名，记得更新 Railway 的 CORS 配置（当前只允许 localhost:5173）

### 更新 CORS

在 `web_app.py` 中找到 `CORSMiddleware` 配置，添加你的前端域名：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://你的vercel域名.vercel.app",
        "https://你的自定义域名.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

或者用环境变量动态配置（推荐）。

## 备选方案：全部放 Railway

如果不想分开部署，可以全放 Railway（后端已经内置了静态文件服务）：

1. 不需要 Vercel
2. Railway 部署后直接访问 Railway 域名即可
3. 环境变量加上 `VITE_SUPABASE_URL` 和 `VITE_SUPABASE_ANON_KEY`
4. 但需要在部署前先 build 前端（Dockerfile 已处理）

这种方案更简单，缺点是没有 CDN 加速静态资源。

## 费用估算

| 服务 | 免费额度 | 预计月费 |
|------|---------|---------|
| Supabase | 50K MAU, 500MB DB | 免费（小规模） |
| Railway | $5 credit/月 | ~$5-10（取决于用户量） |
| Vercel | 100GB 带宽 | 免费（Hobby plan） |

对于个人项目或小规模使用，总成本约 $5-10/月。
