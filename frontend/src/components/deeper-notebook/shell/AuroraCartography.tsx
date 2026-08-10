'use client'

/**
 * Presentation-only atmospheric layer for the Luminous shell.
 *
 * The layer has no content or effects of its own. Its motion and visibility
 * are controlled by the existing display-preference attributes and semantic
 * tokens in the app style system.
 */
export function AuroraCartography() {
  return <div aria-hidden="true" className="dn-aurora-bg dn-aurora-cartography" />
}
