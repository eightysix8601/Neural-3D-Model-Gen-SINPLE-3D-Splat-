import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import { Plus, Trash2, ChevronRight, Box, Clock, CheckCircle, XCircle, Loader, Camera } from "lucide-react";
import { listProjects, deleteProject, type Project } from "../utils/api";
import { useProjectStore } from "../stores/useProjectStore";

const SC: Record<string, { label: string; icon: any; color: string; bg: string }> = {
  PENDING: { label:"대기중", icon:Clock,        color:"text-yellow-400", bg:"bg-yellow-400/10" },
  RUNNING: { label:"처리중", icon:Loader,        color:"text-blue-400",   bg:"bg-blue-400/10"   },
  SUCCESS: { label:"완료",   icon:CheckCircle,   color:"text-emerald-400",bg:"bg-emerald-400/10" },
  FAILED:  { label:"실패",   icon:XCircle,       color:"text-red-400",    bg:"bg-red-400/10"    },
};

function ProjectCard({ project, onDelete }: { project: Project; onDelete: () => void }) {
  const navigate = useNavigate();
  const { setSelectedProject } = useProjectStore();
  const s = SC[project.status];
  const Icon = s.icon;
  return (
    <motion.div layout initial={{opacity:0,y:20}} animate={{opacity:1,y:0}} exit={{opacity:0,scale:0.95}} whileHover={{y:-2}}
      onClick={() => { setSelectedProject(project); navigate(`/view/${project.id}`); }}
      className="group bg-zinc-900 border border-zinc-800 rounded-2xl cursor-pointer overflow-hidden hover:border-violet-600/50 hover:shadow-xl hover:shadow-violet-900/20 transition-all">
      <div className="relative h-40 bg-zinc-800">
        {project.thumbnail_url
          ? <img src={project.thumbnail_url} alt={project.name} className="w-full h-full object-contain p-3 group-hover:scale-105 transition-transform duration-500" />
          : <div className="w-full h-full flex flex-col items-center justify-center gap-2"><Box className="w-10 h-10 text-zinc-700" />{project.image_count > 0 && <span className="text-xs text-zinc-600">{project.image_count}장</span>}</div>
        }
        {project.status === "RUNNING" && (
          <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center gap-2">
            <div className="w-8 h-8 rounded-full border-2 border-violet-500 border-t-transparent animate-spin" />
            <span className="text-xs text-zinc-300 font-mono">{project.progress}%</span>
          </div>
        )}
        <button onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="absolute top-2 left-2 w-7 h-7 bg-black/60 rounded-lg flex items-center justify-center text-zinc-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end justify-end p-3">
          <ChevronRight className="w-5 h-5 text-white" />
        </div>
      </div>
      <div className="p-4">
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className="font-medium text-sm text-zinc-100 truncate">{project.name}</h3>
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${s.bg} ${s.color}`}>
            <Icon className={`w-3 h-3 ${project.status==="RUNNING"?"animate-spin":""}`} />{s.label}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-600">
          <span className="px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-500">{project.model_type.toUpperCase()}</span>
          {project.image_count > 0 && <><span>·</span><span className="flex items-center gap-1"><Camera className="w-3 h-3" />{project.image_count}장</span></>}
        </div>
        {project.status === "RUNNING" && (
          <div className="mt-3 h-1 bg-zinc-800 rounded-full overflow-hidden">
            <motion.div className="h-full bg-gradient-to-r from-violet-600 to-blue-500 rounded-full"
              initial={{width:0}} animate={{width:`${project.progress}%`}} transition={{duration:0.5}} />
          </div>
        )}
      </div>
    </motion.div>
  );
}

export default function HomePage() {
  const navigate = useNavigate();
  const { projects, setProjects, removeProject } = useProjectStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => { listProjects().then(setProjects).catch((e) => toast.error(e.message)).finally(() => setLoading(false)); }, []);

  const handleDelete = async (id: string) => {
    if (!confirm("삭제하시겠습니까?")) return;
    try { await deleteProject(id); removeProject(id); toast.success("삭제 완료"); }
    catch (e: any) { toast.error(e.message); }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="sticky top-0 z-50 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center">
              <Box className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-sm bg-gradient-to-r from-violet-400 to-blue-400 bg-clip-text text-transparent">FigureForge3D</span>
          </div>
          <button onClick={() => navigate("/create")}
            className="bg-violet-600 hover:bg-violet-500 text-white font-medium px-4 py-2 rounded-xl text-sm flex items-center gap-1.5 transition-all">
            <Plus className="w-4 h-4" />새 프로젝트
          </button>
        </div>
      </header>
      <div className="border-b border-zinc-800 relative overflow-hidden">
        <div className="absolute inset-0 opacity-30" style={{background:"radial-gradient(ellipse at 50% 0%, rgba(124,58,237,0.3) 0%, transparent 70%)"}} />
        <div className="relative max-w-7xl mx-auto px-6 py-12">
          <motion.div initial={{opacity:0,y:20}} animate={{opacity:1,y:0}}>
            <h1 className="text-4xl font-bold mb-3 leading-tight">다각도 사진 →<br /><span className="bg-gradient-to-r from-violet-400 to-blue-400 bg-clip-text text-transparent">완전한 3D 모델</span></h1>
            <p className="text-zinc-400 text-base max-w-md">피규어를 여러 각도에서 촬영 → 배경 분리 → COLMAP → SuGaR / GOF 3D 재구성</p>
          </motion.div>
          <motion.div initial={{opacity:0}} animate={{opacity:1}} transition={{delay:0.3}} className="flex items-center gap-1 mt-5 flex-wrap">
            {["📷 다각도 촬영","🎭 배경 분리","📐 패턴 합성","📍 COLMAP","✨ SuGaR/GOF","🎯 3D 모델"].map((s,i) => (
              <div key={i} className="flex items-center gap-1">
                <span className="px-2.5 py-1 bg-zinc-900 border border-zinc-800 rounded-lg text-xs text-zinc-400">{s}</span>
                {i < 5 && <span className="text-zinc-700 text-xs">→</span>}
              </div>
            ))}
          </motion.div>
        </div>
      </div>
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold">내 프로젝트</h2>
          <span className="text-xs text-zinc-600 bg-zinc-900 px-2.5 py-1 rounded-full border border-zinc-800">{projects.length}개</span>
        </div>
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {[...Array(4)].map((_,i) => <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-2xl h-56 animate-pulse" />)}
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-24 space-y-4">
            <div className="w-20 h-20 rounded-3xl bg-zinc-900 flex items-center justify-center mx-auto border border-zinc-800"><Box className="w-10 h-10 text-zinc-700" /></div>
            <div><p className="text-zinc-300 font-medium">아직 프로젝트가 없습니다</p><p className="text-zinc-600 text-sm mt-1">피규어를 여러 각도에서 촬영하고 3D로 만들어보세요</p></div>
            <button onClick={() => navigate("/create")} className="bg-violet-600 hover:bg-violet-500 text-white px-5 py-2.5 rounded-xl text-sm font-medium inline-flex items-center gap-2 transition-all"><Plus className="w-4 h-4" />첫 프로젝트 시작</button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            <AnimatePresence>{projects.map((p) => <ProjectCard key={p.id} project={p} onDelete={() => handleDelete(p.id)} />)}</AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}
