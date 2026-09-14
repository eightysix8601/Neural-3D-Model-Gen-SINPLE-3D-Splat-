import { useEffect, useState, Suspense } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Environment, Center } from "@react-three/drei";
import { useGLTF } from "@react-three/drei";
import { motion } from "framer-motion";
import toast from "react-hot-toast";
import {
  ArrowLeft, Bone, Wand2, Download, Loader2, Sparkles, Settings, Play,
} from "lucide-react";
import { getProject, type Project, type Asset } from "../utils/api";

function GlbModel({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  return <Center><primitive object={scene} scale={1.5} /></Center>;
}

const SKELETON_PRESETS = [
  { id: "humanoid",   label: "사람형 (Humanoid)", desc: "팔·다리·척추가 있는 인간형 캐릭터", bones: 24 },
  { id: "quadruped",  label: "동물형 (Quadruped)", desc: "네 발 동물·드래곤·몬스터",       bones: 32 },
  { id: "simple",     label: "단순 본 (Simple)",   desc: "회전·이동만 필요한 정적 메쉬",   bones: 6  },
  { id: "custom",     label: "커스텀",             desc: "직접 본 위치를 지정합니다",      bones: 0  },
];

export default function RiggingPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [glbUrl, setGlbUrl] = useState<string | null>(null);
  const [preset, setPreset] = useState("humanoid");
  const [autoBone, setAutoBone] = useState(true);
  const [symmetry, setSymmetry] = useState(true);
  const [boneCount, setBoneCount] = useState(24);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!id) return;
    getProject(id).then((p) => {
      setProject(p);
      const glb = p.assets.find((a: Asset) => a.format === "glb");
      if (glb?.download_url) setGlbUrl(glb.download_url);
    }).catch(() => toast.error("프로젝트 로드 실패"));
  }, [id]);

  const handleRig = async () => {
    if (running || done) return;
    setRunning(true);
    toast.loading("리깅 처리 중... (Beta - 시뮬레이션)", { id: "rig", duration: 3000 });
    setTimeout(() => {
      setRunning(false);
      setDone(true);
      toast.success("리깅 완료! (Beta 미리보기)", { id: "rig" });
    }, 3000);
  };

  if (!project) return (
    <div className="h-screen bg-zinc-950 flex items-center justify-center">
      <Loader2 className="w-6 h-6 text-violet-500 animate-spin" />
    </div>
  );

  return (
    <div className="h-screen bg-zinc-950 flex flex-col overflow-hidden text-zinc-100">
      <div className="h-12 border-b border-zinc-800 flex items-center px-4 gap-3 shrink-0 bg-zinc-950/80 backdrop-blur-xl">
        <button onClick={() => navigate(`/view/${id}`)}
          className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 px-2 py-1 rounded hover:bg-zinc-800 transition-colors">
          <ArrowLeft className="w-3.5 h-3.5" />뷰어로
        </button>
        <div className="w-px h-4 bg-zinc-800" />
        <Bone className="w-4 h-4 text-fuchsia-400" />
        <span className="text-sm font-medium">{project.name} • 리깅</span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-fuchsia-950/40 border border-fuchsia-800/50 text-fuchsia-300">
          Beta
        </span>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 p-2">
          <div className="w-full h-full rounded-2xl overflow-hidden bg-zinc-900 relative">
            {glbUrl ? (
              <Canvas shadows dpr={[1, 2]} camera={{ position: [0, 1.5, 4], fov: 42 }}>
                <ambientLight intensity={0.5} />
                <directionalLight position={[5, 8, 5]} intensity={1.2} />
                <Environment preset="studio" />
                <Suspense fallback={null}>
                  <GlbModel url={glbUrl} />
                </Suspense>
                <OrbitControls enablePan enableZoom enableRotate />
              </Canvas>
            ) : (
              <div className="w-full h-full flex flex-col items-center justify-center gap-3 text-zinc-500">
                <Bone className="w-10 h-10 text-zinc-700" />
                <p className="text-sm">3D 모델이 준비되지 않았습니다</p>
                <button onClick={() => navigate(`/view/${id}`)}
                  className="text-xs text-violet-400 hover:underline">뷰어로 이동</button>
              </div>
            )}

            {done && (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                className="absolute top-4 left-1/2 -translate-x-1/2 bg-emerald-950/80 border border-emerald-700/60 rounded-xl px-4 py-2 backdrop-blur">
                <span className="text-xs text-emerald-300 flex items-center gap-2">
                  <Sparkles className="w-3.5 h-3.5" /> 리깅 결과 미리보기 — Beta 데모입니다
                </span>
              </motion.div>
            )}
          </div>
        </div>

        <div className="w-80 border-l border-zinc-800 bg-zinc-950 flex flex-col overflow-hidden shrink-0">
          <div className="px-4 py-3 border-b border-zinc-800 flex items-center gap-2">
            <Settings className="w-4 h-4 text-zinc-500" />
            <span className="text-sm font-medium">리깅 설정</span>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-5">
            <div>
              <label className="text-xs font-medium text-zinc-400 mb-2 block">스켈레톤 프리셋</label>
              <div className="space-y-2">
                {SKELETON_PRESETS.map((p) => (
                  <button key={p.id} onClick={() => { setPreset(p.id); setBoneCount(p.bones); }}
                    className={`w-full text-left p-3 rounded-xl border transition-all ${
                      preset === p.id
                        ? "border-fuchsia-500 bg-fuchsia-950/20"
                        : "border-zinc-800 bg-zinc-900 hover:border-zinc-700"
                    }`}>
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-sm font-medium">{p.label}</span>
                      {p.bones > 0 && <span className="text-xs text-zinc-600">{p.bones} bones</span>}
                    </div>
                    <p className="text-xs text-zinc-500">{p.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-3">
              <label className="text-xs font-medium text-zinc-400 block">옵션</label>

              <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-800 bg-zinc-900 cursor-pointer">
                <div>
                  <p className="text-sm font-medium">자동 본 배치</p>
                  <p className="text-xs text-zinc-500">메쉬 형태를 분석해 자동으로 본을 심습니다</p>
                </div>
                <input type="checkbox" checked={autoBone} onChange={(e) => setAutoBone(e.target.checked)}
                  className="w-4 h-4 accent-fuchsia-500" />
              </label>

              <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-800 bg-zinc-900 cursor-pointer">
                <div>
                  <p className="text-sm font-medium">좌우 대칭</p>
                  <p className="text-xs text-zinc-500">좌우 본을 미러링합니다</p>
                </div>
                <input type="checkbox" checked={symmetry} onChange={(e) => setSymmetry(e.target.checked)}
                  className="w-4 h-4 accent-fuchsia-500" />
              </label>

              {preset === "custom" && (
                <div className="p-3 rounded-xl border border-zinc-800 bg-zinc-900">
                  <div className="flex justify-between mb-2">
                    <span className="text-sm font-medium">본 개수</span>
                    <span className="text-xs font-mono text-fuchsia-400">{boneCount}</span>
                  </div>
                  <input type="range" min={4} max={64} value={boneCount}
                    onChange={(e) => setBoneCount(+e.target.value)} className="w-full" />
                </div>
              )}
            </div>

            <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-900/40 text-xs text-amber-300">
              ⚠️ 리깅은 현재 <strong>Beta</strong> 단계입니다. 결과가 완벽하지 않을 수 있어요.
            </div>
          </div>

          <div className="p-4 border-t border-zinc-800 space-y-2">
            <button onClick={handleRig} disabled={running || done}
              className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-fuchsia-600 to-pink-600 hover:from-fuchsia-500 hover:to-pink-500 disabled:opacity-40 text-white font-medium py-2.5 rounded-xl transition-all">
              {running ? (
                <><Loader2 className="w-4 h-4 animate-spin" />처리 중...</>
              ) : done ? (
                <><Sparkles className="w-4 h-4" />완료됨</>
              ) : (
                <><Play className="w-4 h-4" />리깅 시작</>
              )}
            </button>
            {done && (
              <button onClick={() => toast("FBX 익스포트는 준비 중입니다", { icon: "📦" })}
                className="w-full flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-medium py-2.5 rounded-xl transition-all">
                <Download className="w-4 h-4" />FBX 다운로드
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
