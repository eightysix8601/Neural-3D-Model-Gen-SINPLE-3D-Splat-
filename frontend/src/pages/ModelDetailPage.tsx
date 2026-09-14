import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import toast from "react-hot-toast";
import {
  Heart, Eye, Download, ArrowLeft, Loader2, Box, Calendar, User as UserIcon,
} from "lucide-react";
import TopNav from "../components/TopNav";
import GlbViewer from "../components/viewer/GlbViewer";
import { getProject, toggleLike, assetFileUrl, type Project } from "../utils/api";
import { useAuthStore } from "../stores/useAuthStore";

const CATEGORY_LABEL: Record<string, string> = {
  other: "기타", character: "캐릭터", vehicle: "차량",
  furniture: "가구", animal: "동물", food: "음식",
  prop: "소품", building: "건물",
};

export default function ModelDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [liked, setLiked] = useState(false);
  const [likeCount, setLikeCount] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getProject(id)
      .then((p) => {
        setProject(p);
        setLiked(!!p.liked_by_me);
        setLikeCount(p.like_count);
      })
      .catch((e: Error) => {
        toast.error(e.message);
        navigate("/");
      })
      .finally(() => setLoading(false));
  }, [id, navigate]);

  const onLike = async () => {
    if (!project) return;
    if (!user) {
      toast("로그인이 필요합니다", { icon: "🔒" });
      navigate("/login");
      return;
    }
    if (busy) return;
    setBusy(true);
    try {
      const r = await toggleLike(project.id);
      setLiked(r.liked);
      setLikeCount(r.like_count);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100">
        <TopNav />
        <div className="flex items-center justify-center py-32">
          <Loader2 className="w-6 h-6 text-violet-500 animate-spin" />
        </div>
      </div>
    );
  }
  if (!project) return null;

  const glb = project.assets?.find((a) => a.format === "glb");
  const obj = project.assets?.find((a) => a.format === "obj");
  const ply = project.assets?.find((a) => a.format === "ply");
  const cover = project.images?.[0]?.thumbnail_url ?? project.thumbnail_url;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <TopNav />
      <div className="max-w-6xl mx-auto px-6 py-8">
        <Link to="/" className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 mb-6">
          <ArrowLeft className="w-3.5 h-3.5" />갤러리로 돌아가기
        </Link>

        <div className="grid grid-cols-1 lg:grid-cols-[1.4fr,1fr] gap-8">
          {/* 미리보기: 라이브 3D 뷰어. iframe 으로 GLB 를 직접 띄우면 브라우저가
              model/gltf-binary 를 모르고 자동 다운로드 다이얼로그를 띄우던 문제 해결. */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            className="aspect-square rounded-3xl overflow-hidden bg-gradient-to-br from-zinc-900 to-zinc-950 border border-zinc-800 relative">
            {glb ? (
              <GlbViewer url={assetFileUrl(project.id, glb.id)} />
            ) : cover ? (
              <img src={cover} alt={project.name} className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <Box className="w-16 h-16 text-zinc-700" />
              </div>
            )}
          </motion.div>

          {/* 메타 + 액션 */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
            className="space-y-5">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs px-2 py-0.5 rounded-full bg-violet-950/40 text-violet-300 border border-violet-800/40">
                  {CATEGORY_LABEL[project.category] ?? project.category}
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700 uppercase">
                  {project.model_type}
                </span>
              </div>
              <h1 className="text-3xl font-bold mb-2">{project.name}</h1>
              {project.description && (
                <p className="text-zinc-400 text-sm leading-relaxed">{project.description}</p>
              )}
            </div>

            <div className="flex items-center gap-4 text-sm text-zinc-400">
              <span className="flex items-center gap-1.5">
                <UserIcon className="w-3.5 h-3.5" />
                <span className="text-zinc-200">@{project.owner?.username ?? "anon"}</span>
              </span>
              <span className="flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5" />
                {new Date(project.created_at).toLocaleDateString()}
              </span>
              <span className="flex items-center gap-1.5">
                <Eye className="w-3.5 h-3.5" />{project.view_count}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <button onClick={onLike} disabled={busy}
                className={`flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-medium border transition-all ${
                  liked
                    ? "bg-rose-500/90 border-rose-400 text-white shadow-lg shadow-rose-900/40"
                    : "bg-zinc-900 border-zinc-800 text-zinc-300 hover:border-rose-500"
                }`}>
                <Heart className={`w-4 h-4 ${liked ? "fill-current" : ""}`} />
                {likeCount}
              </button>
            </div>

            <div className="space-y-2 pt-2">
              <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">다운로드</div>
              {glb && (
                <a href={assetFileUrl(project.id, glb.id, true)}
                  className="flex items-center justify-between p-3 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-violet-600/50 transition-all group">
                  <div>
                    <div className="font-medium text-sm">GLB · glTF Binary</div>
                    <div className="text-xs text-zinc-500">Three.js, Blender, Unity, Unreal 호환</div>
                  </div>
                  <Download className="w-4 h-4 text-zinc-500 group-hover:text-violet-400" />
                </a>
              )}
              {obj && (
                <a href={assetFileUrl(project.id, obj.id, true)}
                  className="flex items-center justify-between p-3 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-blue-600/50 transition-all group">
                  <div>
                    <div className="font-medium text-sm">OBJ {obj.has_texture ? "+ Texture (zip)" : ""}</div>
                    <div className="text-xs text-zinc-500">전 3D 툴 호환, 텍스처 분리 파일</div>
                  </div>
                  <Download className="w-4 h-4 text-zinc-500 group-hover:text-blue-400" />
                </a>
              )}
              {ply && (
                <a href={assetFileUrl(project.id, ply.id, true)}
                  className="flex items-center justify-between p-3 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-teal-600/50 transition-all group">
                  <div>
                    <div className="font-medium text-sm">PLY · Point Cloud</div>
                    <div className="text-xs text-zinc-500">포인트 클라우드, CloudCompare 호환</div>
                  </div>
                  <Download className="w-4 h-4 text-zinc-500 group-hover:text-teal-400" />
                </a>
              )}
              {!glb && !obj && !ply && (
                <div className="text-sm text-zinc-500">아직 다운로드 가능한 파일이 없습니다</div>
              )}
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
