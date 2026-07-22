# 使用方法

1. 新建一个空 Git 仓库，或打开准备开发的仓库。
2. 把本目录中的 `AGENTS.md` 放到仓库根目录。
3. 把 `MASTER_PROMPT.md` 放到仓库根目录或直接复制全文给 Codex。
4. 把 `.env.example` 放到根目录。
5. 在仓库创建 `fixtures/`，放入以下文件：
   - `【吉拾开张】直播间数据登记系统（AI）.xlsx`
   - `【吉拾开张】直播部门排班系统(2).xlsx`
   - 参考截图
6. 给 Codex 的第一条消息：

```text
请读取根目录 AGENTS.md 和 MASTER_PROMPT.md，严格按主任务书执行。先检查 fixture，创建 docs/EXEC_PLAN.md，然后直接搭建可运行应用。没有飞书凭证时使用 mock 和 Excel fixture，不要停工。
```

7. 不要把真实 App Secret、机器人 Webhook 或签名密钥提交到仓库。只写入本地 `.env` 或部署平台的 Secret 管理。
8. Codex 完成后要求其运行 `make check` 和 `make verify-production`，并查看 `docs/TEST_REPORT.md`。
