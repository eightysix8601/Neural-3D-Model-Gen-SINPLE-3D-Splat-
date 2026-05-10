import { create } from "zustand";
import type { Project } from "../utils/api";

interface Store {
  projects: Project[]; selectedProject: Project | null;
  liveProgress: number; liveStep: string; wsConnection: WebSocket | null;
  setProjects: (p: Project[]) => void; setSelectedProject: (p: Project | null) => void;
  updateProject: (id: string, patch: Partial<Project>) => void;
  addProject: (p: Project) => void; removeProject: (id: string) => void;
  connectWs: (projectId: string) => void; disconnectWs: () => void;
}

export const useProjectStore = create<Store>((set, get) => ({
  projects: [], selectedProject: null, liveProgress: 0, liveStep: "", wsConnection: null,
  setProjects: (projects) => set({ projects }),
  addProject: (p) => set((s) => ({ projects: [p, ...s.projects] })),
  removeProject: (id) => set((s) => ({ projects: s.projects.filter((p) => p.id !== id) })),
  setSelectedProject: (project) => set({ selectedProject: project, liveProgress: 0, liveStep: "" }),
  updateProject: (id, patch) => set((s) => ({
    projects: s.projects.map((p) => p.id === id ? { ...p, ...patch } : p),
    selectedProject: s.selectedProject?.id === id ? { ...s.selectedProject, ...patch } : s.selectedProject,
  })),
  connectWs: (projectId) => {
    get().disconnectWs();
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/pipeline/${projectId}`);
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "progress") {
          set({ liveProgress: msg.data.progress ?? 0, liveStep: msg.data.step ?? "" });
          get().updateProject(projectId, { progress: msg.data.progress ?? 0, current_step: msg.data.step ?? null, status: msg.data.status ?? "RUNNING" });
        }
        if (msg.type === "completed") {
          set({ liveProgress: 100, liveStep: "완료!" });
          get().updateProject(projectId, { status: "SUCCESS", progress: 100 });
          import("../utils/api").then(({ getProject }) => getProject(projectId).then((proj) => {
            get().updateProject(projectId, proj);
            if (get().selectedProject?.id === projectId) set({ selectedProject: proj });
          }));
        }
        if (msg.type === "error") get().updateProject(projectId, { status: "FAILED", error_message: msg.data.message });
      } catch {}
    };
    ws.onerror = (e) => console.error("[WS]", e);
    set({ wsConnection: ws });
  },
  disconnectWs: () => { get().wsConnection?.close(); set({ wsConnection: null }); },
}));
