"use client";

import Link from "next/link";

import { SiteHeader } from "@/components/layout/site-header";
import { signOut } from "@/features/auth/actions";
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
            New meeting
          </button>
          <Link className={styles.profile} href="/settings">
            <span aria-hidden="true">
              {profile.displayName.slice(0, 1).toUpperCase()}
            </span>
            <span className={styles.profileName}>{profile.displayName}</span>
          </Link>
          <form action={signOut}>
            <button className={styles.signOut} type="submit">
              Выйти
            </button>
          </form>
        </>
      }
    />
  );
}
