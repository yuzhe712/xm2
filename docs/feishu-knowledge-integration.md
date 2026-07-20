# 飞书 Drive 文件夹接入说明

IntelliTicket 支持可选接入飞书 Drive 文件夹作为外部知识来源。默认仍使用本地 `mock_data` 知识库；只有配置完整的飞书应用凭证和 Drive 文件夹链接后，后端才会从飞书读取 SOP/知识文章。

## 能力边界

飞书 Drive 文档只作为知识参考：

- 可以提供 SOP、处理步骤、历史经验；
- 不能代表当前故障的实时监控事实；
- 不能替代 Prometheus/Grafana/Jira 等系统的当前观测；
- 读取失败时不会伪造 `data_mode=real` 的知识证据；
- 未支持的文件类型会跳过或仅作为元数据线索，不会声称已读取正文。

## 环境变量

```env
KNOWLEDGE_PROVIDER=feishu
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_DRIVE_FOLDER_URL=https://my.feishu.cn/drive/folder/xxx
FEISHU_BASE_URL=https://open.feishu.cn
FEISHU_TIMEOUT_SECONDS=5
FEISHU_MAX_RESULTS=5
```

也可以直接配置文件夹 token：

```env
FEISHU_DRIVE_FOLDER_TOKEN=xxx
```

如果 `KNOWLEDGE_PROVIDER=feishu` 但 `FEISHU_APP_ID`、`FEISHU_APP_SECRET` 或 Drive 文件夹配置缺失，系统会返回 `FEISHU_KB_NOT_CONFIGURED`，不会继续使用本地 mock 知识库。配置完整但飞书 API 调用失败时，系统会返回结构化错误或部分上下文，不会静默伪装成 mock 成功。

`FEISHU_WIKI_SPACE_ID` 是旧 Wiki Space 场景配置；当前 Drive 文件夹接入不需要。

## 飞书侧准备

1. 在飞书开放平台创建企业自建应用；
2. 获取 `App ID` 和 `App Secret`；
3. 给应用授权 Drive / 云文档 / 文档读取所需权限；
4. 发布并安装应用；
5. 将目标 Drive 文件夹或其中的文档授权给该应用，或确保应用所在组织有可查看权限；
6. 复制目标文件夹链接，配置为 `FEISHU_DRIVE_FOLDER_URL`。

不同组织的飞书权限策略可能不同。如果接口返回 `forbidden` 或空结果，应先检查应用权限、应用是否重新发布安装，以及文件夹/文档是否对应用可见。

## IntelliTicket 中的证据展示

飞书返回的文档会转换为统一 Evidence：

```json
{
  "source_type": "external_knowledge",
  "source_name": "Feishu Drive Folder",
  "data_mode": "real",
  "trace_uri": "https://...",
  "quality": "external_retrieved",
  "quality_reason": "来自飞书 Drive 文件夹读取的真实知识文档，作为知识参考，不代表当前故障事实。"
}
```

前端证据面板会展示来源、数据模式、链接和质量说明。

## 验证建议

未配置飞书时：

```bash
PYTHONPATH=src pytest tests/test_knowledge_service.py tests/test_context_retrieval_agent.py tests/test_support_agents.py
```

配置真实飞书凭证和 Drive 文件夹链接后：

1. 启动后端；
2. 提交一条包含文件夹中文档关键词的工单；
3. 查看 EvidencePanel；
4. 确认来源为 `Feishu Drive Folder`；
5. 确认 `data_mode=real`；
6. 确认报告仍区分“知识参考”和“当前故障事实”。
