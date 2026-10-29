import { portfolioClient } from '../config/api'
import { useApi } from './useApi'

// Phase 3 (2026-10-29): watch lists, market factors, risk engine
export const useWatchlist = (refreshMs = 120000) =>
  useApi(() => portfolioClient.get('/watchlist', { params: { include_dropped: false } }), [], refreshMs)
export const useFactors = (refreshMs = 120000) =>
  useApi(() => portfolioClient.get('/factors'), [], refreshMs)
export const useRiskReport = (refreshMs = 300000) =>
  useApi(() => portfolioClient.get('/risk/report'), [], refreshMs)
