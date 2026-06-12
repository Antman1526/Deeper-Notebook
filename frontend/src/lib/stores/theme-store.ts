import { useEffect, useState } from 'react'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'light' | 'dark' | 'system'

interface ThemeState {
  theme: Theme
  setTheme: (theme: Theme) => void
  getSystemTheme: () => 'light' | 'dark'
  getEffectiveTheme: () => 'light' | 'dark'
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'system',
      
      setTheme: (theme: Theme) => {
        set({ theme })
        
        // Apply theme to document immediately
        if (typeof window !== 'undefined') {
          const root = window.document.documentElement
          const effectiveTheme = theme === 'system' ? get().getSystemTheme() : theme
          
          root.classList.remove('light', 'dark')
          root.classList.add(effectiveTheme)
          root.setAttribute('data-theme', effectiveTheme)
        }
      },
      
      getSystemTheme: () => {
        if (typeof window !== 'undefined') {
          return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
        }
        return 'light'
      },
      
      getEffectiveTheme: () => {
        const { theme } = get()
        return theme === 'system' ? get().getSystemTheme() : theme
      }
    }),
    {
      name: 'theme-storage',
      partialize: (state) => ({ theme: state.theme })
    }
  )
)

// Hook for components to use theme
//
// v0.7.59 — compute effectiveTheme client-side only.
//
// The previous version called `getEffectiveTheme()` during render. On
// the server `typeof window === 'undefined'` so it returned 'light';
// on the client, after Zustand's persist middleware rehydrated, it
// could return 'dark' from localStorage. Any component that used
// `isDark` for class names hydration-mismatched on the first paint,
// flickering between the SSR default and the persisted choice.
//
// We now seed effectiveTheme as 'light' (matches SSR) and update it
// inside useEffect — that effect only runs client-side, AFTER React
// has committed the first render, so the SSR ↔ first-render output
// is identical. Subsequent renders pick up the real value.
//
// We also listen for the system-theme media query so `theme === 'system'`
// follows the OS dynamically without requiring a manual setTheme().
export function useTheme() {
  const { theme, setTheme, getEffectiveTheme, getSystemTheme } = useThemeStore()
  const [effectiveTheme, setEffectiveTheme] = useState<'light' | 'dark'>('light')

  useEffect(() => {
    setEffectiveTheme(getEffectiveTheme())
    if (theme === 'system' && typeof window !== 'undefined') {
      const mql = window.matchMedia('(prefers-color-scheme: dark)')
      const onChange = () => setEffectiveTheme(getSystemTheme())
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    }
  }, [theme, getEffectiveTheme, getSystemTheme])

  return {
    theme,
    setTheme,
    effectiveTheme,
    isDark: effectiveTheme === 'dark',
  }
}