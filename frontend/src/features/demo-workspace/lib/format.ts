import type {
  DemoMeetingStatus,
  DemoTaskStatus,
} from "@/features/demo-workspace/model/demo-data";

const meetingStatusLabels: Record<DemoMeetingStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  review_required: "Needs review",
  approved: "Approved",
  failed: "Failed",
};

const taskStatusLabels: Record<DemoTaskStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  completed: "Completed",
};

const shortMonthNames = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

function parseIsoDateParts(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return null;

  const [, year, month, day] = match;
  const monthName = shortMonthNames[Number(month) - 1];
  if (!year || !monthName || !day) return null;

  return { day, monthName, year };
}

export function meetingStatusLabel(status: DemoMeetingStatus) {
  return meetingStatusLabels[status];
}

export function taskStatusLabel(status: DemoTaskStatus) {
  return taskStatusLabels[status];
}

export function formatMeetingDate(value: string) {
  const date = parseIsoDateParts(value);
  const time = /T(\d{2}):(\d{2})/.exec(value);
  if (!date || !time?.[1] || !time[2]) return value;

  return `${date.day} ${date.monthName} ${date.year} at ${time[1]}:${time[2]}`;
}

export function formatDueDate(value: string | null) {
  if (!value) return "Not set";
  const date = parseIsoDateParts(value);
  return date ? `${date.day} ${date.monthName}` : value;
}
