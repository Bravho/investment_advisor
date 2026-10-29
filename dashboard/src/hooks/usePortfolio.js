import { portfolioClient } from '../config/api'
import { useApi } from './useApi'

export const usePortfolio = (refreshMs = 60000) =>
  useApi(() => portfolioClient.get('/portfolio/summary'), [], refreshMs)

export const usePerformance = (days = 30, refreshMs = 0) =>
  useApi(() => portfolioClient.get('/portfolio/performance', { params: { days } }), [days], refreshMs)

export const useRisk = (refreshMs = 60000) =>
  useApi(() => portfolioClient.get('/portfolio/risk'), [], refreshMs)
