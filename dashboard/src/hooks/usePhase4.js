import { portfolioClient } from '../config/api'
import { useApi } from './useApi'

// Phase 4 (2026-10-30): signals, trade plans, backtest, paper ledger, journal
export const useSignals = (refreshMs = 300000) => useApi(() => portfolioClient.get('/signals'), [], refreshMs)
export const useTradePlans = (refreshMs = 300000) => useApi(() => portfolioClient.get('/trade-plans', { params: { status: 'proposed' } }), [], refreshMs)
export const useBacktest = (refreshMs = 600000) => useApi(() => portfolioClient.get('/backtest/latest'), [], refreshMs)
export const useSignalPerformance = (refreshMs = 600000) => useApi(() => portfolioClient.get('/signals/performance'), [], refreshMs)
export const usePaperTrades = (refreshMs = 300000) => useApi(() => portfolioClient.get('/paper-trades'), [], refreshMs)
export const useJournal = (refreshMs = 600000) => useApi(() => portfolioClient.get('/journal'), [], refreshMs)
