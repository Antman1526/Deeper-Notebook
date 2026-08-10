import { LoginForm } from '@/components/auth/LoginForm'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { AuthFolio } from '@/components/deeper-notebook/AuthFolio'

export default function LoginPage() {
  return (
    <ErrorBoundary>
      <AuthFolio><LoginForm /></AuthFolio>
    </ErrorBoundary>
  )
}
