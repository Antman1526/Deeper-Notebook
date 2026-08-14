import { LoginForm } from '@/components/auth/LoginForm'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { AuthFolio } from '@/components/deeper-notebook/AuthFolio'
import { WorkspaceAuthFrame } from '@/components/deeper-notebook/workspace/WorkspaceAuthFrame'
import { isVisualSystemV2Enabled } from '@/lib/features'

export default function LoginPage() {
  const visualSystemV2Enabled = isVisualSystemV2Enabled()
  const Presentation = visualSystemV2Enabled ? WorkspaceAuthFrame : AuthFolio

  return (
    <ErrorBoundary>
      <Presentation><LoginForm headingLevel={visualSystemV2Enabled ? 2 : 1} /></Presentation>
    </ErrorBoundary>
  )
}
