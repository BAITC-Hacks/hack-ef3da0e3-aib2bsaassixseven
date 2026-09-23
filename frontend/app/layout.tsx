import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hackalem — Full-stack hackathon launchpad",
  description: "A FastAPI, Next.js, and Supabase starter built to ship.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>
        <a className="skip-link" href="#main">Skip to content</a>
        {children}
      </body>
    </html>
  );
}
