import axios from "axios";

export const api = axios.create({ baseURL: "/api/v1", timeout: 30000 });

// Auth token interceptor — stored under "ff3d_token"
api.interceptors.request.use((cfg) => {
  const t = typeof window !== "undefined" ? localStorage.getItem("ff3d_token") : null;
  if (t && cfg.headers) cfg.headers["Authorization"] = `Bearer ${t}`;
  return cfg;
});

api.interceptors.response.use(
  (r) => r,
  (e) => {
    const status = e.response?.status;
    if (status === 401 && typeof window !== "undefined") {
      // 토큰 만료/무효 — 자동 로그아웃
      localStorage.removeItem("ff3d_token");
      localStorage.removeItem("ff3d_user");
    }
    return Promise.reject(new Error(e.response?.data?.detail || e.message || "오류"));
  },
);

// ── 타입 ─────────────────────────────────────────────────────────────
export type ModelType   = "sugar" | "gof" | "twodgs" | "nerf" | "tripo";
export type JobStatus   = "PENDING" | "RUNNING" | "SUCCESS" | "FAILED";
export type AssetFormat = "glb" | "obj" | "ply";
export type Category    =
  | "other" | "character" | "vehicle" | "furniture"
  | "animal" | "food" | "prop" | "building";

export interface User {
  id: string;
  email: string;
  username: string;
  is_admin?: boolean;
  created_at: string;
}

export interface OwnerMini {
  id: string;
  username: string;
}

export interface Asset {
  id: string;
  format: AssetFormat;
  file_size: number | null;
  has_texture: boolean;
  download_url: string | null;
  created_at: string;
}

export interface ProjectImage {
  id: string;
  filename: string;
  width: number | null;
  height: number | null;
  thumbnail_url: string | null;
  order_index: number;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  status: JobStatus;
  progress: number;
  current_step: string | null;
  model_type: ModelType;
  category: Category;
  is_public: boolean;
  like_count: number;
  view_count: number;
  pipeline_config: Record<string, unknown>;
  prompt: string | null;
  error_message: string | null;
  image_count: number;
  created_at: string;
  updated_at: string | null;
  completed_at: string | null;
  assets: Asset[];
  images: ProjectImage[];
  thumbnail_url?: string | null;
  owner?: OwnerMini | null;
  liked_by_me?: boolean;
}

export interface GalleryItem {
  id: string;
  name: string;
  category: Category;
  like_count: number;
  view_count: number;
  created_at: string;
  thumbnail_url: string | null;
  preview_url: string | null;
  owner: OwnerMini | null;
  liked_by_me: boolean;
}

// ── Auth ─────────────────────────────────────────────────────────────
export const register = (data: { email: string; username: string; password: string }) =>
  api.post<{ access_token: string; token_type: string; user: User }>("/auth/register", data).then((r) => r.data);

export const login = (data: { identifier: string; password: string }) =>
  api.post<{ access_token: string; token_type: string; user: User }>("/auth/login", data).then((r) => r.data);

export const fetchMe = () => api.get<User>("/auth/me").then((r) => r.data);

// ── Gallery ──────────────────────────────────────────────────────────
export const listGallery = (params: { category?: Category; sort?: "recent" | "popular"; skip?: number; limit?: number } = {}) =>
  api.get<GalleryItem[]>("/gallery", { params }).then((r) => r.data);

export const listCategories = () =>
  api.get<{ key: Category; count: number }[]>("/gallery/categories").then((r) => r.data);

// ── Projects ─────────────────────────────────────────────────────────
export const createProject = (data: { name: string; description?: string; model_type: ModelType; category?: Category; prompt?: string; pipeline_config?: Record<string, unknown>; }) =>
  api.post<Project>("/projects", data).then((r) => r.data);

export const listProjects = (skip = 0, limit = 50) =>
  api.get<Project[]>("/projects", { params: { skip, limit } }).then((r) => r.data);

export const getProject = (id: string) => api.get<Project>(`/projects/${id}`).then((r) => r.data);

export const updateProject = (id: string, body: Partial<{ name: string; description: string; category: Category; is_public: boolean; prompt: string }>) =>
  api.patch<Project>(`/projects/${id}`, body).then((r) => r.data);

export const uploadImages = (projectId: string, files: File[]) => {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  return api.post(`/projects/${projectId}/images`, form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 300000,
  });
};

export const runPipeline = (projectId: string, opts: { gs_iterations?: number; refinement_time?: string; high_poly?: boolean }) =>
  api.post(`/projects/${projectId}/run`, opts).then((r) => r.data);

export const getPipelineStatus = (projectId: string) =>
  api.get(`/projects/${projectId}/status`).then((r) => r.data);

export const getDownloadUrl = (projectId: string, assetId: string) =>
  api.get(`/projects/${projectId}/assets/${assetId}/download`).then((r) => r.data);

export const deleteProject = (id: string) => api.delete(`/projects/${id}`);

export const toggleLike = (projectId: string) =>
  api.post<{ liked: boolean; like_count: number }>(`/projects/${projectId}/like`).then((r) => r.data);

/** 비공개 프로젝트의 에셋을 GLTFLoader/`<a href>` 같이 헤더 첨부 불가한 곳에서 받기 위한 URL.
 *  공개 프로젝트는 token 없이도 동작하지만, 항상 붙여둬도 무방. */
export function assetFileUrl(projectId: string, assetId: string, dl = false): string {
  const token = typeof window !== "undefined" ? localStorage.getItem("ff3d_token") : null;
  const params: string[] = [];
  if (dl) params.push("dl=1");
  if (token) params.push(`token=${encodeURIComponent(token)}`);
  const q = params.length ? `?${params.join("&")}` : "";
  return `/api/v1/projects/${projectId}/assets/${assetId}/file${q}`;
}
