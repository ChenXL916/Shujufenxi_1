# 飞书开放平台配置

## 应用与权限

在飞书开放平台创建企业自建应用，启用网页应用能力并添加回调地址：

```text
https://你的域名/auth/feishu/callback
```

为应用开通用户身份读取、多维表格 Base/Table/Field/Record 只读权限，并由用户 OAuth 授权读取两个目标 Base。若使用应用机器人向群推送，还需添加“机器人”能力、开通应用身份权限 `im:message:send_as_bot`、发布版本，并把机器人加入目标群且允许发言。最小化授权；生产 App Secret 仅放入环境变量或密钥管理服务。

## 环境变量

```text
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_REDIRECT_URI=https://你的域名/auth/feishu/callback
FEISHU_LIVE_APP_TOKEN=
FEISHU_LIVE_TABLE_ID=
FEISHU_LIVE_VIEW_ID=
FEISHU_SCHEDULE_APP_TOKEN=
FEISHU_SCHEDULE_TABLE_ID=
FEISHU_SCHEDULE_VIEW_ID=
FEISHU_SCHEDULE_YEAR=2026
FEISHU_BOT_WEBHOOK_URL=
FEISHU_BOT_SECRET=
FEISHU_BOT_CHAT_ID=
```

App Token 可从 Base URL 中识别；URL 中的 `table=blk...` 可能只是页面块标识，程序会通过 Base API 自动发现真实的 `tbl...` 表。实绩 Base 自动发现所有直播间表，排班 Base 自动识别主播排班和人员排班。应用使用用户访问令牌读取 Base，500 条分页，429/超时/5xx 指数退避；401/403 不重试并返回清晰权限错误。

群预警支持两种发送方式：配置 `FEISHU_BOT_CHAT_ID` 时使用现有应用机器人和 tenant access token；配置 Webhook/Secret 时使用群自定义机器人。两种方式同时配置时优先 Webhook。应用机器人发送使用事件 UUID 去重，避免超时重试产生重复消息。

## 验证步骤

1. 管理后台 → 数据源 → “测试连接”。
2. 点击“扫描字段”，核对 Table、字段名和字段映射。
3. 执行 `make sync-feishu` 或“立即同步”。
4. 在同步记录中核对读取/新增/更新/未变化/无效数量。
5. 管理后台 → 系统设置 → 测试机器人卡片，确认飞书返回消息 ID且群内收到卡片。
6. 退出开发旁路，以飞书账号登录，确认 Viewer/Operator/Admin 与直播间权限。

若未配置 App ID/Secret，命令会明确切换到 Excel fixture + Mock Feishu API，不阻塞应用、图表、预警、权限和 E2E 验收。
