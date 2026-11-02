export interface RuntimeConfig {
  region: string
  userPoolId: string
  clientId: string
  cognitoDomain: string
}

let cached: RuntimeConfig | null = null

/** Written to S3 by Terraform, so one build works for every environment. */
export async function loadConfig(): Promise<RuntimeConfig> {
  if (cached) return cached
  const response = await fetch('/config.json', { cache: 'no-cache' })
  if (!response.ok) throw new Error(`Could not load /config.json (${response.status})`)
  cached = (await response.json()) as RuntimeConfig
  return cached
}
