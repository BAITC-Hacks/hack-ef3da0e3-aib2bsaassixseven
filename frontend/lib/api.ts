import { getPublicEnv } from "@/lib/env";

export type MeResponse = {
  user: {
    id: string;
    email: string | null;
    role: string;
  };
  profile: {
    id: string;
    display_name: string | null;
    created_at: string;
    updated_at: string;
  } | null;
};

export class ApiError extends Error {
  constructor(message = "FastAPI request failed") {
    super(message);
    this.name = "ApiError";
  }
}

export class UnauthorizedApiError extends ApiError {
  constructor() {
    super("FastAPI rejected the current session");
    this.name = "UnauthorizedApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isMeResponse(value: unknown): value is MeResponse {
  if (!isRecord(value) || !isRecord(value.user)) return false;
  if (
    typeof value.user.id !== "string" ||
    typeof value.user.role !== "string" ||
    !(typeof value.user.email === "string" || value.user.email === null)
  ) {
    return false;
  }
  if (value.profile === null) return true;
  return (
    isRecord(value.profile) &&
    typeof value.profile.id === "string" &&
    (typeof value.profile.display_name === "string" ||
      value.profile.display_name === null) &&
    typeof value.profile.created_at === "string" &&
    typeof value.profile.updated_at === "string"
  );
}

export async function fetchCurrentUser(
  accessToken: string,
  fetcher: typeof fetch = fetch,
): Promise<MeResponse> {
  const { apiUrl } = getPublicEnv();
  const response = await fetcher(`${apiUrl}/api/v1/me`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (response.status === 401) throw new UnauthorizedApiError();
  if (!response.ok) throw new ApiError();

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new ApiError("FastAPI returned invalid JSON");
  }
  if (!isMeResponse(data)) throw new ApiError("FastAPI returned invalid data");
  return data;
}

