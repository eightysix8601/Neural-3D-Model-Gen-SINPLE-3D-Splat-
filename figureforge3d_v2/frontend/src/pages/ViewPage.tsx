/**
 * frontend/src/pages/ViewPage.tsx
 * 실시간 미리보기 포함 버전
 */
import { useEffect, useState, Suspense, useRef, lazy } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Environment, ContactShadows, Grid, Center } from "@react-three/drei";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import {
  ArrowLeft, Download, Activity, Package,
  CheckCircle2, XCircle, Loader2, Eye,
} from "lucide-react";
import { getProject, getDownloadUrl, api, type Project, type Asset } from "../utils/api";
import { useProjectStore } from "../stores/useProjectStore";
import PointCloudViewer from "../components/viewer/PointCloudViewer";

// ── 진행 단계 정의 ────────────────────────────────────────────────────────────
const STEPS = [
  { label: "카메라 포즈 추정 (COLMAP)", range: [0,  30] },
  { label: "배경 분리 (BiRefNet)",      range: [30, 55] },
  { label: "3D 학습 (3DGS)",            range: [55, 92] },
  { label: "메쉬 추출 (SuGaR/GOF)",     range: [92, 100] },
];

// ── 미리보기 타입 ─────────────────────────────────────────────────────────────
interface PreviewData {
  type: "pointcloud" | "glb" | null;
  url: string | null;
  progress: number;
  label: string;
  stage?: "colmap" | "gs7k" | "gs30k" | "mesh";
  point_size?: number;
  color?: string;
}

// ── GLB 3D 뷰어 ───────────────────────────────────────────────────────────────
function LoadingMesh() {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((_, dt) => {
    if (ref.current) {
      ref.current.rotation.y += dt * 0.8;
      ref.current.rotation.x += dt * 0.3;
    }
  });
  return (
    <mesh ref={ref}>
      <icosahedronGeometry args={[0.8, 1]} />
      <meshStandardMaterial color="#7c3aed" metalness={0.9} roughness={0.1} wireframe />
    </mesh>
  );
}

function GlbModel({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  useEffect(() => {
    scene.traverse((c) => {
      if (c instanceof THREE.Mesh) { c.castShadow = true; c.receiveShadow = true; }
    });
  }, [scene]);
  return <Center><primitive object={scene} scale={1.5} /></Center>;
}

function GlbViewer({ glbUrl }: { glbUrl: string }) {
  return (
    <Canvas shadows dpr={[1, 2]} camera={{ position: [0, 1.5, 4], fov: 42 }}
      gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }}>
      <ambientLight intensity={0.4} />
      <directionalLight position={[5, 8, 5]} intensity={1.2} castShadow shadow-mapSize={[2048, 2048]} />
      <pointLight position={[-5, 5, -5]} intensity={0.3} color="#a78bfa" />
      <Environment preset="studio" />
      <Suspense fallback={<LoadingMesh />}>
        <GlbModel url={glbUrl} />
      </Suspense>
      <ContactShadows position={[0, -1.5, 0]} opacity={0.4} scale={6} blur={3} />
      <Grid position={[0, -1.5, 0]} args={[12, 12]} cellColor="#3f3f46" sectionColor="#7c3aed" infiniteGrid />
      <OrbitControls enablePan enableZoom enableRotate autoRotate autoRotateSpeed={0.8} />
    </Canvas>
  );
}

