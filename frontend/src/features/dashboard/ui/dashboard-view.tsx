"use client";

import Link from "next/link";

import { PageHeader } from "@/components/ui/page-header";
import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";
import type { DemoMeetingStatus } from "@/features/demo-workspace/model/demo-data";

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
  const { meetings, profile } = useDemoWorkspace();
  const recentMeetings = [...meetings].sort(
    (left, right) =>
      new Date(right.recordedAt).getTime() -
      new Date(left.recordedAt).getTime(),
  );

  return (
    <div>
      <PageHeader
        title={`Good afternoon, ${profile.displayName}`}
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
                        {meeting.participantNames.length > 0
                          ? meeting.participantNames.join(", ")
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

      <p className={styles.demoNotice}>
        Demo data stays in this browser session until the meeting API is
        connected.
      </p>
    </div>
  );
}
