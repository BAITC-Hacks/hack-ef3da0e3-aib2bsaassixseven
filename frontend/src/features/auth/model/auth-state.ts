export type AuthActionState = {
  status: "idle" | "error" | "success";
  message: string;
};

export const initialAuthState: AuthActionState = {
  status: "idle",
  message: "",
};
