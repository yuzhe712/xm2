import { useCallback, useEffect, useState } from 'react'

import { getDeskCatalog, getDeskKnowledge, TicketApiError } from '../api/tickets'
import type {
  ApiErrorPayload,
  CatalogItem,
  DeskId,
  KnowledgeArticle,
} from '../types/tickets'

interface UseDeskResourcesOptions {
  apiBaseUrl?: string
  deskId: DeskId
}

interface UseDeskResourcesResult {
  catalogItems: CatalogItem[]
  knowledgeItems: KnowledgeArticle[]
  loading: boolean
  error: TicketApiError | ApiErrorPayload['error'] | Error | null
  refresh: () => Promise<void>
}

export function useDeskResources(options: UseDeskResourcesOptions): UseDeskResourcesResult {
  const { apiBaseUrl, deskId } = options
  const [catalogItems, setCatalogItems] = useState<CatalogItem[]>([])
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeArticle[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<TicketApiError | ApiErrorPayload['error'] | Error | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [catalog, knowledge] = await Promise.all([
        getDeskCatalog(deskId, fetch, apiBaseUrl),
        getDeskKnowledge(deskId, fetch, apiBaseUrl),
      ])
      setCatalogItems(catalog.items)
      setKnowledgeItems(knowledge.items)
    } catch (err) {
      setCatalogItems([])
      setKnowledgeItems([])
      setError(err instanceof Error ? err : new Error('服务台资源加载失败'))
    } finally {
      setLoading(false)
    }
  }, [apiBaseUrl, deskId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { catalogItems, knowledgeItems, loading, error, refresh }
}
