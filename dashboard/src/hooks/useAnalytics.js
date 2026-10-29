import { portfolioClient } from '../config/api'
import { useApi } from './useApi'

export const useAccuracy = () => useApi(() => portfolioClient.get('/analytics/accuracy'))
export const useRecommendations = (limit = 100) =>
  useApi(() => portfolioClient.get('/recommendations/history', { params: { limit } }), [limit])
