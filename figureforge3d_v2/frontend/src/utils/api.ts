import axios from "axios";

export const api = axios.create({ baseURL: "/api/v1", timeout: 30000 });
api.interceptors.response.use((r) => r, (e) => Promise.reject(new Error(e.response?.data?.detail || e.message || "오류")));

export type ModelType   = "sugar" | "gof";
export type JobStatus   = "PENDING" | "RUNNING" | "SUCCESS" | "FAILED";
export type AssetFormat = "glb" | "obj" | "ply";

export interface Asset { id: string; format: AssetFormat; file_size: number | null; has_texture: boolean; download_url: string | null; created_at: string; }
export interface ProjectImage { id: string; filename: string; width: number | null; height: number | null; thumbnail_url: string | null; order_index: number; }
export interface Project { id: string; name: string; description: string | null; status: JobStatus; progress: number; current_step: string | null; model_type: ModelType; pipeline_config: Record<string, unknown>; error_message: string | null; image_count: number; created_at: string; updated_at: string | null; completed_at: string | null; assets: Asset[]; images: ProjectImage[]; thumbnail_url?: string | null; }

export const createProject = (data: { name: string; description?: string; model_type: ModelType; pipeline_config?: Record<string, unknown>; }) => api.post<Project>("/projects", data).then((r) => r.data);
export const listProjects = (skip = 0, limit = 20) => api.get<Project[]>("/projects", { params: { skip, limit } }).then((r) => r.data);
export const getProject = (id: string) => api.get<Project>(`/projects/${id}`).then((r) => r.data);
export const uploadImages = (projectId: string, files: File[]) => { const form = new FormData(); files.forEach((f) => form.append("files", f)); return api.post(`/projects/${projectId}/images`, form, { headers: { "Content-Type": "multipart/form-data" }, timeout: 300000 }); };
export const runPipeline = (projectId: string, opts: { gs_iterations?: number; refinement_time?: string; high_poly?: boolean }) => api.post(`/projects/${projectId}/run`, opts).then((r) => r.data);
export const getPipelineStatus = (projectId: string) => api.get(`/projects/${projectId}/status`).then((r) => r.data);
export const getDownloadUrl = (projectId: string, assetId: string) => api.get(`/projects/${projectId}/assets/${assetId}/download`).then((r) => r.data);
export const deleteProject = (id: string) => api.delete(`/projects/${id}`);
