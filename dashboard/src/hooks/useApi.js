import { useCallback, useEffect, useState } from 'react'

export function useApi(request, dependencies = [], refreshMs = 0) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refetch = useCallback(async () => {
    setError(null)
    try {
      const result = await request()
      setData(result?.data ?? result)
    } catch (requestError) {
      setError(requestError)
    } finally {
      setLoading(false)
    }
  }, dependencies)

  useEffect(() => {
    setLoading(true)
    refetch()
    if (!refreshMs) return undefined
    const interval = window.setInterval(refetch, refreshMs)
    return () => window.clearInterval(interval)
  }, [refetch, refreshMs])

  return { data, loading, error, refetch, setData }
}
