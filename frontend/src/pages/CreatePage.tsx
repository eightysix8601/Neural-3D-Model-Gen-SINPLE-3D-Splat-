import { useState, useCallback, useRef, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useDropzone } from "react-dropzone";
import toast from "react-hot-toast";
import {
  ArrowLeft, ArrowRight, Upload, X, Camera, Video,
  ChevronDown, ChevronUp, Rocket, Film, Image as ImageIcon,
  Info, Zap, Layers,
} from "lucide-react";
import { api, createProject, uploadImages, runPipeline, type ModelType, type Category } from "../utils/api";
import { useProjectStore } from "../stores/useProjectStore";

const CATEGORIES: { key: Category; label: string; emoji: string }[] = [
  { key: "character", label: "캐릭터", emoji: "🧙" },
  { key: "vehicle",   label: "차량",   emoji: "🚗" },
  { key: "furniture", label: "가구",   emoji: "🪑" },
  { key: "animal",    label: "동물",   emoji: "🐶" },
  { key: "food",      label: "음식",   emoji: "🍔" },
  { key: "prop",      label: "소품",   emoji: "🎁" },
  { key: "building",  label: "건물",   emoji: "🏠" },
  { key: "other",     label: "기타",   emoji: "📦" },
];

const MODELS = [
  {
    id: "sugar" as ModelType,
    name: "SuGaR",
    tag: "추천",
    tagColor: "bg-violet-900/40 text-violet-400 border-violet-700",
    desc: "정밀한 표면 메쉬 추출",
    detailDesc: "피규어의 표면을 삼각형 메쉬로 정밀하게 재구성해요. 색상 텍스처가 포함되어 Blender 등 3D 툴에서 바로 사용 가능해요.",
    time: "30~40분",
    q: 4, s: 3,
    badge: "텍스처 포함",
  },
  {
    id: "gof" as ModelType,
    name: "GOF",
    tag: "고품질",
    tagColor: "bg-teal-900/40 text-teal-400 border-teal-700",
    desc: "곡면 디테일 최고 품질",
    detailDesc: "둥근 곡면이 많은 피규어에 특화된 모델이에요. 표면 디테일이 SuGaR보다 뛰어나지만 시간이 조금 더 걸려요.",
    time: "20~30분",
    q: 5, s: 4,
    badge: "최고 품질",
  },
  {
    id: "twodgs" as ModelType,
    name: "2DGS",
    tag: "신규",
    tagColor: "bg-amber-900/40 text-amber-400 border-amber-700",
    desc: "표면 정렬 가우시안 + TSDF 메쉬",
    detailDesc: "가우시안을 디스크 형태로 표면에 정렬해 SuGaR보다 깔끔한 메쉬를 뽑아요. 매끈한 피규어·소품에 특히 강하고 텍스처가 포함돼요.",
    time: "20~30분",
    q: 5, s: 4,
    badge: "텍스처 포함",
  },
  {
    id: "nerf" as ModelType,
    name: "NeRF",
    tag: "신규",
    tagColor: "bg-blue-900/40 text-blue-400 border-blue-700",
    desc: "nerfstudio nerfacto 기반",
    detailDesc: "신경 방사장(NeRF)으로 장면을 학습한 뒤 Poisson 방식으로 메쉬를 추출해요. 반사·투명이 많은 피규어에 강하고 텍스처가 포함돼요.",
    time: "20~35분",
    q: 4, s: 3,
    badge: "텍스처 포함",
  },
];

function Bar({ v, c }: { v: number; c: string }) {
  return (
    <div className="flex gap-1">
      {[...Array(5)].map((_, i) => (
        <div key={i} className={`w-5 h-1.5 rounded-full ${i < v ? c : "bg-zinc-700"}`} />
      ))}
    </div>
  );
}

type InputMode = "images" | "video";

interface VideoInfo {
  duration: number; fps: number; width: number; height: number;
  estimated_frames_3fps: number; recommended_target: number;
}

