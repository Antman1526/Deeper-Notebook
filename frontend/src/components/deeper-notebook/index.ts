/**
 * Deeper Notebook product component layer. See ./README.md for the pattern.
 *
 * Import from this barrel so upstream-page edits are one-line:
 *   import { ReasoningSlotCard } from '@/components/deeper-notebook'
 */

import './folio/folio.css'

export { ReasoningSlotCard } from './ReasoningSlotCard'
export { ThemeSwitcher } from './ThemeSwitcher'
export { ThemeGallery } from './ThemeGallery'
export { ThemePreviewCard } from './ThemePreviewCard'
export { GmailIntegration } from './GmailIntegration'
export { GmailSidebarButton } from './GmailSidebarButton'
export { ArtifactRail } from './ArtifactRail'
export { RunTimeline } from './RunTimeline'
export { SourceHealthPill, getSourceReadiness } from './SourceHealthPill'
export { ModelFleetBadge } from './ModelFleetBadge'
export { CitationCoverageBadge } from './CitationCoverageBadge'
export { CitationDrawer } from './CitationDrawer'
export { DataTableViewer, FlashcardDeck, MindMapViewer, QuizRunner } from './StudyArtifactViewers'

export { EvidenceInsert } from './folio/EvidenceInsert'
export { FolioIndex } from './folio/FolioIndex'
export { FolioPage } from './folio/FolioPage'
export { FolioRouteFrame } from './folio/FolioRouteFrame'
export { FolioSpread } from './folio/FolioSpread'
export { FolioState } from './folio/FolioState'
export { FolioTab } from './folio/FolioTab'
export { MarginNote } from './folio/MarginNote'
export type { EvidenceInsertProps } from './folio/EvidenceInsert'
export type { FolioIndexProps } from './folio/FolioIndex'
export type { FolioPageProps } from './folio/FolioPage'
export type { FolioRouteFrameProps } from './folio/FolioRouteFrame'
export type { FolioSpreadProps } from './folio/FolioSpread'
export type { FolioStateProps } from './folio/FolioState'
export type { FolioTabItem, FolioTabProps } from './folio/FolioTab'
export type { MarginNoteProps } from './folio/MarginNote'
