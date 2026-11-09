import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

type StoredDraft<T> = {
  version: 1
  savedAt: string
  data: T
}

export type RecoverableDraft<T> = StoredDraft<T> & { key: string }

type DraftStatus = 'saving' | 'saved' | 'unavailable' | null

export function useDraftProtection<T>(
  key: string | null,
  current: T,
  baseline: T,
  active: boolean,
  trackChanges = true,
) {
  const [recovery, setRecovery] = useState<RecoverableDraft<T> | null>(null)
  const [inspectedKey, setInspectedKey] = useState<string | null>(null)
  const [status, setStatus] = useState<DraftStatus>(null)
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const inspectedKeys = useRef(new Set<string>())
  const currentJson = JSON.stringify(current)
  const baselineJson = JSON.stringify(baseline)
  const hasUnsavedChanges = active && trackChanges && currentJson !== baselineJson
  const recoverableDraft = recovery?.key === key ? recovery : null
  const latest = useRef({ key, current, hasUnsavedChanges, recoverableDraft })

  useLayoutEffect(() => {
    latest.current = { key, current, hasUnsavedChanges, recoverableDraft }
  }, [current, hasUnsavedChanges, key, recoverableDraft])

  useEffect(() => {
    if (!active || !key || inspectedKeys.current.has(key)) return
    inspectedKeys.current.add(key)
    try {
      const raw = window.localStorage.getItem(key)
      if (raw) {
        const value = JSON.parse(raw) as Partial<StoredDraft<T>>
        if (value.version === 1 && typeof value.savedAt === 'string' && value.data !== undefined) {
          if (JSON.stringify(value.data) !== baselineJson) {
            setRecovery({ key, version: 1, savedAt: value.savedAt, data: value.data })
          } else {
            window.localStorage.removeItem(key)
          }
        } else {
          window.localStorage.removeItem(key)
        }
      }
      setInspectedKey(key)
    } catch {
      setStatus('unavailable')
      setInspectedKey(key)
    }
  }, [active, baselineJson, key])

  const persistNow = useCallback(() => {
    const {
      key: currentKey,
      current: latestCurrent,
      hasUnsavedChanges: hasChanges,
      recoverableDraft: pendingRecovery,
    } = latest.current
    if (!currentKey || !hasChanges || pendingRecovery) return false
    const timestamp = new Date().toISOString()
    try {
      window.localStorage.setItem(currentKey, JSON.stringify({ version: 1, savedAt: timestamp, data: latestCurrent }))
      setSavedAt(timestamp)
      setStatus('saved')
      return true
    } catch {
      setStatus('unavailable')
      return false
    }
  }, [])

  useEffect(() => {
    if (!key || !active || inspectedKey !== key) return
    if (!hasUnsavedChanges) {
      if (!recoverableDraft) {
        try {
          window.localStorage.removeItem(key)
        } catch {
          // Storage may be unavailable; keep the editor usable.
        }
        setStatus(null)
        setSavedAt(null)
      }
      return
    }
    if (recoverableDraft) return
    setStatus('saving')
    const timer = window.setTimeout(persistNow, 700)
    return () => window.clearTimeout(timer)
  }, [active, hasUnsavedChanges, inspectedKey, key, persistNow, recoverableDraft])

  useEffect(() => {
    if (!hasUnsavedChanges) return
    const beforeUnload = (event: BeforeUnloadEvent) => {
      persistNow()
      event.preventDefault()
      event.returnValue = ''
    }
    const guardLinks = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return
      }
      const target = event.target instanceof Element ? event.target.closest('a[href]') : null
      if (!(target instanceof HTMLAnchorElement) || target.target === '_blank' || target.hasAttribute('download'))
        return
      const destination = new URL(target.href, window.location.href)
      if (
        destination.origin === window.location.origin &&
        destination.pathname === window.location.pathname &&
        destination.search === window.location.search &&
        destination.hash === window.location.hash
      ) {
        return
      }
      const saved = persistNow()
      const message = saved
        ? '当前修改已暂存在此设备，尚未保存到作品。确定离开吗？'
        : '当前修改尚未保存到作品，且无法暂存本地草稿。确定离开吗？'
      if (!window.confirm(message)) {
        event.preventDefault()
        event.stopPropagation()
        event.stopImmediatePropagation()
      }
    }
    let returningAfterBlockedBack = false
    const guardHistory = () => {
      if (returningAfterBlockedBack) {
        returningAfterBlockedBack = false
        return
      }
      const saved = persistNow()
      const message = saved
        ? '当前修改已暂存在此设备，尚未保存到作品。确定离开吗？'
        : '当前修改尚未保存到作品，且无法暂存本地草稿。确定离开吗？'
      if (!window.confirm(message)) {
        returningAfterBlockedBack = true
        window.history.forward()
      }
    }
    window.addEventListener('beforeunload', beforeUnload)
    window.addEventListener('popstate', guardHistory)
    document.addEventListener('click', guardLinks, true)
    return () => {
      window.removeEventListener('beforeunload', beforeUnload)
      window.removeEventListener('popstate', guardHistory)
      document.removeEventListener('click', guardLinks, true)
    }
  }, [hasUnsavedChanges, persistNow])

  const dismissRecovery = useCallback(() => setRecovery(null), [])
  const discardDraft = useCallback(() => {
    if (key) {
      try {
        window.localStorage.removeItem(key)
      } catch {
        // Storage may be unavailable; clear the in-memory recovery state anyway.
      }
    }
    setRecovery(null)
    setStatus(null)
    setSavedAt(null)
  }, [key])

  return {
    hasUnsavedChanges,
    recovery: recoverableDraft,
    dismissRecovery,
    discardDraft,
    persistNow,
    status: hasUnsavedChanges ? status : null,
    savedAt,
  }
}
