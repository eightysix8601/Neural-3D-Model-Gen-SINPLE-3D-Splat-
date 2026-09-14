/**
 * 내 프로젝트 상세 페이지 (/p/:id)
 *
 * 좌: 3D GLB 뷰어 (회전 가능)
 * 우: 이름·태그·카테고리·입력 이미지·프롬프트(메모)·다운로드 + 공개 토글
 *
 * RUNNING / PENDING 상태는 진행률 페이지(/view/:id)로 보낸다.
 */
import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import toast from "react-hot-toast";
import {
  ArrowLeft, Download, Eye, Heart, Globe, Lock, Trash2, Loader2,
  Tag as TagIcon, Calendar, Activity, FileText, Image as ImageIcon, Box,
} from "lucide-react";
import TopNav from "../components/TopNav";
import GlbViewer from "../components/viewer/GlbViewer";
import PointCloudViewer from "../components/viewer/PointCloudViewer";
import {
  getProject, deleteProject, updateProject, toggleLike, assetFileUrl,
  type Project, type Category,
} from "../utils/api";
import { useAuthStore } from "../stores/useAuthStore";

const CATEGORY_LABEL: Record<Category, string> = {
  other: "기타", character: "캐릭터", vehicle: "차량",
  furniture: "가구", animal: "동물", food: "음식",
  prop: "소품", building: "건물",
};

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);

  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyLike, setBusyLike] = useState(false);
  const [view, setView] = useState<"glb" | "ply">("glb");

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getProject(id)
      .then((p) => {
        setProject(p);
        // 아직 진행 중이면 진행률 페이지로
        if (p.status === "RUNNING" || p.status === "PENDING") {
          navigate(`/view/${p.id}`, { replace: true });
        }
      })
      .catch((e: Error) => {
        toast.error(e.message);
        navigate("/projects");
      })
      .finally(() => setLoading(false));
  }, [id, navigate]);

  const glb = useMemo(
    () => project?.assets?.find((a) => a.format === "glb"),
    [project],
  );
  const objAsset = useMemo(
    () => project?.assets?.find((a) => a.format === "obj"),
    [project],
  );
  const plyAsset = useMemo(
    () => project?.assets?.find((a) => a.format === "ply"),
    [project],
  );
  const srcImage = project?.images?.[0];

  const isOwner = !!(user && project?.owner?.id === user.id);

  const handleTogglePublic = async () => {
    if (!project) return;
    if (project.status !== "SUCCESS") {
      toast.error("완료된 프로젝트만 공개할 수 있습니다");
      return;
    }
    const next = !project.is_public;
    const tid = toast.loading(next ? "공개로 전환 중..." : "비공개로 전환 중...");
    try {
      const updated = await updateProject(project.id, { is_public: next });
      setProject((p) => p ? { ...p, is_public: updated.is_public } : p);
      toast.success(next ? "갤러리에 공개되었습니다" : "비공개로 전환되었습니다", { id: tid });
    } catch (e: any) {
      toast.error(e.message, { id: tid });
    }
  };

  const handleDelete = async () => {
    if (!project) return;
    if (!confirm("이 프로젝트를 영구 삭제하시겠습니까?")) return;
    const tid = toast.loading("삭제 중...");
    try {
      await deleteProject(project.id);
      toast.success("삭제 완료", { id: tid });
      navigate("/projects");
    } catch (e: any) {
      toast.error(e.message, { id: tid });
    }
  };

  const onLike = async () => {
    if (!project) return;
    if (!user) { toast("로그인이 필요합니다", { icon: "🔒" }); return; }
    if (busyLike) return;
    setBusyLike(true);
    try {
      const r = await toggleLike(project.id);
      setProject((p) => p ? { ...p, liked_by_me: r.liked, like_count: r.like_count } : p);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusyLike(false);
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

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <TopNav />
      <div className="max-w-7xl mx-auto px-6 py-6">
        <Link to={isOwner ? "/projects" : "/"}
          className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 mb-4">
          <ArrowLeft className="w-3.5 h-3.5" />{isOwner ? "내 프로젝트로" : "갤러리로"}
        </Link>

        <div className="grid grid-cols-1 lg:grid-cols-[1.6fr,1fr] gap-6">
          {/* ── 좌: 3D 뷰어 ───────────────────────────────────── */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            className="relative aspect-[4/3] lg:aspect-square rounded-3xl overflow-hidden bg-zinc-900 border border-zinc-800">
            {view === "glb" && glb && (
              <GlbViewer url={assetFileUrl(project.id, glb.id)} />
            )}
            {view === "ply" && plyAsset && (
              <PointCloudViewer
                url={assetFileUrl(project.id, plyAsset.id)}
                useDirectUrl
                stage="gs30k"
                label="3DGS 포인트클라우드"
              />
            )}
            {!glb && !plyAsset && (
              <div className="w-full h-full flex flex-col items-center justify-center gap-2 text-zinc-700">
                <Box className="w-12 h-12" />
                <span className="text-sm">표시 가능한 3D 파일이 없습니다</span>
              </div>
            )}

            {/* 뷰 전환 토글 (GLB/PLY 둘 다 있을 때만) */}
            {glb && plyAsset && (
              <div className="absolute top-3 left-3 z-10 flex p-0.5 bg-zinc-950/80 backdrop-blur-md border border-zinc-700 rounded-xl">
                <button
                  onClick={() => setView("glb")}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                    view === "glb" ? "bg-violet-600 text-white" : "text-zinc-400 hover:text-zinc-200"
                  }`}
                  title="메쉬 (GLB)"
                >
                  메쉬
                </button>
                <button
                  onClick={() => setView("ply")}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                    view === "ply" ? "bg-teal-600 text-white" : "text-zinc-400 hover:text-zinc-200"
                  }`}
                  title="포인트클라우드 (PLY)"
                >
                  PLY
                </button>
              </div>
            )}
          </motion.div>

          {/* ── 우: 메타데이터 ────────────────────────────────── */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
            className="space-y-4">
            {/* 헤더: 이름 + 카테고리 + 공개 토글 */}
            <div>
              <div className="flex items-start justify-between gap-2 mb-2">
                <h1 className="text-2xl font-bold leading-tight flex-1">{project.name}</h1>
                {isOwner && project.status === "SUCCESS" && (
                  <button onClick={handleTogglePublic}
                    className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all ${
                      project.is_public
                        ? "bg-emerald-950/60 border-emerald-700 text-emerald-200"
                        : "bg-zinc-900 border-zinc-700 text-zinc-300 hover:border-violet-600"
                    }`}>
                    {project.is_public ? <Globe className="w-3 h-3" /> : <Lock className="w-3 h-3" />}
                    {project.is_public ? "공개" : "비공개"}
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-violet-950/40 text-violet-300 border border-violet-800/40">
                  <TagIcon className="w-3 h-3" />{CATEGORY_LABEL[project.category] ?? project.category}
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700 uppercase">
                  {project.model_type}
                </span>
                <span className="inline-flex items-center gap-1 text-zinc-500">
                  <Calendar className="w-3 h-3" />{new Date(project.created_at).toLocaleDateString()}
                </span>
                {project.is_public && (
                  <span className="inline-flex items-center gap-1 text-zinc-500">
                    <Eye className="w-3 h-3" />{project.view_count}
                  </span>
                )}
              </div>
              {project.description && (
                <p className="mt-3 text-sm text-zinc-400 leading-relaxed">{project.description}</p>
              )}
            </div>

            {/* 좋아요 */}
            <div className="flex items-center gap-2">
              <button onClick={onLike} disabled={busyLike || !project.is_public}
                title={!project.is_public ? "공개된 프로젝트만 좋아요" : ""}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-medium border transition-all disabled:opacity-50 ${
                  project.liked_by_me
                    ? "bg-rose-500/90 border-rose-400 text-white"
                    : "bg-zinc-900 border-zinc-800 text-zinc-300 hover:border-rose-500"
                }`}>
                <Heart className={`w-4 h-4 ${project.liked_by_me ? "fill-current" : ""}`} />
                {project.like_count}
              </button>
            </div>

            {/* 입력 이미지 */}
            {srcImage && (
              <section className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
                <div className="flex items-center gap-2 text-sm font-medium text-zinc-300 mb-3">
                  <ImageIcon className="w-4 h-4 text-blue-400" />입력 이미지
                </div>
                <div className="aspect-square rounded-xl overflow-hidden bg-zinc-800 border border-zinc-800">
                  {srcImage.thumbnail_url ? (
                    <img src={srcImage.thumbnail_url} alt={srcImage.filename}
                      className="w-full h-full object-contain" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-zinc-700">
                      <ImageIcon className="w-8 h-8" />
                    </div>
                  )}
                </div>
                <p className="mt-2 text-xs text-zinc-500 truncate">{srcImage.filename}</p>
              </section>
            )}

            {/* 프롬프트 / 메모 */}
            <section className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-zinc-300 mb-2">
                <FileText className="w-4 h-4 text-fuchsia-400" />프롬프트 / 메모
              </div>
              {project.prompt ? (
                <p className="text-sm text-zinc-300 whitespace-pre-wrap leading-relaxed">{project.prompt}</p>
              ) : (
                <p className="text-sm text-zinc-600 italic">메모가 없습니다</p>
              )}
            </section>

            {/* 다운로드 */}
            <section className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 space-y-2">
              <div className="text-sm font-medium text-zinc-300 mb-1">다운로드</div>
              {glb && (
                <a href={assetFileUrl(project.id, glb.id, true)}
                  className="flex items-center justify-between p-2.5 rounded-xl bg-zinc-950 border border-zinc-800 hover:border-violet-600/50 transition-all group">
                  <div>
                    <div className="text-sm font-medium">GLB</div>
                    <div className="text-xs text-zinc-500">Three.js, Blender, Unity 호환</div>
                  </div>
                  <Download className="w-4 h-4 text-zinc-500 group-hover:text-violet-400" />
                </a>
              )}
              {objAsset && (
                <a href={assetFileUrl(project.id, objAsset.id, true)}
                  className="flex items-center justify-between p-2.5 rounded-xl bg-zinc-950 border border-zinc-800 hover:border-blue-600/50 transition-all group">
                  <div>
                    <div className="text-sm font-medium">OBJ{objAsset.has_texture ? " + 텍스처 (zip)" : ""}</div>
                    <div className="text-xs text-zinc-500">전 3D 툴 호환</div>
                  </div>
                  <Download className="w-4 h-4 text-zinc-500 group-hover:text-blue-400" />
                </a>
              )}
              {plyAsset && (
                <a href={assetFileUrl(project.id, plyAsset.id, true)}
                  className="flex items-center justify-between p-2.5 rounded-xl bg-zinc-950 border border-zinc-800 hover:border-teal-600/50 transition-all group">
                  <div>
                    <div className="text-sm font-medium">PLY</div>
                    <div className="text-xs text-zinc-500">포인트 클라우드</div>
                  </div>
                  <Download className="w-4 h-4 text-zinc-500 group-hover:text-teal-400" />
                </a>
              )}
              {!glb && !objAsset && !plyAsset && (
                <p className="text-sm text-zinc-600">아직 다운로드 가능한 파일이 없습니다</p>
              )}
            </section>

            {/* 소유자 액션 */}
            {isOwner && (
              <div className="flex gap-2">
                <button onClick={() => navigate(`/view/${project.id}`)}
                  className="flex-1 px-3 py-2 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-zinc-700 text-sm text-zinc-300 flex items-center justify-center gap-1.5">
                  <Activity className="w-4 h-4" />파이프라인 보기
                </button>
                <button onClick={handleDelete}
                  className="flex-1 px-3 py-2 rounded-xl bg-red-950/40 border border-red-900/50 hover:bg-red-900/40 text-sm text-red-300 flex items-center justify-center gap-1.5">
                  <Trash2 className="w-4 h-4" />삭제
                </button>
              </div>
            )}
          </motion.div>
        </div>
      </div>
    </div>
  );
}
