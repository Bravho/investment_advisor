import { portfolioClient } from '../config/api'
import { useApi } from './useApi'

export const useAdvisoryCandidates = (refreshMs = 120000) =>
  useApi(() => portfolioClient.get('/opportunities/advisory'), [], refreshMs)