export default function CreatePage() {
  const navigate = useNavigate();
  const [sp] = useSearchParams();
  const mode = sp.get("mode") === "tripo" ? "tripo" : "highres";
  const { addProject, setSelectedProject, connectWs } = useProjectStore();
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [showAdv, setShowAdv] = useState(false);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [category, setCategory] = useState<Category>("character");
  const [prompt, setPrompt] = useState("");
  const [useTexture, setUseTexture] = useState(true);
  const [modelType, setModelType] = useState<ModelType>(mode === "tripo" ? "tripo" : "sugar");
  useEffect(() => {
    if (mode === "tripo") setModelType("tripo");
  }, [mode]);
  const [gsIter, setGsIter] = useState(30000);
  const [refTime, setRefTime] = useState("short");
  const [inputMode, setInputMode] = useState<InputMode>("images");
  const [files, setFiles] = useState<File[]>([]);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null);
  const [targetFrames, setTargetFrames] = useState(60);
  const [extractionFps, setExtractionFps] = useState(3.0);
  const [analyzingVideo, setAnalyzingVideo] = useState(false);
  const [videoUploadProgress, setVideoUploadProgress] = useState(0);

  const onDrop = useCallback((accepted: File[]) => setFiles((p) => [...p, ...accepted].slice(0, 200)), []);
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { "image/*": [".jpg", ".jpeg", ".png", ".webp"] }, multiple: true
  });

  const videoInputRef = useRef<HTMLInputElement>(null);
  const handleVideoSelect = async (file: File) => {
    setVideoFile(file);
    setVideoInfo(null);
    setAnalyzingVideo(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await api.post(
        "/projects/00000000-0000-0000-0000-000000000000/analyze-video", form,
        { headers: { "Content-Type": "multipart/form-data" }, timeout: 30000 }
      ).catch(() => null);
      if (resp?.data) {
        setVideoInfo(resp.data);
        setTargetFrames(resp.data.recommended_target ?? 60);
        toast.success(`동영상 분석 완료: ${resp.data.duration}초`);
      } else {
        setVideoInfo({ duration: 0, fps: 30, width: 0, height: 0, estimated_frames_3fps: 0, recommended_target: 60 });
      }
    } catch {
      setVideoInfo({ duration: 0, fps: 30, width: 0, height: 0, estimated_frames_3fps: 0, recommended_target: 60 });
    } finally {
      setAnalyzingVideo(false);
    }
  };

  const minImages = mode === "tripo" ? 1 : 3;
  const imgQuality = files.length === 0 ? "none" : files.length < 20 ? "low" : files.length < 40 ? "good" : "excellent";
  const QC = {
    none:      { color: "text-zinc-600",    label: "이미지 없음",               bar: "bg-zinc-700"    },
    low:       { color: "text-yellow-400",  label: `${files.length}장 (20장 이상 권장)`, bar: "bg-yellow-500" },
    good:      { color: "text-blue-400",    label: "좋음",                       bar: "bg-blue-500"    },
    excellent: { color: "text-emerald-400", label: "최고 품질",                   bar: "bg-emerald-500" },
  };
  const qc = QC[imgQuality];
  const canProceed = inputMode === "images" ? files.length >= minImages : videoFile !== null;

  // 학습 스텝 설명
  const gsIterDesc =
    gsIter <= 10000 ? "⚡ 빠르지만 품질이 낮아요. 테스트용으로 적합해요." :
    gsIter <= 20000 ? "🔵 기본보다 빠르고 어느 정도 품질이 나와요." :
    gsIter <= 30000 ? "✅ 권장 설정이에요. 품질과 속도의 균형이 좋아요." :
    gsIter <= 50000 ? "⭐ 고품질이지만 시간이 더 걸려요." :
    "🏆 최고 품질이지만 1시간 이상 걸릴 수 있어요.";

  const refTimeDesc = {
    short:  "약 2,000번 정제 • 10~15분 추가 • 빠른 결과물 확인용",
    medium: "약 7,000번 정제 • 30~40분 추가 • 일반적인 품질",
    long:   "약 15,000번 정제 • 1시간+ 추가 • 최고 품질의 메쉬",
  };

  const handleSubmit = async () => {
    if (!name.trim()) { toast.error("프로젝트 이름 입력"); return; }
    if (!canProceed) {
      toast.error(inputMode === "images" ? `최소 ${minImages}장 이상 업로드하세요` : "동영상 파일을 선택하세요");
      return;
    }
    if (mode === "highres" && inputMode === "images" && files.length < 20) {
      if (!confirm(`${files.length}장만 업로드됐어요. 20장 이상 권장합니다. 계속할까요?`)) return;
    }
    setSubmitting(true);
    const tid = toast.loading("프로젝트 생성 중...");
    try {
      const project = await createProject({
        name: name.trim(), description: desc.trim() || undefined,
        model_type: modelType,
        category,
        prompt: prompt.trim() || undefined,
        pipeline_config: mode === "tripo"
          ? { num_inference_steps: 50, guidance_scale: 7.0, use_texture: useTexture }
          : { gs_iterations: gsIter, refinement_time: refTime },
      });
      if (inputMode === "images") {
        toast.loading(`이미지 업로드 중... (${files.length}장)`, { id: tid });
        await uploadImages(project.id, files);
      } else {
        toast.loading("동영상 업로드 및 프레임 추출 중...", { id: tid });
        const form = new FormData();
        form.append("file", videoFile!);
        form.append("target_frames", String(targetFrames));
        form.append("extraction_fps", String(extractionFps));
        form.append("blur_threshold", "80.0");
        await api.post(`/projects/${project.id}/video`, form, {
          headers: { "Content-Type": "multipart/form-data" }, timeout: 600000,
          onUploadProgress: (e) => { if (e.total) setVideoUploadProgress(Math.round(e.loaded / e.total * 50)); },
        });
        setVideoUploadProgress(100);
      }
      toast.loading("파이프라인 시작 중...", { id: tid });
      await runPipeline(project.id, { gs_iterations: gsIter, refinement_time: refTime });
      toast.success("파이프라인 시작!", { id: tid });
      addProject(project); setSelectedProject(project); connectWs(project.id);
      navigate(`/view/${project.id}`);
    } catch (e: any) {
      toast.error(e.message, { id: tid });
    } finally {
      setSubmitting(false); setVideoUploadProgress(0);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-2xl mx-auto px-6 h-14 flex items-center gap-4">
          <button onClick={() => navigate("/")} className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 px-3 py-1.5 rounded-lg hover:bg-zinc-800 transition-colors">
            <ArrowLeft className="w-3.5 h-3.5" />홈
          </button>
          <div className="w-px h-4 bg-zinc-800" />
          <span className="text-sm font-medium text-zinc-300">새 프로젝트</span>
          <div className="ml-auto flex items-center gap-2">
            {[1, 2].map((n) => (
              <div key={n} className="flex items-center gap-1">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium transition-all ${step + 1 === n ? "bg-violet-600 text-white" : step + 1 > n ? "bg-emerald-600 text-white" : "bg-zinc-800 text-zinc-500"}`}>
                  {step + 1 > n ? "✓" : n}
                </div>
                {n < 2 && <div className={`w-6 h-px ${step >= n ? "bg-violet-600" : "bg-zinc-800"}`} />}
              </div>
            ))}
          </div>
        </div>
      </header>

      <div className="max-w-2xl mx-auto px-6 py-8">
        <AnimatePresence mode="wait">

          {/* ── Step 0: 프로젝트 설정 ── */}
          {step === 0 && (
            <motion.div key="s0" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }} className="space-y-6">
              <div className={`p-4 rounded-2xl border ${
                mode === "tripo"
                  ? "border-violet-700/40 bg-gradient-to-r from-violet-950/40 to-zinc-900"
                  : "border-blue-700/30 bg-gradient-to-r from-blue-950/30 to-zinc-900"
              }`}>
                <div className="flex items-center gap-3">
                  {mode === "tripo"
                    ? <Zap className="w-5 h-5 text-violet-400" />
                    : <Layers className="w-5 h-5 text-blue-400" />}
                  <div className="flex-1">
                    <div className="font-semibold text-sm">
                      {mode === "tripo" ? "스마트 메시 생성" : "고정밀 모델 생성"}
                    </div>
                    <div className="text-xs text-zinc-400">
                      {mode === "tripo"
                        ? "이미지 1장으로 1~3분 안에 메쉬 생성 (TripoSG/TripoSF)"
                        : "다각도 사진/영상으로 COLMAP + SuGaR/GOF/2DGS/NeRF, 텍스처 포함"}
                    </div>
                  </div>
                  <button onClick={() => navigate(`/create?mode=${mode === "tripo" ? "highres" : "tripo"}`)}
                    className="text-xs px-2.5 py-1 rounded-md bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300">
                    모드 전환
                  </button>
                </div>
              </div>

              <div>
                <h1 className="text-2xl font-bold mb-1">프로젝트 설정</h1>
                <p className="text-zinc-500 text-sm">
                  {mode === "tripo" ? "이름과 카테고리를 정해주세요" : "이름과 3D 재구성 방식을 선택하세요"}
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">프로젝트 이름 *</label>
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 루피 피규어 3D"
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-xl px-4 py-3 text-white placeholder-zinc-600 focus:outline-none focus:border-violet-500 transition-all" />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">카테고리</label>
                <div className="grid grid-cols-4 gap-2">
                  {CATEGORIES.map((c) => (
                    <button key={c.key} onClick={() => setCategory(c.key)}
                      className={`px-2 py-2 rounded-xl border text-sm transition-all flex flex-col items-center gap-1 ${
                        category === c.key
                          ? "border-violet-500 bg-violet-950/30 text-white"
                          : "border-zinc-800 bg-zinc-900 text-zinc-300 hover:border-zinc-700"
                      }`}>
                      <span className="text-lg">{c.emoji}</span>
                      <span className="text-xs">{c.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* 프롬프트 / 메모 — 스마트 메시 모드에서만 제공 (메타데이터). 생성 자체에는 영향 X. */}
              {mode === "tripo" && (
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-1">
                    프롬프트 / 메모 <span className="text-xs text-zinc-600">(선택)</span>
                  </label>
                  <p className="text-xs text-zinc-600 mb-2">
                    모델 설명·키워드·제작 메모. 검색·정리에 쓰입니다.
                    <span className="text-zinc-500"> (현재 TripoSG 표준 모델은 이미지만 사용 — 메타로 저장)</span>
                  </p>
                  <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)}
                    rows={3} maxLength={2000}
                    placeholder="예: 검정 마스크 쓴 닌자 캐릭터, 발차기 포즈"
                    className="w-full bg-zinc-900 border border-zinc-700 rounded-xl px-4 py-3 text-white placeholder-zinc-600 focus:outline-none focus:border-violet-500 transition-all resize-none" />
                </div>
              )}

              {/* 텍스쳐 자동 적용 토글 — 스마트 메시 모드 한정 */}
              {mode === "tripo" && (
                <label className="flex items-center gap-3 p-3 bg-zinc-900 border border-zinc-800 rounded-xl cursor-pointer hover:border-zinc-700 transition-all">
                  <input type="checkbox" checked={useTexture}
                    onChange={(e) => setUseTexture(e.target.checked)}
                    className="w-4 h-4 accent-violet-600 cursor-pointer" />
                  <div className="flex-1">
                    <div className="text-sm font-medium text-zinc-200">텍스쳐 자동 적용</div>
                    <div className="text-xs text-zinc-500 mt-0.5">
                      입력 이미지를 정면 방향으로 메쉬에 투영 (정면 또렷, 뒷면 회색)
                    </div>
                  </div>
                </label>
              )}

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">설명 (선택)</label>
                <textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="피규어 이름, 크기 등 메모..." rows={2}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-xl px-4 py-3 text-white placeholder-zinc-600 focus:outline-none focus:border-violet-500 transition-all resize-none" />
              </div>

              {/* 모델 선택 — 고정밀 모드에서만 노출 */}
              {mode === "highres" && (
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">3D 재구성 방식 선택</label>
                <p className="text-xs text-zinc-600 mb-3">어떤 방식으로 3D 모델을 만들지 선택하세요</p>
                <div className="space-y-3">
                  {MODELS.map((m) => (
                    <button key={m.id} onClick={() => setModelType(m.id)}
                      className={`w-full text-left p-4 rounded-2xl border transition-all ${modelType === m.id ? "border-violet-500 bg-violet-950/30" : "border-zinc-700 bg-zinc-900 hover:border-zinc-600"}`}>
                      <div className="flex items-start gap-3">
                        <div className={`mt-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 ${modelType === m.id ? "border-violet-500" : "border-zinc-600"}`}>
                          {modelType === m.id && <div className="w-2 h-2 rounded-full bg-violet-500" />}
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <span className="font-semibold text-sm">{m.name}</span>
                            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${m.tagColor}`}>{m.tag}</span>
                            <span className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700">{m.badge}</span>
                            <span className="text-xs text-zinc-600 ml-auto">⏱ {m.time}</span>
                          </div>
                          <p className="text-xs font-medium text-zinc-300 mb-1">{m.desc}</p>
                          <p className="text-xs text-zinc-500 mb-2">{m.detailDesc}</p>
                          <div className="grid grid-cols-2 gap-2">
                            <div><span className="text-xs text-zinc-600">품질</span><Bar v={m.q} c="bg-violet-500" /></div>
                            <div><span className="text-xs text-zinc-600">속도</span><Bar v={m.s} c="bg-emerald-500" /></div>
                          </div>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              )}

              {/* 고급 설정 — 고정밀 모드에서만 */}
              {mode === "highres" && (
              <div className="border border-zinc-800 rounded-2xl overflow-hidden">
                <button onClick={() => setShowAdv((v) => !v)}
                  className="w-full flex items-center justify-between px-4 py-3 text-sm text-zinc-400 hover:text-zinc-300 transition-colors">
                  <div className="flex items-center gap-2">
                    <span>고급 설정</span>
                    <span className="text-xs text-zinc-600">(선택사항)</span>
                  </div>
                  {showAdv ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
                <AnimatePresence>
                  {showAdv && (
                    <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden">
                      <div className="px-4 pb-4 space-y-5 border-t border-zinc-800 pt-4">

                        {/* 학습 스텝 */}
                        <div>
                          <div className="flex justify-between mb-1">
                            <label className="text-sm font-medium text-zinc-300">3D 학습 정밀도</label>
                            <span className="text-xs font-mono text-violet-400">{gsIter.toLocaleString()} 스텝</span>
                          </div>
                          <input type="range" min={10000} max={60000} step={5000} value={gsIter}
                            onChange={(e) => setGsIter(+e.target.value)} className="w-full mb-2" />
                          <div className="flex justify-between text-xs text-zinc-600 mb-2">
                            <span>빠름 (10k)</span>
                            <span className="text-violet-400">권장 (30k)</span>
                            <span>최고품질 (60k)</span>
                          </div>
                          <div className="bg-zinc-800/50 rounded-xl px-3 py-2 flex items-start gap-2">
                            <Info className="w-3.5 h-3.5 text-zinc-500 mt-0.5 shrink-0" />
                            <p className="text-xs text-zinc-400">{gsIterDesc}</p>
                          </div>
                        </div>

                        {/* 정제 시간 (SuGaR만) */}
                        {modelType === "sugar" && (
                          <div>
                            <label className="text-sm font-medium text-zinc-300 block mb-1">메쉬 정제 수준</label>
                            <p className="text-xs text-zinc-600 mb-2">3D 형태를 얼마나 세밀하게 다듬을지 결정해요</p>
                            <div className="flex gap-2 mb-2">
                              {(["short", "medium", "long"] as const).map((t) => (
                                <button key={t} onClick={() => setRefTime(t)}
                                  className={`flex-1 py-2 rounded-xl text-xs font-medium transition-all ${refTime === t ? "bg-violet-600 text-white" : "bg-zinc-800 text-zinc-500 hover:text-zinc-300"}`}>
                                  {t === "short" ? "빠름" : t === "medium" ? "보통" : "정밀"}
                                </button>
                              ))}
                            </div>
                            <div className="bg-zinc-800/50 rounded-xl px-3 py-2 flex items-start gap-2">
                              <Info className="w-3.5 h-3.5 text-zinc-500 mt-0.5 shrink-0" />
                              <p className="text-xs text-zinc-400">{refTimeDesc[refTime as keyof typeof refTimeDesc]}</p>
                            </div>
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              )}

              <button onClick={() => { if (!name.trim()) { toast.error("이름 입력"); return; } setStep(1); }}
                className="w-full bg-violet-600 hover:bg-violet-500 text-white font-medium px-5 py-3 rounded-xl transition-all flex items-center justify-center gap-2">
                다음: {mode === "tripo" ? "이미지 1장 업로드" : "사진/동영상 업로드"} <ArrowRight className="w-4 h-4" />
              </button>
            </motion.div>
          )}

          {/* ── Step 1: 업로드 ── */}
          {step === 1 && (
            <motion.div key="s1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="space-y-5">
              <div>
                <h1 className="text-2xl font-bold mb-1">
                  {mode === "tripo" ? "이미지 1장 업로드" : "사진 또는 동영상 업로드"}
                </h1>
                <p className="text-zinc-500 text-sm">
                  {mode === "tripo"
                    ? "정면이 잘 보이는 1장의 이미지를 올리세요. 단색 배경일수록 좋습니다."
                    : "피규어를 여러 각도에서 촬영한 사진 또는 360° 동영상을 올려주세요"}
                </p>
              </div>

              {/* 입력 방식 선택 — 고정밀에서만 동영상 선택지 제공 */}
              {mode === "highres" && (
              <div className="flex gap-2">
                {[
                  { id: "images" as InputMode, icon: ImageIcon, label: "사진 여러 장", desc: "20~60장 직접 촬영" },
                  { id: "video"  as InputMode, icon: Film,      label: "동영상",      desc: "360° 회전 영상" },
                ].map((m) => {
                  const Icon = m.icon;
                  return (
                    <button key={m.id} onClick={() => setInputMode(m.id)}
                      className={`flex-1 flex flex-col items-center gap-2 p-4 rounded-2xl border transition-all ${inputMode === m.id ? "border-violet-500 bg-violet-950/30" : "border-zinc-700 bg-zinc-900 hover:border-zinc-600"}`}>
                      <Icon className={`w-6 h-6 ${inputMode === m.id ? "text-violet-400" : "text-zinc-500"}`} />
                      <span className={`text-sm font-medium ${inputMode === m.id ? "text-white" : "text-zinc-400"}`}>{m.label}</span>
                      <span className="text-xs text-zinc-600">{m.desc}</span>
                    </button>
                  );
                })}
              </div>
              )}

              {/* 이미지 모드 */}
              {inputMode === "images" && (
                <>
                  <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-4 space-y-3">
                    <div className="flex items-center gap-2"><Camera className="w-4 h-4 text-blue-400" /><span className="text-sm font-medium text-zinc-200">촬영 가이드</span></div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      {[
                        { l: "수평 360°", c: "36장", d: "10도 간격", cl: "bg-blue-900/40 border-blue-700" },
                        { l: "위 45°",    c: "12장", d: "30도 간격", cl: "bg-purple-900/40 border-purple-700" },
                        { l: "아래 45°",  c: "12장", d: "30도 간격", cl: "bg-teal-900/40 border-teal-700" },
                      ].map((g) => (
                        <div key={g.l} className={`${g.cl} border rounded-xl p-2.5 text-center`}>
                          <p className="font-bold text-white text-sm">{g.c}</p>
                          <p className="text-zinc-300">{g.l}</p>
                          <p className="text-zinc-500">{g.d}</p>
                        </div>
                      ))}
                    </div>
                    <div className="flex flex-col gap-1 text-xs text-zinc-500">
                      <span>✅ 흰 배경 또는 단색 배경 권장</span>
                      <span>✅ 최소 20장, 권장 60장</span>
                    </div>
                  </div>

                  <div {...getRootProps()} className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all ${isDragActive ? "border-violet-500 bg-violet-950/20" : "border-zinc-700 hover:border-violet-600/50 hover:bg-zinc-900"}`}>
                    <input {...getInputProps()} />
                    <div className="flex flex-col items-center gap-3">
                      <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ${isDragActive ? "bg-violet-600" : "bg-zinc-800"}`}>
                        <Upload className={`w-6 h-6 ${isDragActive ? "text-white" : "text-zinc-500"}`} />
                      </div>
                      <div>
                        <p className={`font-medium text-sm ${isDragActive ? "text-violet-400" : "text-zinc-300"}`}>
                          {isDragActive ? "놓으세요!" : "클릭하거나 드래그해서 업로드"}
                        </p>
                        <p className="text-xs text-zinc-600 mt-1">JPG, PNG, WEBP · 최대 200장{files.length > 0 && ` · 현재 ${files.length}장`}</p>
                      </div>
                    </div>
                  </div>

                  {files.length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs"><span className="text-zinc-500">예상 품질</span><span className={qc.color}>{qc.label}</span></div>
                      <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                        <motion.div className={`h-full rounded-full ${qc.bar}`} initial={{ width: 0 }} animate={{ width: `${Math.min((files.length / 60) * 100, 100)}%` }} transition={{ duration: 0.5 }} />
                      </div>
                      <div className="flex justify-between text-xs text-zinc-600"><span>0</span><span className="text-yellow-600">20</span><span className="text-blue-600">40</span><span className="text-emerald-600">60</span></div>
                    </div>
                  )}

                  {files.length > 0 && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-zinc-500">{files.length}장 선택됨</span>
                        <button onClick={() => setFiles([])} className="text-xs text-red-500 hover:text-red-400">전체 삭제</button>
                      </div>
                      <div className="grid grid-cols-6 gap-1.5 max-h-48 overflow-y-auto pr-1">
                        {files.map((f, i) => (
                          <div key={f.name + i} className="relative group aspect-square">
                            <img src={URL.createObjectURL(f)} alt="" className="w-full h-full object-cover rounded-lg" />
                            <button onClick={() => setFiles((fl) => fl.filter((_, idx) => idx !== i))}
                              className="absolute inset-0 bg-black/60 rounded-lg opacity-0 group-hover:opacity-100 flex items-center justify-center">
                              <X className="w-3 h-3 text-white" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* 동영상 모드 */}
              {inputMode === "video" && (
                <>
                  <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-4 space-y-3">
                    <div className="flex items-center gap-2"><Video className="w-4 h-4 text-teal-400" /><span className="text-sm font-medium text-zinc-200">동영상 촬영 가이드</span></div>
                    <div className="flex flex-col gap-1.5 text-xs text-zinc-400">
                      <span>✅ 피규어 주위를 천천히 한 바퀴 돌며 촬영</span>
                      <span>✅ 조명이 균일하고 배경이 단색인 환경 권장</span>
                      <span>✅ 흔들림 없이 천천히 10~30초 촬영</span>
                      <span>⚠️ MP4, MOV, AVI 형식 지원</span>
                    </div>
                  </div>

                  <div onClick={() => videoInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all ${videoFile ? "border-emerald-600/50 bg-emerald-950/10" : "border-zinc-700 hover:border-teal-600/50 hover:bg-zinc-900"}`}>
                    <input ref={videoInputRef} type="file" accept="video/*" className="hidden"
                      onChange={(e) => { if (e.target.files?.[0]) handleVideoSelect(e.target.files[0]); }} />
                    <div className="flex flex-col items-center gap-3">
                      <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ${videoFile ? "bg-emerald-700" : "bg-zinc-800"}`}>
                        <Film className={`w-6 h-6 ${videoFile ? "text-white" : "text-zinc-500"}`} />
                      </div>
                      {videoFile ? (
                        <div><p className="font-medium text-sm text-emerald-400">{videoFile.name}</p><p className="text-xs text-zinc-500 mt-1">{(videoFile.size / 1024 / 1024).toFixed(1)} MB</p></div>
                      ) : (
                        <div><p className="font-medium text-sm text-zinc-300">클릭해서 동영상 선택</p><p className="text-xs text-zinc-600 mt-1">MP4, MOV, AVI, WebM</p></div>
                      )}
                    </div>
                  </div>

                  {analyzingVideo && <div className="flex items-center gap-2 text-sm text-zinc-400"><div className="w-4 h-4 rounded-full border-2 border-teal-500 border-t-transparent animate-spin" />동영상 분석 중...</div>}

                  {videoInfo && !analyzingVideo && (
                    <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-4 space-y-3">
                      <span className="text-sm font-medium text-zinc-300">동영상 정보</span>
                      <div className="grid grid-cols-3 gap-2 text-xs">
                        {[
                          { label: "길이", value: videoInfo.duration > 0 ? `${videoInfo.duration}초` : "알 수 없음" },
                          { label: "해상도", value: videoInfo.width > 0 ? `${videoInfo.width}×${videoInfo.height}` : "알 수 없음" },
                          { label: "FPS", value: videoInfo.fps > 0 ? `${videoInfo.fps}` : "알 수 없음" },
                        ].map((info) => (
                          <div key={info.label} className="bg-zinc-800 rounded-xl p-2.5 text-center">
                            <p className="text-zinc-400">{info.label}</p>
                            <p className="font-medium text-white mt-0.5">{info.value}</p>
                          </div>
                        ))}
                      </div>
                      <div className="space-y-3 pt-1">
                        <div>
                          <div className="flex justify-between mb-1"><label className="text-xs text-zinc-400">추출할 프레임 수</label><span className="text-xs font-mono text-teal-400">{targetFrames}장</span></div>
                          <input type="range" min={20} max={120} step={5} value={targetFrames} onChange={(e) => setTargetFrames(+e.target.value)} className="w-full" />
                          <div className="flex justify-between text-xs text-zinc-600 mt-1"><span>20 (최소)</span><span className="text-blue-600">60 (권장)</span><span>120</span></div>
                        </div>
                        <div>
                          <label className="text-xs text-zinc-400 block mb-2">초당 추출 FPS</label>
                          <div className="flex gap-2">
                            {[1.0, 2.0, 3.0, 5.0].map((f) => (
                              <button key={f} onClick={() => setExtractionFps(f)}
                                className={`flex-1 py-1.5 rounded-lg text-xs transition-all ${extractionFps === f ? "bg-teal-600 text-white" : "bg-zinc-800 text-zinc-500 hover:text-zinc-300"}`}>
                                {f}fps
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {submitting && videoUploadProgress > 0 && (
                    <div className="space-y-2">
                      <div className="flex justify-between text-xs text-zinc-400">
                        <span>{videoUploadProgress < 50 ? "동영상 업로드 중..." : "프레임 추출 중..."}</span>
                        <span>{videoUploadProgress}%</span>
                      </div>
                      <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                        <motion.div className="h-full bg-gradient-to-r from-teal-600 to-blue-500 rounded-full"
                          animate={{ width: `${videoUploadProgress}%` }} transition={{ duration: 0.3 }} />
                      </div>
                    </div>
                  )}
                </>
              )}

              <div className="flex gap-3">
                <button onClick={() => setStep(0)} className="flex items-center gap-1.5 px-4 py-2.5 text-sm text-zinc-400 hover:text-zinc-300 hover:bg-zinc-800 rounded-xl border border-zinc-700 transition-all">
                  <ArrowLeft className="w-4 h-4" />이전
                </button>
                <button onClick={handleSubmit} disabled={submitting || !canProceed}
                  className="flex-1 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium px-5 py-2.5 rounded-xl transition-all flex items-center justify-center gap-2">
                  {submitting
                    ? <><div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />처리 중...</>
                    : <><Rocket className="w-4 h-4" />3D 생성 시작{inputMode === "images" ? ` (${files.length}장)` : videoFile ? ` (${videoFile.name.slice(0, 15)}...)` : ""}</>
                  }
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
