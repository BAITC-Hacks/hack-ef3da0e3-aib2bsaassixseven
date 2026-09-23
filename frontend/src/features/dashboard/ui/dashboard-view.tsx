"use client";

import Link from "next/link";

import { PageHeader } from "@/components/ui/page-header";
import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";
import type { DemoMeetingStatus } from "@/features/demo-workspace/model/demo-data";
import { useMeetingsQuery } from "@/features/meetings/api/hooks";
import type { Meeting } from "@/features/meetings/api/schemas";

import styles from "./dashboard-view.module.scss";

const dashboardStatusLabels: Record<DemoMeetingStatus, string> = {
  queued: "Future",
  processing: "In process",
  review_required: "In process",
  approved: "Closed",
  failed: "Failed",
};

export function dashboardStatusLabel(status: DemoMeetingStatus) {
  return dashboardStatusLabels[status];
}

export function DashboardView() {
  const workspace = useDemoWorkspace();

  return workspace.isDemo ? (
    <DashboardContent
      isDemo
      meetings={workspace.meetings}
      profileName={workspace.profile.displayName}
    />
  ) : (
    <LiveDashboardView profileName={workspace.profile.displayName} />
  );
}

function LiveDashboardView({ profileName }: { profileName: string }) {
  const query = useMeetingsQuery();
  if (query.isPending) return <p role="status">Loading meetings…</p>;
  if (query.error) return <p role="alert">The meeting service could not be reached.</p>;

  return (
    <DashboardContent
      isDemo={false}
      meetings={query.data.items}
      profileName={profileName}
    />
  );
}

function DashboardContent({
  isDemo,
  meetings,
  profileName,
}: {
  isDemo: boolean;
  meetings: Array<
    | ReturnType<typeof useDemoWorkspace>["meetings"][number]
    | Meeting
  >;
  profileName: string;
}) {
  const recentMeetings = [...meetings].sort(
    (left, right) =>
      new Date("recordedAt" in right ? right.recordedAt : right.created_at).getTime() -
      new Date("recordedAt" in left ? left.recordedAt : left.created_at).getTime(),
  );

  return (
    <div>
      <PageHeader
        title={`Good afternoon, ${profileName}`}
      />

      <section className={styles.section} aria-labelledby="recent-meetings-title">
        <header className={styles.sectionHeader}>
          <h2 id="recent-meetings-title">Recent meetings</h2>
          <Link href="/meetings">View all</Link>
        </header>

        {meetings.length > 0 ? (
          <ol className={styles.meetingList}>
            {recentMeetings.slice(0, 4).map((meeting) => {
              const visibleStatus = dashboardStatusLabel(meeting.status);

              return (
                <li key={meeting.id}>
                  <article aria-labelledby={`${meeting.id}-title`}>
                    <div className={styles.meetingIdentity}>
                      <h3 id={`${meeting.id}-title`}>
                        <Link href={`/meetings/${meeting.id}`}>
                          {meeting.title}
                        </Link>
                      </h3>
                      <p className={styles.participants}>
                        {("participantNames" in meeting
                          ? meeting.participantNames
                          : meeting.participants).length > 0
                          ? ("participantNames" in meeting
                              ? meeting.participantNames
                              : meeting.participants).join(", ")
                          : "No participants added"}
                      </p>
                    </div>
                    <span
                      aria-label={visibleStatus}
                      className={styles.status}
                      data-status={meeting.status}
                    >
                      {visibleStatus}
                    </span>
                  </article>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className={styles.emptyMeetings}>
            No meetings yet. Add a recording to get started.
          </p>
        )}
      </section>

      {isDemo ? (
        <p className={styles.demoNotice}>
          Demo data stays in memory for this browser session and is never
          uploaded.
        </p>
      ) : null}
    </div>
  );
}
