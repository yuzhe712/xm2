from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.tickets import DataMode, DeskId
from intelliticket_backend.services.knowledge.connectors.base import KnowledgeDocument


class FeishuKnowledgeConnector:
    """飞书 Drive 文件夹知识文档 Connector。"""

    source_name = "Feishu Drive Folder"

    def __init__(
        self,
        *,
        app_id: SecretStr,
        app_secret: SecretStr,
        base_url: str,
        wiki_space_id: str | None,
        drive_folder_url: str | None = None,
        drive_folder_token: str | None = None,
        timeout_seconds: float,
        max_results: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self.wiki_space_id = wiki_space_id
        self.drive_folder_url = drive_folder_url
        self.drive_folder_token = drive_folder_token or self._folder_token_from_url(
            drive_folder_url
        )
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self.client = client or httpx.Client(timeout=timeout_seconds)
        self._token: str | None = None
        self._token_expires_at = 0.0

    def search_sops(
        self,
        *,
        query: str,
        service_name: str | None,
        limit: int,
    ) -> list[KnowledgeDocument]:
        search_key = " ".join(part for part in [service_name, query] if part).strip()
        return self._search(search_key=search_key, desk_id=None, limit=limit, allow_browse=False)

    def search_support_articles(
        self,
        *,
        query: str,
        desk_id: DeskId,
        limit: int,
    ) -> list[KnowledgeDocument]:
        return self._search(
            search_key=query.strip(),
            desk_id=desk_id,
            limit=limit,
            allow_browse=not query.strip(),
        )

    def _search(
        self,
        *,
        search_key: str,
        desk_id: DeskId | None,
        limit: int,
        allow_browse: bool,
    ) -> list[KnowledgeDocument]:
        if not self.drive_folder_token:
            raise AppError(
                "FEISHU_KB_UNAVAILABLE",
                "飞书 Drive 文件夹未配置",
                502,
                {"source": self.source_name},
            )
        if not search_key.strip() and not allow_browse:
            return []

        token = self._tenant_access_token()
        records = self._list_drive_files(
            token=token,
            folder_token=self.drive_folder_token,
            limit=max(limit, self.max_results),
        )
        documents = []
        for record in records:
            document = self._document_from_drive_record(record, token=token, desk_id=desk_id)
            if document is not None:
                documents.append(document)

        matches = self._rank_documents(documents, search_key)
        if not matches and not allow_browse:
            return []
        return (matches if search_key.strip() else documents)[: min(limit, self.max_results)]

    def _tenant_access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at:
            return self._token
        try:
            response = self.client.post(
                f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self.app_id.get_secret_value(),
                    "app_secret": self.app_secret.get_secret_value(),
                },
            )
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise self._unavailable("飞书 tenant_access_token 获取失败", exc) from exc
        self._ensure_feishu_ok(payload, "飞书 tenant_access_token 获取失败")
        token = payload.get("tenant_access_token")
        if not isinstance(token, str) or not token.strip():
            raise AppError(
                "FEISHU_KB_UNAVAILABLE",
                "飞书 tenant_access_token 响应缺少 token",
                502,
                {"source": self.source_name},
            )
        expire = payload.get("expire")
        ttl = int(expire) if isinstance(expire, int | float) else 3600
        self._token = token
        self._token_expires_at = now + max(ttl - 60, 60)
        return token

    def _list_drive_files(
        self,
        *,
        token: str,
        folder_token: str,
        limit: int,
        depth: int = 0,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(records) < limit:
            params: dict[str, Any] = {
                "folder_token": folder_token,
                "page_size": min(50, max(limit - len(records), 1)),
            }
            if page_token:
                params["page_token"] = page_token
            try:
                response = self.client.get(
                    f"{self.base_url}/open-apis/drive/v1/files",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise self._unavailable("飞书 Drive 文件夹列表获取失败", exc) from exc
            self._ensure_feishu_ok(payload, "飞书 Drive 文件夹列表获取失败")
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                return records
            items = data.get("files") or data.get("items")
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if self._is_folder_record(item) and depth < 2:
                        child_token = self._first_text(item, "token", "file_token", "id")
                        if child_token:
                            records.extend(
                                self._list_drive_files(
                                    token=token,
                                    folder_token=child_token,
                                    limit=limit - len(records),
                                    depth=depth + 1,
                                )
                            )
                    else:
                        records.append(item)
                    if len(records) >= limit:
                        break
            has_more = bool(data.get("has_more"))
            next_page_token = data.get("page_token") or data.get("next_page_token")
            if not has_more or not isinstance(next_page_token, str) or not next_page_token:
                break
            page_token = next_page_token
        return records[:limit]

    def _is_folder_record(self, record: dict[str, Any]) -> bool:
        file_type = (self._first_text(record, "type", "file_type") or "").lower()
        return file_type == "folder"

    def _document_from_drive_record(
        self,
        record: dict[str, Any],
        *,
        token: str,
        desk_id: DeskId | None,
    ) -> KnowledgeDocument | None:
        file_type = (self._first_text(record, "type", "file_type") or "").lower()
        if file_type in {"folder", "shortcut", "image", "pdf", "sheet", "bitable"}:
            return None

        source_id = self._first_text(record, "token", "file_token", "doc_token", "id")
        title = self._first_text(record, "name", "title") or "飞书 Drive 文档"
        url = self._first_text(record, "url", "link", "docs_url") or self._drive_file_url(source_id)
        updated_at = self._first_text(record, "updated_at", "update_time", "modified_time")
        if not source_id:
            source_id = self._safe_slug(title)

        content = self._read_document_content(token=token, record=record, source_id=source_id)
        summary = self._summary_from_content(content) if content else title
        quality = "external_retrieved" if content else "external_metadata_only"
        article_id = f"feishu-{self._safe_slug(source_id)}"
        return KnowledgeDocument(
            evidence_id=f"ev_feishu_{self._safe_slug(source_id)}",
            source_type="external_knowledge",
            source_id=source_id,
            source_name=self.source_name,
            title=title,
            summary=summary,
            actions=self._actions_from_summary(summary),
            service=self._first_text(record, "service"),
            desk_scope=desk_id,
            retrieved_at=self._now(),
            updated_at=updated_at,
            quality=quality,
            data_mode=DataMode.REAL,
            trace_uri=url,
            article_id=article_id,
            sop_id=article_id,
        )

    def _read_document_content(
        self,
        *,
        token: str,
        record: dict[str, Any],
        source_id: str,
    ) -> str | None:
        file_type = (self._first_text(record, "type", "file_type") or "").lower()
        candidates: list[str] = []
        if file_type == "docx":
            candidates.append(f"/open-apis/docx/v1/documents/{source_id}/raw_content")
        elif file_type == "doc":
            candidates.append(f"/open-apis/doc/v2/{source_id}/raw_content")
        else:
            return None

        for path in candidates:
            try:
                response = self.client.get(
                    f"{self.base_url}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise self._unavailable("飞书文档正文读取失败", exc) from exc
            self._ensure_feishu_ok(payload, "飞书文档正文读取失败")
            content = self._content_from_payload(payload)
            if content:
                return content
        return None

    def _content_from_payload(self, payload: dict[str, Any]) -> str | None:
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict):
            for key in ("content", "raw_content", "text"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return self._strip_html(value)
        for key in ("content", "raw_content", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return self._strip_html(value)
        return None

    def _rank_documents(
        self,
        documents: list[KnowledgeDocument],
        search_key: str,
    ) -> list[KnowledgeDocument]:
        terms = self._terms(search_key)
        if not terms:
            return documents
        scored = []
        for document in documents:
            haystack = f"{document.title}\n{document.summary}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score > 0:
                scored.append((score, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [document for _, document in scored]

    def _terms(self, value: str) -> list[str]:
        compact = value.strip().lower()
        if not compact:
            return []
        terms = [term for term in re.split(r"\s+", compact) if term]
        terms.extend(
            token
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_+-]+", compact)
            if len(token) >= 4
        )
        keyword_expansions = {
            "超时": ["超时", "timeout"],
            "timeout": ["超时", "timeout"],
            "延迟": ["延迟", "latency"],
            "丢包": ["丢包"],
            "端口": ["端口", "connection refused"],
            "网络": ["网络"],
            "dns": ["dns", "解析失败", "unknownhost"],
            "解析失败": ["dns", "解析失败", "unknownhost"],
            "kafka": ["kafka", "消费积压"],
            "积压": ["积压", "lag"],
            "rabbitmq": ["rabbitmq", "消息队列"],
            "配置": ["配置", "configmap"],
            "变更": ["变更"],
            "权限": ["权限", "角色"],
            "账号": ["账号", "权限"],
            "vpn": ["vpn"],
        }
        for keyword, expanded in keyword_expansions.items():
            if keyword in compact:
                terms.extend(expanded)
        terms.append(compact)
        return list(dict.fromkeys(terms))

    def _summary_from_content(self, content: str) -> str:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        summary = "\n".join(lines[:6]) if lines else content.strip()
        return summary[:1000]

    def _ensure_feishu_ok(self, payload: dict[str, Any], message: str) -> None:
        code = payload.get("code")
        if code not in {0, "0", None}:
            raise AppError(
                "FEISHU_KB_UNAVAILABLE",
                message,
                502,
                {
                    "source": self.source_name,
                    "feishu_code": code,
                    "feishu_msg": payload.get("msg") or payload.get("message"),
                },
            )

    def _unavailable(self, message: str, exc: Exception) -> AppError:
        return AppError(
            "FEISHU_KB_UNAVAILABLE",
            message,
            502,
            {"source": self.source_name, "error_type": type(exc).__name__},
        )

    def _folder_token_from_url(self, value: str | None) -> str | None:
        if not value:
            return None
        parsed = urlparse(value.strip())
        if not parsed.scheme:
            return value.strip()
        match = re.search(r"/drive/folder/([^/?#]+)", parsed.path)
        if match:
            return match.group(1)
        match = re.search(r"/folder/([^/?#]+)", parsed.path)
        if match:
            return match.group(1)
        return None

    def _drive_file_url(self, source_id: str | None) -> str | None:
        if not source_id:
            return None
        host = urlparse(self.drive_folder_url or "").netloc or "my.feishu.cn"
        return f"https://{host}/drive/file/{source_id}"

    def _first_text(self, record: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int | float):
                return str(value)
            if isinstance(value, dict):
                for nested in ("text", "value", "url"):
                    nested_value = value.get(nested)
                    if isinstance(nested_value, str) and nested_value.strip():
                        return nested_value.strip()
        return None

    def _actions_from_summary(self, summary: str) -> list[str]:
        lines = [line.strip(" -•\t") for line in self._strip_html(summary).splitlines()]
        actions = [line for line in lines if line]
        return actions[:6] or [self._strip_html(summary)[:120]]

    def _strip_html(self, text: str) -> str:
        return re.sub(r"<[^>]+>", "", text).strip()

    def _safe_slug(self, value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
        return (slug or "document")[:80]

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
