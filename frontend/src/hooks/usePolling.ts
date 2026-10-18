import { useEffect, useRef, useState } from "react"

/** Serial requests, cancellation on leave/hide, and immediate refresh on return. */
export function usePolling(task: (signal: AbortSignal) => Promise<void>, delay: number, enabled = true) {
  const taskRef = useRef(task)
  useEffect(() => { taskRef.current = task }, [task])
  useEffect(() => {
    if (!enabled) return
    let disposed = false, running = false, refreshPending = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let controller: AbortController | undefined
    const clear = () => { clearTimeout(timer); timer = undefined }
    const tick = async () => {
      clear()
      if (disposed || document.hidden || running) return
      running = true; refreshPending = false
      controller = new AbortController()
      try { await taskRef.current(controller.signal) }
      catch (error) { if (!controller.signal.aborted) console.error("Polling failed", error) }
      finally {
        running = false
        if (!disposed && !document.hidden) timer = setTimeout(tick, refreshPending ? 0 : delay)
      }
    }
    const visibility = () => {
      clear()
      if (document.hidden) { refreshPending = false; controller?.abort() }
      else { refreshPending = true; void tick() }
    }
    document.addEventListener("visibilitychange", visibility)
    void tick()
    return () => { disposed = true; clear(); controller?.abort(); document.removeEventListener("visibilitychange", visibility) }
  }, [delay, enabled])
}

export function usePageVisible() {
  const [visible, setVisible] = useState(() => !document.hidden)
  useEffect(() => {
    const update = () => setVisible(!document.hidden)
    document.addEventListener("visibilitychange", update)
    return () => document.removeEventListener("visibilitychange", update)
  }, [])
  return visible
}
