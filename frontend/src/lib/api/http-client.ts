import { z } from "zod";

import { publicEnv } from "@/lib/config/public-env";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type RequestOptions<TBody> = Omit<RequestInit, "body"> & {
  body?: TBody;
};

export async function apiRequest<TResponse, TBody = never>(
  path: `/${string}`,
  schema: z.ZodType<TResponse>,
  options: RequestOptions<TBody> = {},
): Promise<TResponse> {
  const response = await fetch(`${publicEnv.NEXT_PUBLIC_API_URL}${path}`, {
    ...options,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    headers: {
      Accept: "application/json",
      ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const details = await response.json().catch(() => undefined);
    throw new ApiError("API request failed", response.status, details);
  }

  return schema.parse(await response.json());
}
