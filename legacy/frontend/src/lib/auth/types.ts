export interface FusionUser {
  sub: string
  email: string
  name: string
  groups: string[]
}

export interface AuthContextValue {
  user: FusionUser | null
  isAuthenticated: boolean
  isLoading: boolean
  isBypass: boolean
  signIn: () => Promise<void>
  signOut: () => Promise<void>
}
