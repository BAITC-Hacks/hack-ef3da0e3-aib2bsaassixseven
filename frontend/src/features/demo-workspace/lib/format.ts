import type {
  DemoMeetingStatus,
  DemoTaskStatus,
} from "@/features/demo-workspace/model/demo-data";

const meetingStatusLabels: Record<DemoMeetingStatus, string> = {
  queued: "В очереди",
  processing: "Обработка",
  review_required: "Нужна проверка",
  approved: "Утверждено",
  failed: "Ошибка",
};

const taskStatusLabels: Record<DemoTaskStatus, string> = {
  open: "Открыто",
  in_progress: "В работе",
  completed: "Выполнено",
};

export function meetingStatusLabel(status: DemoMeetingStatus) {
  return meetingStatusLabels[status];
}

export function taskStatusLabel(status: DemoTaskStatus) {
  return taskStatusLabels[status];
}

export function formatMeetingDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDueDate(value: string | null) {
  if (!value) return "Не указан";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
  }).format(new Date(`${value}T12:00:00`));
}