// ── 진행률 패널 ───────────────────────────────────────────────────────────────
function ProgressPanel({ progress, step, status, error }: {
  progress: number; step: string; status: string; error?: string | null;
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 space-y-4">
      <div className="flex items-center gap-2">
        {status === "RUNNING" && <Loader2 className="w-4 h-4 text-violet-400 animate-spin" />}
        {status === "SUCCESS" && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
        {status === "FAILED"  && <XCircle className="w-4 h-4 text-red-400" />}
        <span className="text-sm font-medium">
          {status === "SUCCESS" ? "3D 모델 생성 완료 🎉" : status === "FAILED" ? "처리 실패" : "처리 중..."}
        </span>
        {status === "RUNNING" && (
          <span className="ml-auto text-xs font-mono text-violet-400">{progress}%</span>
        )}
      </div>

      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${status === "FAILED" ? "bg-red-500" : "bg-gradient-to-r from-violet-600 to-blue-500"}`}
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.5 }}
        />
      </div>

      {step && status === "RUNNING" && (
        <p className="text-xs text-zinc-500 truncate">{step}</p>
      )}

      {(status === "RUNNING" || status === "SUCCESS") && (
        <div className="space-y-1.5">
          {STEPS.map((s) => {
            const done   = progress >= s.range[1];
            const active = progress >= s.range[0] && progress < s.range[1];
            return (
              <div key={s.label} className={`flex items-center gap-2 text-xs transition-colors ${
                done ? "text-emerald-400" : active ? "text-zinc-100" : "text-zinc-700"
              }`}>
                <span className="w-4 text-center">{done ? "✓" : active ? "▶" : "○"}</span>
                <span>{s.label}</span>
                {active && <span className="ml-auto text-violet-400 animate-pulse">진행 중</span>}
              </div>
            );
          })}
        </div>
      )}

      {status === "FAILED" && error && (
        <div className="p-3 bg-red-950/30 border border-red-900/50 rounded-xl text-xs text-red-400">
          {error}
        </div>
      )}
    </div>
  );
}

// ── 에셋 패널 ─────────────────────────────────────────────────────────────────
function AssetsPanel({ assets, projectId }: { assets: Asset[]; projectId: string }) {
  const [loading, setLoading] = useState<string | null>(null);
  const META: Record<string, { icon: string; desc: string; color: string }> = {
    glb: { icon: "🎯", desc: "웹 뷰어 / Three.js",  color: "text-violet-400" },
    obj: { icon: "📐", desc: "Blender / Maya",      color: "text-blue-400"   },
    ply: { icon: "🔵", desc: "포인트클라우드",       color: "text-teal-400"   },
  };

  const download = async (asset: Asset) => {
    setLoading(asset.id);
    try {
      let url = asset.download_url;
      if (!url) {
        const d = await getDownloadUrl(projectId, asset.id);
        url = d.download_url;
      }
      const a = document.createElement("a");
      a.href = url!;
      a.download = `model.${asset.format}`;
      a.click();
      toast.success(`${asset.format.toUpperCase()} 다운로드`);
    } catch { toast.error("다운로드 실패"); }
    finally { setLoading(null); }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
      <h3 className="text-sm font-medium text-zinc-300 mb-3">결과 파일</h3>
      {assets.length === 0 ? (
        <p className="text-xs text-zinc-600 text-center py-4">아직 파일이 없습니다</p>
      ) : (
        <div className="space-y-2">
          {assets.map((asset) => {
            const meta = META[asset.format] ?? { icon: "📄", desc: "", color: "text-zinc-400" };
            return (
              <button key={asset.id} onClick={() => download(asset)}
                disabled={loading === asset.id}
                className="w-full flex items-center gap-3 p-3 bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-all group text-left">
                <span className="text-lg">{meta.icon}</span>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${meta.color}`}>{asset.format.toUpperCase()}</p>
                  <p className="text-xs text-zinc-600">{meta.desc}</p>
                  {asset.file_size && (
                    <p className="text-xs text-zinc-700">{(asset.file_size / 1024 / 1024).toFixed(1)} MB</p>
                  )}
                </div>
                {loading === asset.id
                  ? <Loader2 className="w-4 h-4 text-violet-400 animate-spin" />
                  : <Download className="w-4 h-4 text-zinc-600 group-hover:text-zinc-300 transition-colors" />
                }
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── 메인 ViewPage ─────────────────────────────────────────────────────────────
export default function ViewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { selectedProject, setSelectedProject, connectWs, liveProgress, liveStep } = useProjectStore();

  const [project, setProject] = useState<Project | null>(selectedProject);
  const [glbUrl, setGlbUrl] = useState<string | null>(null);
  const [tab, setTab] = useState<"progress" | "assets">("progress");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // 실시간 미리보기
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [prevPreviewUrl, setPrevPreviewUrl] = useState<string | null>(null);
  const previewStageRef = useRef<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 미리보기 API 호출
  const fetchPreview = async (projectId: string) => {
    try {
      const resp = await api.get(`/projects/${projectId}/preview`);
      const data: PreviewData = resp.data;

      // URL이 바뀐 경우에만 업데이트 (불필요한 리렌더 방지)
      if (data.url) {
        // stage가 바뀔 때만 뷰어 업데이트 (URL이 달라도 같은 단계면 유지)
        let stage: PreviewData["stage"] = "gs30k";
        if (data.progress < 55) stage = "colmap";
        else if (data.progress < 75) stage = "gs7k";
        else if (data.progress < 92) stage = "gs30k";
        else if (data.type === "glb") stage = "mesh";

        if (stage !== previewStageRef.current) {
          setPreview({ ...data, stage });
          setPrevPreviewUrl(data.url);
          previewStageRef.current = stage;
        }
      }
    } catch {}
  };

  useEffect(() => {
    if (!id) return;
    getProject(id).then((p) => {
      setProject(p);
      setSelectedProject(p);
      if (p.status === "RUNNING") {
        connectWs(id);
        setTab("progress");
        fetchPreview(id);
      }
      if (p.status === "SUCCESS") {
        setTab("assets");
        const glb = p.assets.find((a) => a.format === "glb");
        if (glb?.download_url) setGlbUrl(glb.download_url);
        fetchPreview(id);
      }
    }).catch(() => toast.error("프로젝트 로드 실패"));
  }, [id]);

  // 처리 중일 때 3초마다 프로젝트 상태 + 미리보기 폴링
  useEffect(() => {
    if (!id || !project) return;
    if (project.status !== "RUNNING") return;

    pollRef.current = setInterval(async () => {
      try {
        const updated = await getProject(id);
        setProject(updated);
        setSelectedProject(updated);

        if (updated.status !== "RUNNING") {
          if (pollRef.current) clearInterval(pollRef.current);
          if (updated.status === "SUCCESS") {
            setTab("assets");
            const glb = updated.assets.find((a) => a.format === "glb");
            if (glb?.download_url) setGlbUrl(glb.download_url);
          }
        }
        // 미리보기 업데이트
        await fetchPreview(id);
      } catch {}
    }, 3000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [id, project?.status]);

  if (!project) return (
    <div className="h-screen bg-zinc-950 flex items-center justify-center">
      <Loader2 className="w-6 h-6 text-violet-500 animate-spin" />
    </div>
  );

  const progress = liveProgress > 0 ? liveProgress : project.progress;
  const step = liveStep || project.current_step || "";

  // 뷰어에 표시할 내용 결정
  const showGlb = project.status === "SUCCESS" && glbUrl;
  const showPointCloud = !showGlb && preview?.type === "pointcloud" && preview.url;
  const showLoadingMesh = !showGlb && !showPointCloud;

  return (
    <div className="h-screen bg-zinc-950 flex flex-col overflow-hidden">
      {/* 탑바 */}
      <div className="h-12 border-b border-zinc-800 flex items-center px-4 gap-3 shrink-0 bg-zinc-950/80 backdrop-blur-xl">
        <button onClick={() => navigate("/")} className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors px-2 py-1 rounded hover:bg-zinc-800">
          <ArrowLeft className="w-3.5 h-3.5" />홈
        </button>
        <div className="w-px h-4 bg-zinc-800" />
        <span className="text-sm font-medium text-zinc-200 truncate">{project.name}</span>

        {/* 상태 배지 */}
        <span className={`text-xs px-2 py-0.5 rounded-full border ${
          project.status === "SUCCESS" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" :
          project.status === "RUNNING" ? "bg-violet-500/10 border-violet-500/30 text-violet-400" :
          project.status === "FAILED"  ? "bg-red-500/10 border-red-500/30 text-red-400" :
          "bg-zinc-800 border-zinc-700 text-zinc-500"
        }`}>
          {project.status === "RUNNING" ? `처리 중 ${progress}%` :
           project.status === "SUCCESS" ? "✓ 완료" :
           project.status === "FAILED"  ? "✗ 실패" : "대기"}
        </span>

        {/* 미리보기 표시 중 배지 */}
        {showPointCloud && (
          <div className="flex items-center gap-1.5 px-2 py-0.5 bg-zinc-800 rounded-full">
            <Eye className="w-3 h-3 text-zinc-400" />
            <span className="text-xs text-zinc-400">미리보기: {preview?.label}</span>
          </div>
        )}

        <button onClick={() => setSidebarOpen((v) => !v)}
          className="ml-auto text-xs text-zinc-500 hover:text-zinc-300 transition-colors px-2 py-1 rounded hover:bg-zinc-800">
          {sidebarOpen ? "패널 닫기" : "패널 열기"}
        </button>
      </div>

      {/* 본문 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 3D 뷰어 */}
        <div className="flex-1 p-2">
          <div className="w-full h-full rounded-2xl overflow-hidden bg-zinc-900 relative">

            {/* GLB 완성 뷰어 */}
            {showGlb && <GlbViewer glbUrl={glbUrl} />}

            {/* 포인트클라우드 실시간 미리보기 */}
            {showPointCloud && (
              <PointCloudViewer
                url={preview!.url!}
                color={preview!.color}
                pointSize={preview!.point_size}
                label={preview!.label}
                stage={preview!.stage}
              />
            )}

            {/* 기본 로딩 애니메이션 (미리보기 없을 때) */}
            {showLoadingMesh && (
              <Canvas camera={{ position: [0, 0, 3], fov: 42 }}>
                <ambientLight intensity={0.5} />
                <Suspense fallback={null}>
                  <LoadingMesh />
                </Suspense>
                <OrbitControls autoRotate autoRotateSpeed={2} enableZoom={false} />
              </Canvas>
            )}

            {/* 처리 중 + 미리보기 없을 때 안내 */}
            {showLoadingMesh && project.status === "RUNNING" && (
              <div className="absolute bottom-4 left-0 right-0 flex justify-center">
                <div className="bg-zinc-900/80 backdrop-blur-sm border border-zinc-800 rounded-xl px-4 py-2 flex items-center gap-2">
                  <Loader2 className="w-3.5 h-3.5 text-violet-400 animate-spin" />
                  <span className="text-xs text-zinc-400">
                    {progress < 30 ? "COLMAP 포즈 추정 완료 시 미리보기 표시" : "결과 준비 중..."}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 사이드바 */}
        <AnimatePresence>
          {sidebarOpen && (
            <motion.div
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 270, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full border-l border-zinc-800 bg-zinc-950 flex flex-col overflow-hidden shrink-0"
            >
              {/* 탭 */}
              <div className="flex border-b border-zinc-800 shrink-0">
                {[
                  { id: "progress", label: "진행", icon: Activity },
                  { id: "assets",   label: "파일", icon: Package },
                ].map((t) => {
                  const Icon = t.icon;
                  return (
                    <button key={t.id} onClick={() => setTab(t.id as any)}
                      className={`flex-1 py-3 flex flex-col items-center gap-0.5 text-xs transition-colors ${
                        tab === t.id ? "text-violet-400 border-b-2 border-violet-500" : "text-zinc-600 hover:text-zinc-400"
                      }`}>
                      <Icon className="w-4 h-4" />
                      {t.label}
                    </button>
                  );
                })}
              </div>

              <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {tab === "progress" && (
                  <ProgressPanel
                    progress={progress}
                    step={step}
                    status={project.status}
                    error={project.error_message}
                  />
                )}
                {tab === "assets" && (
                  <AssetsPanel assets={project.assets} projectId={project.id} />
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
