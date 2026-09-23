"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type {
  DemoMeeting,
  DemoProfile,
  DemoTaskStatus,
} from "@/features/demo-workspace/model/demo-data";
import { seededMeetings } from "@/features/demo-workspace/model/demo-data";

export type NewMeetingInput = {
  title: string;
  recordedAt: string;
  language: DemoMeeting["language"];
  participantNames: string[];
  audioFileName: string;
};

type DemoWorkspaceValue = {
  meetings: DemoMeeting[];
  profile: DemoProfile;
  isNewMeetingOpen: boolean;
  openNewMeeting: () => void;
  closeNewMeeting: () => void;
  createMeeting: (input: NewMeetingInput) => string;
  deleteMeeting: (meetingId: string) => void;
  updateMeeting: (
    meetingId: string,
    patch: Partial<Pick<DemoMeeting, "title" | "summary" | "transcript">>,
  ) => void;
  saveReview: (
    meetingId: string,
    review: Pick<
      DemoMeeting,
      "title" | "summary" | "transcript" | "assignments"
    >,
  ) => void;
  approveMeeting: (meetingId: string) => void;
  updateTaskStatus: (taskId: string, status: DemoTaskStatus) => void;
  updateProfile: (profile: DemoProfile) => void;
};

const DemoWorkspaceContext = createContext<DemoWorkspaceValue | null>(null);

export function DemoWorkspaceProvider({
  children,
  initialProfile,
}: {
  children: React.ReactNode;
  initialProfile: DemoProfile;
}) {
  const [meetings, setMeetings] = useState(seededMeetings);
  const [profile, setProfile] = useState(initialProfile);
  const [isNewMeetingOpen, setIsNewMeetingOpen] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const activeTimers = timers.current;
    return () => activeTimers.forEach(window.clearTimeout);
  }, []);

  const value = useMemo<DemoWorkspaceValue>(
    () => ({
      meetings,
      profile,
      isNewMeetingOpen,
      openNewMeeting: () => setIsNewMeetingOpen(true),
      closeNewMeeting: () => setIsNewMeetingOpen(false),
      createMeeting(input) {
        const id = crypto.randomUUID();
        const meeting: DemoMeeting = {
          id,
          title: input.title,
          recordedAt: input.recordedAt,
          createdAt: new Date().toISOString(),
          status: "processing",
          processingStage: "Загрузка на NVIDIA-сервер",
          language: input.language,
          participantNames: input.participantNames,
          audioFileName: input.audioFileName,
          duration: null,
          summary: "",
          transcript: [],
          assignments: [],
        };

        setMeetings((current) => [meeting, ...current]);

        timers.current.push(
          window.setTimeout(() => {
            setMeetings((current) =>
              current.map((item) =>
                item.id === id
                  ? { ...item, processingStage: "Транскрибация записи" }
                  : item,
              ),
            );
          }, 900),
          window.setTimeout(() => {
            setMeetings((current) =>
              current.map((item) =>
                item.id === id
                  ? { ...item, processingStage: "Извлечение поручений" }
                  : item,
              ),
            );
          }, 1_800),
          window.setTimeout(() => {
            setMeetings((current) =>
              current.map((item) =>
                item.id === id
                  ? {
                      ...item,
                      status: "review_required",
                      processingStage: null,
                      duration: "18:42",
                      summary:
                        "Черновик готов. Проверьте спикеров, содержание и поручения перед утверждением.",
                      transcript: [
                        {
                          id: `${id}-segment-1`,
                          speaker: input.participantNames[0] || "SPEAKER_01",
                          time: "00:01:12",
                          text: "Проверочный фрагмент расшифровки новой встречи.",
                        },
                      ],
                      assignments: [
                        {
                          id: `${id}-task-1`,
                          title: "Проверить автоматически созданный протокол",
                          assignee: input.participantNames[0] || null,
                          dueDate: null,
                          status: "open",
                          evidence: "Проверочный фрагмент расшифровки новой встречи.",
                          time: "00:01:12",
                        },
                      ],
                    }
                  : item,
              ),
            );
          }, 2_800),
        );

        return id;
      },
      deleteMeeting(meetingId) {
        setMeetings((current) =>
          current.filter((meeting) => meeting.id !== meetingId),
        );
      },
      updateMeeting(meetingId, patch) {
        setMeetings((current) =>
          current.map((meeting) =>
            meeting.id === meetingId
              ? { ...meeting, ...patch, status: "review_required" }
              : meeting,
          ),
        );
      },
      saveReview(meetingId, review) {
        setMeetings((current) =>
          current.map((meeting) =>
            meeting.id === meetingId
              ? { ...meeting, ...review, status: "review_required" }
              : meeting,
          ),
        );
      },
      approveMeeting(meetingId) {
        setMeetings((current) =>
          current.map((meeting) =>
            meeting.id === meetingId
              ? { ...meeting, status: "approved" }
              : meeting,
          ),
        );
      },
      updateTaskStatus(taskId, status) {
        setMeetings((current) =>
          current.map((meeting) => ({
            ...meeting,
            assignments: meeting.assignments.map((task) =>
              task.id === taskId ? { ...task, status } : task,
            ),
          })),
        );
      },
      updateProfile: setProfile,
    }),
    [isNewMeetingOpen, meetings, profile],
  );

  return (
    <DemoWorkspaceContext.Provider value={value}>
      {children}
    </DemoWorkspaceContext.Provider>
  );
}

export function useDemoWorkspace() {
  const context = useContext(DemoWorkspaceContext);
  if (!context) {
    throw new Error("useDemoWorkspace must be used inside DemoWorkspaceProvider");
  }
  return context;
}
