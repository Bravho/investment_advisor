import { portfolioClient } from '../config/api'
import { useApi } from './useApi'

// Phase 4 (2026-10-30): signals, trade plans, backtest, paper ledger, journal
export const useSignals = (refreshMs = 300000) => useApi(() => portfolioClient.get('/signals'), [], refreshMs)
export const useTradePlans = (refreshMs = 300000) => useApi(() => portfolioClient.get('/trade-plans', { params: { status: 'proposed' } }), [], refreshMs)
export const useBacktest = (refreshMs = 600000) => useApi(() => portfolioClient.get('/backtest/latest'), [], refreshMs)
export const useSignalPerformance = (refreshMs = 600000) => useApi(() => portfolioClient.get('/signals/performance'), [], refreshMs)
export const usePaperTrades = (refreshMs = 300000) => useApi(() => portfolioClient.get('/paper-trades'), [], refreshMs)
export const useJournal = (refreshMs = 600000) => useApi(() => portfolioClient.get('/journal'), [], refreshMs)
export const usePredictions = (refreshMs = 600000) => useApi(() => portfolioClient.get('/predictions'), [], refreshMs)
export const usePredictionScoreboard = (refreshMs = 600000) => useApi(() => portfolioClient.get('/predictions/scoreboard'), [], refreshMs)
// Pro #4/#6 (2026-10-30)
export const useConstruction = (refreshMs = 900000) => useApi(() => portfolioClient.get('/portfolio/construction'), [], refreshMs)
export const useAttribution = (refreshMs = 900000) => useApi(() => portfolioClient.get('/performance/attribution'), [], refreshMs)
// 2026-10-30: momentum_base_swing setup (Tho's lesson, swing adaptation)
export const useMomentumBase = (refreshMs = 600000) => useApi(() => portfolioClient.get('/setups/momentum-base'), [], refreshMs)
// 2026-11-01 (Tho): approved plans + approval history; override approvals carry override_badge_th / badge_th
export const useApprovedPlans = (refreshMs = 300000) => useApi(() => portfolioClient.get('/trade-plans', { params: { status: 'approved' } }), [], refreshMs)
export const usePlanAudit = (refreshMs = 300000) => useApi(() => portfolioClient.get('/trade-plans/audit', { params: { limit: 20 } }), [], refreshMs)
