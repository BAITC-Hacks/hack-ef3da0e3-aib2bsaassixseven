export type DemoMeetingStatus =
  | "queued"
  | "processing"
  | "review_required"
  | "approved"
  | "failed";

export type DemoTaskStatus = "open" | "in_progress" | "completed";

export type DemoTranscriptSegment = {
  id: string;
  speaker: string;
  time: string;
  text: string;
};

export type DemoAssignment = {
  id: string;
  title: string;
  assignee: string | null;
  dueDate: string | null;
  status: DemoTaskStatus;
  evidence: string;
  time: string;
};

export type DemoMeeting = {
  id: string;
  title: string;
  recordedAt: string;
  createdAt: string;
  status: DemoMeetingStatus;
  processingStage: string | null;
  language: "auto" | "ru" | "kk" | "mixed";
  participantNames: string[];
  audioFileName: string;
  duration: string | null;
  summary: string;
  transcript: DemoTranscriptSegment[];
  assignments: DemoAssignment[];
};

export type DemoProfile = {
  displayName: string;
  email: string;
  role: string;
  department: string;
};

export const seededMeetings: DemoMeeting[] = [
  {
    id: "weekly-product-sync",
    title: "Еженедельный продуктовый синк",
    recordedAt: "2026-09-23T10:00",
    createdAt: "2026-09-23T10:46:00+05:00",
    status: "approved",
    processingStage: null,
    language: "mixed",
    participantNames: ["Влад", "Алия", "Ернур", "Ерасыл"],
    audioFileName: "product-sync-23-09.m4a",
    duration: "42:18",
    summary:
      "Команда согласовала структуру MVP, порядок интеграции NVIDIA-сервера и сценарий демонстрации. До следующего синка нужно завершить интерфейс проверки и подготовить смешанную тестовую запись.",
    transcript: [
      {
        id: "tr-1",
        speaker: "Влад",
        time: "00:03:18",
        text: "Давайте до пятницы закончим интерфейс проверки протокола и покажем его всей команде.",
      },
      {
        id: "tr-2",
        speaker: "Ернур",
        time: "00:07:44",
        text: "Я подготовлю контракт meeting API и описание локального хранения результатов.",
      },
      {
        id: "tr-3",
        speaker: "Ерасыл",
        time: "00:15:09",
        text: "Аралас тілдегі он минуттық тест жазбасын ертең жіберемін.",
      },
    ],
    assignments: [
      {
        id: "task-review-ui",
        title: "Завершить интерфейс проверки протокола",
        assignee: "Влад",
        dueDate: "2026-09-25",
        status: "in_progress",
        evidence: "Давайте до пятницы закончим интерфейс проверки протокола…",
        time: "00:03:18",
      },
      {
        id: "task-api-contract",
        title: "Подготовить контракт meeting API",
        assignee: "Ернур",
        dueDate: "2026-09-24",
        status: "open",
        evidence: "Я подготовлю контракт meeting API…",
        time: "00:07:44",
      },
      {
        id: "task-mixed-recording",
        title: "Подготовить смешанную тестовую запись",
        assignee: "Ерасыл",
        dueDate: "2026-09-24",
        status: "completed",
        evidence: "Аралас тілдегі он минуттық тест жазбасын ертең жіберемін.",
        time: "00:15:09",
      },
    ],
  },
  {
    id: "budget-review",
    title: "Обсуждение бюджета пилота",
    recordedAt: "2026-09-22T15:30",
    createdAt: "2026-09-22T16:18:00+05:00",
    status: "review_required",
    processingStage: null,
    language: "ru",
    participantNames: ["Алия", "Влад", "Данияр"],
    audioFileName: "pilot-budget.wav",
    duration: "36:02",
    summary:
      "Черновик: обсуждены вычислительные ресурсы пилота и лимит хранения временных файлов. Два поручения требуют подтверждения ответственного.",
    transcript: [
      {
        id: "budget-tr-1",
        speaker: "SPEAKER_01",
        time: "00:11:20",
        text: "Нужно уточнить стоимость дополнительной GPU-сессии до следующей встречи.",
      },
    ],
    assignments: [
      {
        id: "task-gpu-cost",
        title: "Уточнить стоимость дополнительной GPU-сессии",
        assignee: null,
        dueDate: null,
        status: "open",
        evidence: "Нужно уточнить стоимость дополнительной GPU-сессии…",
        time: "00:11:20",
      },
    ],
  },
  {
    id: "customer-interview",
    title: "Интервью с заказчиком",
    recordedAt: "2026-09-23T12:10",
    createdAt: "2026-09-23T12:54:00+05:00",
    status: "processing",
    processingStage: "Диаризация спикеров",
    language: "auto",
    participantNames: ["Алия", "Заказчик"],
    audioFileName: "customer-interview.mp3",
    duration: null,
    summary: "",
    transcript: [],
    assignments: [],
  },
];
