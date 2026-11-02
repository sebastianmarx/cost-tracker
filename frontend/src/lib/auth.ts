import { ErrorResponse, UserManager, WebStorageStateStore, type User } from 'oidc-client-ts'
import { loadConfig, type RuntimeConfig } from './config'

let manager: UserManager | null = null
let config: RuntimeConfig | null = null

/**
 * Cognito hosted UI with Authorization Code + PKCE. Tokens live in
 * localStorage so the session survives closing the tab or browser; the
 * long-lived refresh token keeps it alive until an explicit sign-out.
 */
async function getManager(): Promise<UserManager> {
  if (manager) return manager
  config = await loadConfig()
  manager = new UserManager({
    authority: `https://cognito-idp.${config.region}.amazonaws.com/${config.userPoolId}`,
    client_id: config.clientId,
    redirect_uri: `${window.location.origin}/callback`,
    post_logout_redirect_uri: `${window.location.origin}/`,
    response_type: 'code',
    scope: 'openid email',
    userStore: new WebStorageStateStore({ store: window.localStorage }),
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    automaticSilentRenew: true, // uses the refresh token, no iframe
    loadUserInfo: false,
  })
  return manager
}

let refreshing: Promise<User | null> | null = null

/** Refresh-token grant rejected for good (revoked/expired) vs. a transient failure. */
function isDefinitiveAuthError(e: unknown): boolean {
  if (e instanceof ErrorResponse) return e.error === 'invalid_grant' || e.error === 'invalid_client'
  return false
}

/** One refresh at a time; concurrent callers share the same request. */
function refresh(um: UserManager): Promise<User | null> {
  refreshing ??= um
    .signinSilent()
    .catch(async (e) => {
      // Only drop the session when Cognito says the refresh token is dead.
      // Network errors etc. keep the stored user so the next call can retry.
      if (isDefinitiveAuthError(e)) await um.removeUser()
      return null
    })
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

export async function currentUser(): Promise<User | null> {
  const um = await getManager()
  const user = await um.getUser()
  if (user && !user.expired) return user
  if (user?.refresh_token) return refresh(um)
  return null
}

/** Forces a token refresh, e.g. after the API rejected the access token. */
export async function forceRefresh(): Promise<User | null> {
  const um = await getManager()
  const user = await um.getUser()
  return user?.refresh_token ? refresh(um) : null
}

export async function signIn(returnTo = window.location.pathname): Promise<void> {
  const um = await getManager()
  await um.signinRedirect({ state: { returnTo } })
}

/** Finishes the redirect from Cognito and returns the path to go back to. */
export async function completeSignIn(): Promise<string> {
  const um = await getManager()
  const user = await um.signinRedirectCallback()
  const state = user.state as { returnTo?: string } | undefined
  const target = state?.returnTo ?? '/'
  // Only same-origin paths; never an absolute URL from the state.
  return target.startsWith('/') && !target.startsWith('//') ? target : '/'
}

export async function signOut(): Promise<void> {
  const um = await getManager()
  await um.removeUser()
  // Cognito's logout endpoint is not in its discovery document.
  const params = new URLSearchParams({
    client_id: config!.clientId,
    logout_uri: `${window.location.origin}/`,
  })
  window.location.assign(`${config!.cognitoDomain}/logout?${params}`)
}

export async function accessToken(): Promise<string | null> {
  const user = await currentUser()
  return user?.access_token ?? null
}
