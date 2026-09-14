import { create } from "zustand";
import type { User } from "../utils/api";
import { fetchMe } from "../utils/api";

interface AuthStore {
  user: User | null;
  token: string | null;
  initialized: boolean;
  setSession: (user: User, token: string) => void;
  clear: () => void;
  hydrate: () => Promise<void>;
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  token: null,
  initialized: false,

  setSession: (user, token) => {
    localStorage.setItem("ff3d_token", token);
    localStorage.setItem("ff3d_user", JSON.stringify(user));
    set({ user, token, initialized: true });
  },

  clear: () => {
    localStorage.removeItem("ff3d_token");
    localStorage.removeItem("ff3d_user");
    set({ user: null, token: null, initialized: true });
  },

  hydrate: async () => {
    if (get().initialized) return;
    const token = localStorage.getItem("ff3d_token");
    if (!token) {
      set({ initialized: true });
      return;
    }
    try {
      const me = await fetchMe();
      set({ user: me, token, initialized: true });
    } catch {
      // 토큰 만료/무효
      localStorage.removeItem("ff3d_token");
      localStorage.removeItem("ff3d_user");
      set({ user: null, token: null, initialized: true });
    }
  },
}));
