import { portfolioClient } from '../config/api'
import { useApi } from './useApi'

// 2026-10-31: de-duplicated, Thai-summarised news feed (portfolio engine /news/feed)
export const useNewsFeed = (includeCrypto = false, refreshMs = 300000) =>
  useApi(() => portfolioClient.get('/news/feed', { params: { hours: 72, limit: 80, include_crypto: includeCrypto } }), [includeCrypto], refreshMs)
