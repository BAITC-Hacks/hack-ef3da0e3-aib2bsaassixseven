import { z } from "zod";

export function normalizeApiUrl(value: string): string {
  const url = new URL(value);
  const pathname = url.pathname.replace(/\/+$/, "");

  url.pathname = pathname.endsWith("/api/v1")
    ? pathname
    : `${pathname}/api/v1`.replace(/\/{2,}/g, "/");
  url.search = "";
  url.hash = "";

  return url.toString().replace(/\/$/, "");
}

const publicEnvSchema = z.object({
  NEXT_PUBLIC_API_URL: z
    .url()
    .default("http://localhost:8000")
    .transform(normalizeApiUrl),
  NEXT_PUBLIC_APP_NAME: z.string().min(1).default("Tirke"),
  NEXT_PUBLIC_SITE_URL: z.url().default("http://localhost:3000"),
  NEXT_PUBLIC_SUPABASE_URL: z.url().default("https://example.supabase.co"),
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: z
    .string()
    .min(1)
    .default("replace-with-publishable-key"),
});

const source = {
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME,
  NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
};

export const publicEnv = {
  ...publicEnvSchema.parse(source),
  isSupabaseConfigured: Boolean(
    source.NEXT_PUBLIC_SUPABASE_URL?.trim() &&
      source.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim(),
  ),
};
