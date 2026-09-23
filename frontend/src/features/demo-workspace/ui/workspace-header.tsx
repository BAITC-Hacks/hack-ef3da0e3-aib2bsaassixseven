"use client";

import Link from "next/link";

import { SiteHeader } from "@/components/layout/site-header";
import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";

import styles from "./workspace-header.module.scss";

export function WorkspaceHeader() {
  const { openNewMeeting, profile } = useDemoWorkspace();

  return (
    <SiteHeader
      action={
        <>
          <button
            className={styles.newMeeting}
            onClick={openNewMeeting}
            type="button"
          >
            <span aria-hidden="true" className={styles.addIcon}>
              +
            </span>
            <span>New meeting</span>
          </button>
          <Link
            aria-label="Open profile"
            className={styles.profile}
            href="/settings"
            title="Open profile"
          >
            <span aria-hidden="true">
              {profile.displayName.slice(0, 1).toUpperCase()}
            </span>
          </Link>
        </>
      }
    />
  );
}
