import { LoginForm } from '@/components/auth/LoginForm'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { AuthFolio } from '@/components/deeper-notebook/AuthFolio'
import { WorkspaceAuthFrame } from '@/components/deeper-notebook/workspace/WorkspaceAuthFrame'
import { isVisualSystemV2Enabled } from '@/lib/features'

export default function LoginPage() {
  const Presentation = isVisualSystemV2Enabled() ? WorkspaceAuthFrame : AuthFolio

  return (
    <ErrorBoundary>
      <Presentation><LoginForm /></Presentation>
    </ErrorBoundary>
  )
}
