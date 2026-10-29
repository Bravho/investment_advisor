import { portfolioClient } from '../config/api'
import { useApi } from './useApi'

export const useOpportunities = (refreshMs = 60000) =>
  useApi(() => portfolioClient.get('/opportunities'), [], refreshMs)
