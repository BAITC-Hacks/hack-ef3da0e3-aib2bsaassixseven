type PublicEnvironment = Record<string, string | undefined>;

const fallback = {
  apiUrl: "http://localhost:8000",
  supabasePublishableKey: "replace-with-publishable-key",
  supabaseUrl: "https://example.supabase.co",
} as const;

function withoutTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function getPublicEnv(source: PublicEnvironment = process.env) {
  const configuredUrl = source.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const configuredKey = source.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();

  return {
    apiUrl: withoutTrailingSlash(
      source.NEXT_PUBLIC_API_URL?.trim() || fallback.apiUrl,
    ),
    supabasePublishableKey:
      configuredKey || fallback.supabasePublishableKey,
    supabaseUrl: withoutTrailingSlash(configuredUrl || fallback.supabaseUrl),
    isSupabaseConfigured: Boolean(configuredUrl && configuredKey),
  };
}

