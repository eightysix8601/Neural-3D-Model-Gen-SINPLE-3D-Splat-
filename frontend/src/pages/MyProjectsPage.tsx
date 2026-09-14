import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import {
  Plus, Trash2, ChevronRight, Box, Clock, CheckCircle, XCircle, Loader,
  Camera, Bone, Globe, Lock, Download,
} from "lucide-react";
import { listProjects, deleteProject, updateProject, assetFileUrl, type Project } from "../utils/api";
import { useProjectStore } from "../stores/useProjectStore";
import TopNav from "../components/TopNav";

const SC: Record<string, { label: string; icon: any; color: string; bg: string }> = {
  PENDING: { label: "대기중", icon: Clock,        color: "text-yellow-400", bg: "bg-yellow-400/10" },
  RUNNING: { label: "처리중", icon: Loader,       color: "text-blue-400",   bg: "bg-blue-400/10" },
  SUCCESS: { label: "완료",   icon: CheckCircle,  color: "text-emerald-400",bg: "bg-emerald-400/10" },
  FAILED:  { label: "실패",   icon: XCircle,      color: "text-red-400",    bg: "bg-red-400/10" },
};


function ProjectCard({
  project, onDelete, onTogglePublic,
}: {
  project: Project;
  onDelete: () => void;
  onTogglePublic: () => void;
}) {
  const navigate = useNavigate();
  const { setSelectedProject } = useProjectStore();
  const s = SC[project.status];
  const Icon = s.icon;
  const glb = project.assets?.find((a) => a.format === "glb");
  const obj = project.assets?.find((a) => a.format === "obj");
  return (
    <motion.div layout
      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }} whileHover={{ y: -2 }}
      onClick={() => {
        setSelectedProject(project);
        // 완료된 프로젝트는 상세 페이지(/p/:id), 진행 중은 파이프라인 모니터(/view/:id)
        navigate(project.status === "SUCCESS" ? `/p/${project.id}` : `/view/${project.id}`);
      }}
      className="group bg-zinc-900 border border-zinc-800 rounded-2xl cursor-pointer overflow-hidden hover:border-violet-600/50 hover:shadow-xl hover:shadow-violet-900/20 transition-all">
      <div className="relative h-44 bg-zinc-800">
        {project.thumbnail_url ? (
          <img src={project.thumbnail_url} alt={project.name}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center gap-2">
            <Box className="w-10 h-10 text-zinc-700" />
            {project.image_count > 0 && <span className="text-xs text-zinc-600">{project.image_count}장</span>}
          </div>
        )}
        {project.status === "RUNNING" && (
          <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center gap-2">
            <div className="w-8 h-8 rounded-full border-2 border-violet-500 border-t-transparent animate-spin" />
            <span className="text-xs text-zinc-300 font-mono">{project.progress}%</span>
          </div>
        )}
        <button onClick={(e) => { e.stopPropagation(); onDelete(); }} title="프로젝트 삭제"
          className="absolute top-2 left-2 flex items-center gap-1 px-2 h-7 bg-black/70 hover:bg-red-600 border border-zinc-700 hover:border-red-500 rounded-lg text-xs font-medium text-zinc-200 hover:text-white transition-all">
          <Trash2 className="w-3.5 h-3.5" />삭제
        </button>
        {project.status === "SUCCESS" && (
          <button onClick={(e) => { e.stopPropagation(); onTogglePublic(); }} title={project.is_public ? "갤러리에서 내리기" : "갤러리에 공개"}
            className={`absolute top-2 right-2 flex items-center gap-1 px-2 h-7 rounded-lg text-xs font-medium transition-all border ${
              project.is_public
                ? "bg-emerald-950/70 border-emerald-700 text-emerald-200"
                : "bg-zinc-950/70 border-zinc-700 text-zinc-300 hover:bg-violet-900"
            }`}>
            {project.is_public ? <Globe className="w-3 h-3" /> : <Lock className="w-3 h-3" />}
            {project.is_public ? "공개" : "비공개"}
          </button>
        )}
      </div>
      <div className="p-4">
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className="font-medium text-sm text-zinc-100 truncate">{project.name}</h3>
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${s.bg} ${s.color}`}>
            <Icon className={`w-3 h-3 ${project.status === "RUNNING" ? "animate-spin" : ""}`} />{s.label}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-600 mb-2">
          <span className="px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-500">{project.model_type.toUpperCase()}</span>
          {project.image_count > 0 && <><span>·</span><span className="flex items-center gap-1"><Camera className="w-3 h-3" />{project.image_count}장</span></>}
        </div>
        {project.status === "SUCCESS" && (
          <div className="flex gap-1.5 pt-1">
            {glb && (
              <a href={assetFileUrl(project.id, glb.id, true)}
                onClick={(e) => e.stopPropagation()}
                className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg text-xs bg-violet-950/50 text-violet-300 border border-violet-800/40 hover:bg-violet-900/60">
                <Download className="w-3 h-3" />GLB
              </a>
            )}
            {obj && (
              <a href={assetFileUrl(project.id, obj.id, true)}
                onClick={(e) => e.stopPropagation()}
                className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg text-xs bg-blue-950/50 text-blue-300 border border-blue-800/40 hover:bg-blue-900/60">
                <Download className="w-3 h-3" />OBJ
              </a>
            )}
          </div>
        )}
        {project.status === "RUNNING" && (
          <div className="mt-3 h-1 bg-zinc-800 rounded-full overflow-hidden">
            <motion.div className="h-full bg-gradient-to-r from-violet-600 to-blue-500 rounded-full"
              initial={{ width: 0 }} animate={{ width: `${project.progress}%` }} transition={{ duration: 0.5 }} />
          </div>
        )}
      </div>
    </motion.div>
  );
}


export default function MyProjectsPage() {
  const navigate = useNavigate();
  const { projects, setProjects, removeProject, updateProject: storeUpdate } = useProjectStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listProjects().then(setProjects)
      .catch((e: Error) => toast.error(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleDelete = async (id: string) => {
    if (!confirm("이 프로젝트를 삭제하시겠습니까?\n3D 모델·이미지·DB 기록이 모두 영구 삭제됩니다.")) return;
    const tid = toast.loading("삭제 중...");
    try {
      await deleteProject(id);
      removeProject(id);
      toast.success("삭제 완료", { id: tid });
    } catch (e: any) {
      toast.error(e.message || "삭제 실패", { id: tid });
    }
  };

  const handleTogglePublic = async (p: Project) => {
    if (p.status !== "SUCCESS") {
      toast.error("완료된 프로젝트만 공개할 수 있습니다");
      return;
    }
    const next = !p.is_public;
    const tid = toast.loading(next ? "갤러리에 공개 중..." : "비공개로 전환 중...");
    try {
      const updated = await updateProject(p.id, { is_public: next });
      storeUpdate(p.id, { is_public: updated.is_public });
      toast.success(next ? "갤러리에 공개되었습니다" : "비공개로 전환되었습니다", { id: tid });
    } catch (e: any) {
      toast.error(e.message, { id: tid });
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <TopNav />
      <div className="border-b border-zinc-800 relative overflow-hidden">
        <div className="absolute inset-0 opacity-30" style={{ background: "radial-gradient(ellipse at 50% 0%, rgba(124,58,237,0.3) 0%, transparent 70%)" }} />
        <div className="relative max-w-7xl mx-auto px-6 py-10">
          <h1 className="text-3xl font-bold mb-2">내 프로젝트</h1>
          <p className="text-zinc-400 text-sm">생성한 3D 모델 관리 · 다운로드 · 갤러리 공개</p>
        </div>
      </div>
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <span className="text-xs text-zinc-600 bg-zinc-900 px-2.5 py-1 rounded-full border border-zinc-800">{projects.length}개</span>
          </div>
          <div className="flex gap-2">
            <button onClick={() => navigate("/create?mode=tripo")}
              className="bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500 text-white font-medium px-3 py-2 rounded-xl text-sm flex items-center gap-1.5 transition-all shadow-lg shadow-violet-900/30">
              <Plus className="w-4 h-4" />스마트 메시
            </button>
            <button onClick={() => navigate("/create?mode=highres")}
              className="bg-gradient-to-r from-blue-600 to-teal-600 hover:from-blue-500 hover:to-teal-500 text-white font-medium px-3 py-2 rounded-xl text-sm flex items-center gap-1.5 transition-all shadow-lg shadow-blue-900/30">
              <Plus className="w-4 h-4" />고정밀
            </button>
          </div>
        </div>
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-2xl h-72 animate-pulse" />)}
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-24 space-y-4">
            <div className="w-20 h-20 rounded-3xl bg-zinc-900 flex items-center justify-center mx-auto border border-zinc-800">
              <Box className="w-10 h-10 text-zinc-700" />
            </div>
            <div>
              <p className="text-zinc-300 font-medium">아직 프로젝트가 없습니다</p>
              <p className="text-zinc-600 text-sm mt-1">스마트 메시 또는 고정밀 모드로 시작해보세요</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            <AnimatePresence>
              {projects.map((p) => (
                <ProjectCard key={p.id} project={p}
                  onDelete={() => handleDelete(p.id)}
                  onTogglePublic={() => handleTogglePublic(p)} />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}
