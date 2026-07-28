# API 示例

以下示例使用 PowerShell，账号和密码只从当前进程环境读取。示例不包含部署密码、固定 Token 或真实工单数据。

```powershell
$base = "http://127.0.0.1:8080"
$loginBody = @{
  user_id = $env:INTELLITICKET_USERNAME
  password = $env:INTELLITICKET_PASSWORD
} | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/login" `
  -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($login.token)" }
```

## 员工创建和查询工单

```powershell
$body = @{
  title = "支付接口超时"
  text = "支付成功率连续十分钟低于内部告警阈值，请协助排查。"
  desk_id = "ops"
  priority = "P3"
} | ConvertTo-Json

$ticket = Invoke-RestMethod -Method Post -Uri "$base/api/v1/tickets/submit" `
  -Headers $headers -ContentType "application/json" -Body $body

Invoke-RestMethod -Headers $headers `
  -Uri "$base/api/v1/ai-runs/$($ticket.ai_run_id)"
Invoke-RestMethod -Headers $headers `
  -Uri "$base/api/v1/tickets/$($ticket.ticket_id)/workflow"
Invoke-RestMethod -Headers $headers `
  -Uri "$base/api/v1/tickets/mine?limit=20&offset=0"
```

`data_mode` 由后端部署配置决定。客户端即使提交同名字段，也不能把 mock/real 模式改为另一个值。

## 运维认领、回复和解决

使用 operator 账号重新登录并生成 `$operatorHeaders`：

```powershell
$operatorLogin = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/login" `
  -ContentType "application/json" `
  -Body (@{
    user_id = $env:INTELLITICKET_OPERATOR_USERNAME
    password = $env:INTELLITICKET_OPERATOR_PASSWORD
  } | ConvertTo-Json)
$operatorHeaders = @{ Authorization = "Bearer $($operatorLogin.token)" }

$current = Invoke-RestMethod -Headers $operatorHeaders `
  -Uri "$base/api/v1/tickets/$($ticket.ticket_id)/workflow"

$claimed = Invoke-RestMethod -Method Post -Headers $operatorHeaders `
  -Uri "$base/api/v1/tickets/$($ticket.ticket_id)/claim" `
  -ContentType "application/json" `
  -Body (@{ version = $current.version } | ConvertTo-Json)

Invoke-RestMethod -Method Post -Headers $operatorHeaders `
  -Uri "$base/api/v1/tickets/$($ticket.ticket_id)/comments" `
  -ContentType "application/json" `
  -Body (@{
    version = $claimed.version
    visibility = "public"
    body = "已开始排查，请稍候。"
  } | ConvertTo-Json)

$afterReply = Invoke-RestMethod -Headers $operatorHeaders `
  -Uri "$base/api/v1/tickets/$($ticket.ticket_id)/workflow"

$resolved = Invoke-RestMethod -Method Post -Headers $operatorHeaders `
  -Uri "$base/api/v1/tickets/$($ticket.ticket_id)/resolve" `
  -ContentType "application/json" `
  -Body (@{
    version = $afterReply.version
    resolution_summary = "服务恢复，支付探针通过。"
    root_cause = "上游连接池耗尽。"
    fix_action = "重建连接池并修正容量上限。"
    verification = "连续十五分钟成功率高于 99.9%。"
  } | ConvertTo-Json)
```

只有当前处理人或 admin 能解决工单。内部备注将 `visibility` 改为 `internal`，员工查询评论和时间线时不会收到该内容。

## 员工确认或重新打开

```powershell
# 确认关闭
Invoke-RestMethod -Method Post -Headers $headers `
  -Uri "$base/api/v1/tickets/$($ticket.ticket_id)/confirm" `
  -ContentType "application/json" `
  -Body (@{ version = $resolved.version } | ConvertTo-Json)

# 若问题复现，可在 resolved/closed 状态带原因重新打开
Invoke-RestMethod -Method Post -Headers $headers `
  -Uri "$base/api/v1/tickets/$($ticket.ticket_id)/reopen" `
  -ContentType "application/json" `
  -Body (@{ version = $resolved.version; reason = "问题再次出现" } | ConvertTo-Json)
```

## 版本冲突

所有状态写操作携带 `version`。两个处理人同时用 version 1 认领时，只有一个成功；另一个得到 409：

```json
{
  "error": {
    "code": "TICKET_VERSION_CONFLICT",
    "message": "工单已被其他用户更新",
    "details": {
      "expected_version": 1,
      "current_version": 2
    }
  }
}
```

客户端收到 409 后应重新获取详情，不要盲目重放写请求。

## 附件

PowerShell 7 可直接使用 `-Form`；其他环境可使用 `curl.exe`：

```powershell
curl.exe -X POST `
  -H "Authorization: Bearer $($login.token)" `
  -F "file=@$env:ATTACHMENT_PATH" `
  "$base/api/v1/tickets/$($ticket.ticket_id)/attachments"

Invoke-RestMethod -Headers $headers `
  -Uri "$base/api/v1/tickets/$($ticket.ticket_id)/attachments"
```

支持的文件必须同时通过扩展名、MIME、文件签名、非空和 25 MiB 上限校验。下载权限继承工单可见性。

## 管理员创建用户

```powershell
$newUser = @{
  username = $env:NEW_USERNAME
  display_name = $env:NEW_DISPLAY_NAME
  role = "operator"
  password = $env:NEW_USER_PASSWORD
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Headers $adminHeaders `
  -Uri "$base/api/v1/users" -ContentType "application/json" -Body $newUser
```

停用用户后，该用户已签发的 Token 会在下一次请求时失效。

## 健康和指标

```powershell
Invoke-RestMethod "$base/health"
Invoke-RestMethod "$base/ready"
Invoke-WebRequest "$base/metrics"
```

`/health` 不代表依赖就绪；流量接入和部署判断应使用 `/ready`。
