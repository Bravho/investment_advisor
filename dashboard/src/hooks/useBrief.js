import { portfolioClient } from '../config/api'
import { useApi } from './useApi'

export const useBrief = (refreshMs = 60000) =>
  useApi(() => portfolioClient.get('/brief/today'), [], refreshMs)
