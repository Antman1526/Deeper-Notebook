interface DesktopVersionWindow {
  DEEPER_NOTEBOOK_VERSION?: string
  // Transitional fallback for desktop wrappers shipped before the rebrand.
  ONP_VERSION?: string
}

export function readDesktopVersion(
  target: object,
): string | undefined {
  const bridge = target as DesktopVersionWindow
  return bridge.DEEPER_NOTEBOOK_VERSION || bridge.ONP_VERSION
}
