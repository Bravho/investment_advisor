import { portfolioClient } from '../config/api'
import { useApi } from './useApi'

export const useThaiWatchlist = (refreshMs = 300000) =>
  useApi(() => portfolioClient.get('/opportunities/thai-watchlist'), [], refreshMs)
