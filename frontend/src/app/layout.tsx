import type { Metadata } from "next";

import { AppProviders } from "@/components/providers/app-providers";

import "./globals.scss";

export const metadata: Metadata = {
  title: {
    default: "Tirke",
    template: "%s · Tirke",
  },
  description:
    "Private meeting transcription, review, and protocol export.",
  icons: {
    icon: [{ url: "/favicon.png", type: "image/png" }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
