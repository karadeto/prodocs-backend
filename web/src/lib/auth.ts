const TOKEN_KEY = 'prodocs.token'
const EMAIL_KEY = 'prodocs.email'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getEmail(): string | null {
  return localStorage.getItem(EMAIL_KEY)
}

export function isAuthenticated(): boolean {
  const token = getToken()
  if (!token) return false
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return typeof payload.exp !== 'number' || payload.exp * 1000 > Date.now()
  } catch {
    return false
  }
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(EMAIL_KEY)
}

async function authRequest(path: string, email: string, password: string): Promise<void> {
  const res = await fetch(`/api/v1/auth/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    let detail = 'Something went wrong. Try again.'
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* keep default */
    }
    throw new Error(detail)
  }
  const data = await res.json()
  localStorage.setItem(TOKEN_KEY, data.access_token)
  localStorage.setItem(EMAIL_KEY, data.email)
}

export const login = (email: string, password: string) => authRequest('login', email, password)
export const register = (email: string, password: string) => authRequest('register', email, password)
