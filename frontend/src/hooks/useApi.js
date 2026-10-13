import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Small data-fetching hook with loading / error / refetch.
 * All values come from the backend API — no client-side derivation.
 */
export function useApi(fetcher, deps = [], { immediate = true } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const alive = useRef(true);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetcherRef.current();
      if (alive.current) setData(result);
    } catch (err) {
      if (alive.current && err.name !== 'AbortError') setError(err.message || 'Request failed');
    } finally {
      if (alive.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    alive.current = true;
    if (immediate) run();
    return () => {
      alive.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error, refetch: run };
}

export default useApi;
