interface DesktopVersionWindow {
  DEEPER_NOTEBOOK_VERSION?: string
  ONP_VERSION?: string
}

export function readDesktopVersion(
  target: object,
): string | undefined {
  const bridge = target as DesktopVersionWindow
  return bridge.DEEPER_NOTEBOOK_VERSION || bridge.ONP_VERSION
}
