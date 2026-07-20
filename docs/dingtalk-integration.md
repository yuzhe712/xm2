# 钉钉接入：手把手教程

目标：让 IntelliTicket 的工单通知发到你的钉钉群。

---

## 第一步：在钉钉里创建两个群

打开电脑版钉钉。

### 创建运维群

1. 点左上角 **+** → **发起群聊**
2. 随便拉一个人（比如同事），群名改为 `IntelliTicket 运维告警群`
3. 创建好后把拉进来的人踢掉也没关系，机器人不需要成员

### 创建员工群

同上，群名叫 `IntelliTicket 工单通知群`。

最终你有两个群：一个收运维告警，一个收工单解决通知。

---

## 第二步：给运维群加机器人

### 2.1 进入机器人设置

1. 打开 `IntelliTicket 运维告警群`
2. 点右上角的 **齿轮图标**（群设置）
3. 往下滑，找到 **智能群助手**
4. 点 **添加机器人**
5. 在弹窗里选最后一个 **自定义机器人**（通过 Webhook 接入）

### 2.2 配置机器人

1. **机器人名字**：填 `IntelliTicket 运维通知`
2. **安全设置**：选 **自定义关键词**，填 `TCK`
   > 工单编号格式为 TCK-xxxxxxxx，每条通知肯定包含"TCK"。用纯英文 ASCII 字符避免编码歧义。
3. 勾选 **我已阅读并同意**
4. 点 **完成**

### 2.3 复制 Webhook 地址

弹窗里会出现一个 URL，格式像这样：

```
https://oapi.dingtalk.com/robot/send?access_token=a1b2c3d4e5f6...
```

**复制整段 URL，存到记事本里**。点完"完成"后这个地址就看不到了，必须现在复制。

### 2.4 看到机器人加入的提示

群里会出现一条消息：`IntelliTicket 运维通知：已加入群聊`。这说明机器人创建成功。

---

## 第三步：给员工群加机器人

重复第二步的所有操作，唯一的区别：

- 机器人名字：`IntelliTicket 工单通知`
- 安全设置：仍然选 **自定义关键词**，填 `工单`
- 复制 Webhook URL，存到另一个记事本

现在你有两个 Webhook URL：

```
运维群：https://oapi.dingtalk.com/robot/send?access_token=TOKEN_A
员工群：https://oapi.dingtalk.com/robot/send?access_token=TOKEN_B
```

---

## 第四步：测试 Webhook 能不能用

打开终端（cmd 或 PowerShell），用 curl 发一条测试消息：

```bash
curl -X POST "https://oapi.dingtalk.com/robot/send?access_token=你的TOKEN" ^
  -H "Content-Type: application/json" ^
  -d "{\"msgtype\":\"markdown\",\"markdown\":{\"title\":\"测试\",\"text\":\"## 测试消息\n\n这是一条来自 **IntelliTicket** 的测试工单通知。\n\n**工单编号**: TCK-TEST-001\"}}"
```

> PowerShell 用户：把 `^` 换成 `` ` ``（反引号）

去对应钉钉群看一眼——如果收到了一条"测试消息"，说明 Webhook 通了。

**常见错误**：
- 收到 `errcode: 310000`：安全设置没通过，检查关键词是否包含"工单"
- 收到 `errcode: 300001`：token 过期或被删除，重新创建机器人
- 没反应：URL 粘错了，检查 `access_token=` 后面是否完整

---

## 第五步：配置 IntelliTicket

打开项目根目录的 `.env` 文件（没有就新建）：

```
# .env 文件，放在 F:\wdxm\2.企业工单系统\.env

DINGTALK_ENABLED=true
DINGTALK_OPERATOR_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=你的运维群TOKEN
DINGTALK_EMPLOYEE_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=你的员工群TOKEN
```

把两个 `access_token=xxx` 替换成你刚才复制的真实地址。

> 如果你在用 `F:\wdxm\wdapi\secrets.toml`，在里面加：
> ```toml
> [IntelliTicket]
> DINGTALK_ENABLED = true
> DINGTALK_OPERATOR_WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send?access_token=TOKEN_A"
> DINGTALK_EMPLOYEE_WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send?access_token=TOKEN_B"
> ```

---

## 第六步：启动项目，走一遍真实流程

### 6.1 启动后端

```bash
cd F:\wdxm\2.企业工单系统
uvicorn intelliticket_backend.main:app --reload
```

看到 `Uvicorn running on http://127.0.0.1:8000` 就 OK。

### 6.2 启动前端

```bash
cd F:\wdxm\2.企业工单系统\frontend
npm run dev
```

### 6.3 走完整流程

| 步骤 | 操作 | 角色 |
|---|---|---|
| 1 | 打开前端，选 **基础设施 / 内部支持服务台** | 员工 |
| 2 | 登录 `wangwu` / `wangwu123` | 员工 |
| 3 | 在工单提交页输入标题和描述，点提交 | 员工 |
| 4 | 右上角退出，重新登录 `zhangsan` / `zhangsan123` | 运维 |
| 5 | 进入 IT 运维服务台 → 请求 → 看到刚才提交的待处理工单 | 运维 |
| 6 | 点 **查看** → 点 **处理此工单**（这步触发 AI 分析） | 运维 |
| 7 | 👉 **看钉钉运维群**——应该收到一条 P1 紧急通知 | — |
| 8 | 点 **标记已解决**，填三个必填字段，确认 | 运维 |
| 9 | 👉 **看钉钉员工群**——应该收到"工单已解决"通知 | — |

### 6.4 你在钉钉会看到什么

**运维群收到（AI 处理后）：**

```
🔴 P1 紧急工单 TCK-20260717-XXXXXXXX 需【支付系统运维组】立即处理

工单编号: TCK-20260717-XXXXXXXX
优先级: P1
影响服务: payment-service
处理摘要: payment-db 连接池使用率达 96%，历史相似工单 INC-2025-021 根因为连接池耗尽。
建议措施:
- 检查 payment-service 最近 30 分钟部署记录
- 临时扩容 payment-db 连接池至 200
- 观察扩容后超时率和订单量恢复情况
```

**员工群收到（工单解决后）：**

```
工单已解决

工单编号: TCK-20260717-XXXXXXXX
优先级: P3
处理摘要: 您的工单 TCK-20260717-XXXXXXXX 已由运维人员处理完成。
处理结果：已处理完成
建议措施:
- 请查看 IntelliTicket 详情
```

---

## 附录：通知行为速查

| 场景 | 谁收到 | 什么时候 |
|---|---|---|
| 运维点了「AI 诊断」 | 运维群 | AI pipeline 完成瞬间 |
| P1 工单 | 运维群 | 标题带 🔴 + @all |
| P2/P3 工单 | 运维群 | 正常推送 |
| P4 工单 | **不通知** | 低优先级不打扰 |
| 运维点了「标记已解决」 | 员工群 | 提交工单的员工能看到 |
| 钉钉没配置 | 无人收到 | 静默跳过，不影响系统 |

---

## 故障排查

| 现象 | 检查 |
|---|---|
| 钉钉完全没消息 | `.env` 里 `DINGTALK_ENABLED` 是不是 `true`、URL 是否正确 |
| 报 `errcode: 310000` | 安全设置的关键词没匹配上——检查是否填了"工单" |
| 运维群收不到但员工群能收到 | 运维群的 `DINGTALK_OPERATOR_WEBHOOK_URL` 可能有问题 |
| 点了「AI 诊断」后没收到 | 确认当前 `.env` 被正确加载（重启 uvicorn） |
| IPv4/IPv6 问题 | 钉钉 webhook 走公网，确保开发机有外网访问 |
