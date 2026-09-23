import type { Metadata } from "next";
import Link from "next/link";

import { SiteHeader } from "@/components/layout/site-header";
import { DitheredShaderBackground } from "@/features/landing/components/dithered-shader";

import styles from "./page.module.scss";

export const metadata: Metadata = {
  title: "Главная",
  description:
    "Локальная обработка совещаний, расшифровка и подготовка протоколов.",
};

export default function HomePage() {
  return (
    <main className={styles.landing}>
      <DitheredShaderBackground />

      <SiteHeader
        action={
          <div className={styles.authActions}>
            <Link className={styles.workspaceLink} href="/login">
              Log in
            </Link>
            <Link className={styles.signUpLink} href="/login?mode=sign-up">
              Sign up
            </Link>
          </div>
        }
        overlay
      />

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <h1>A meeting record you can verify.</h1>
          <p className={styles.introduction}>
            Tirke turns Russian, Kazakh and mixed-language recordings into an
            editable transcript, decisions and assignments—on infrastructure
            you control.
          </p>
          <div className={styles.actions}>
            <Link className={styles.primaryAction} href="/meetings/new">
              Upload a recording
            </Link>
            <Link className={styles.secondaryAction} href="/dashboard">
              Open dashboard
            </Link>
          </div>
        </div>

        <ol className={styles.workflow} aria-label="How Tirke works">
          <li>
            <span aria-hidden="true">01</span>
            <div>
              <h2>Upload</h2>
              <p>Add a finished meeting recording from your device.</p>
            </div>
          </li>
          <li>
            <span aria-hidden="true">02</span>
            <div>
              <h2>Review</h2>
              <p>Check the transcript and every source-linked assignment.</p>
            </div>
          </li>
          <li>
            <span aria-hidden="true">03</span>
            <div>
              <h2>Approve</h2>
              <p>Export the saved revision only after a human review.</p>
            </div>
          </li>
        </ol>
      </section>

      <footer className={styles.footer}>
        <div className={styles.footerBrand}>
          <Link href="/">Tirke</Link>
          <p>Private meeting intelligence for Russian and Kazakh speech.</p>
        </div>
        <nav className={styles.footerNavigation} aria-label="Footer navigation">
          <Link href="/dashboard">Dashboard</Link>
          <Link href="/meetings">Meetings</Link>
          <Link href="/tasks">Tasks</Link>
          <Link href="/settings">Settings</Link>
        </nav>
        <div className={styles.footerMeta}>
          <span>Local inference · Human approval</span>
          <span>© 2026 Tirke</span>
        </div>
      </footer>
    </main>
  );
}
