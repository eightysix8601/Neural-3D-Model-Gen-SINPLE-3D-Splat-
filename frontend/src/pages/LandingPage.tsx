import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Sparkles, Zap, Box, Camera, Wand2, Bone, Download, Layers,
  ArrowRight, Check, Star, Cpu, Gauge, Image as ImageIcon,
} from "lucide-react";
import TopNav from "../components/TopNav";

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 overflow-x-hidden">
      <TopNav variant="transparent" />

      {/* ── HERO ─────────────────────────────────────────────── */}
      <section className="relative pt-20 pb-32 px-6">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-gradient-radial from-violet-600/30 via-blue-600/10 to-transparent blur-3xl" />
          <div className="absolute top-1/3 right-0 w-[400px] h-[400px] bg-gradient-radial from-blue-600/20 to-transparent blur-3xl" />
        </div>

        <div className="relative max-w-5xl mx-auto text-center">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-violet-700/40 bg-violet-950/30 text-xs text-violet-300 mb-6">
            <Sparkles className="w-3.5 h-3.5" />
            사진 한 묶음으로 완성된 3D 피규어
          </motion.div>

          <motion.h1 initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            className="text-5xl md:text-7xl font-bold leading-tight tracking-tight mb-6">
            촬영만 하면 끝.<br />
            <span className="bg-gradient-to-r from-violet-400 via-blue-400 to-teal-400 bg-clip-text text-transparent">
              완전한 3D 모델
            </span>
            이 됩니다.
          </motion.h1>

          <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
            className="text-lg md:text-xl text-zinc-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            BiRefNet · COLMAP · SuGaR / GOF 파이프라인을 한 번의 클릭으로.<br className="hidden md:block" />
            프린팅·게임·애니메이션에 그대로 사용 가능한 메쉬를 자동 생성합니다.
          </motion.p>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
            className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <button onClick={() => navigate("/projects")}
              className="group relative inline-flex items-center gap-2 bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 text-white font-semibold text-lg px-8 py-4 rounded-2xl shadow-2xl shadow-violet-900/40 hover:shadow-violet-700/60 transition-all hover:scale-[1.02]">
              <Sparkles className="w-5 h-5" />
              생성 시작하기
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </button>
            <button onClick={() => document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })}
              className="px-6 py-4 text-sm text-zinc-400 hover:text-white transition-colors">
              어떻게 동작하나요? →
            </button>
          </motion.div>

          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}
            className="mt-16 flex flex-wrap items-center justify-center gap-8 text-zinc-600 text-xs">
            <div className="flex items-center gap-2"><Check className="w-3.5 h-3.5 text-emerald-500" /> 텍스처 포함 OBJ/GLB</div>
            <div className="flex items-center gap-2"><Check className="w-3.5 h-3.5 text-emerald-500" /> Blender / Three.js 호환</div>
            <div className="flex items-center gap-2"><Check className="w-3.5 h-3.5 text-emerald-500" /> 자동 리깅 (Beta)</div>
            <div className="flex items-center gap-2"><Check className="w-3.5 h-3.5 text-emerald-500" /> 16GB GPU 지원</div>
          </motion.div>
        </div>
      </section>

      {/* ── FEATURES ─────────────────────────────────────────── */}
      <section id="features" className="py-24 px-6 border-t border-zinc-900">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <span className="text-xs font-semibold text-violet-400 tracking-widest uppercase">FEATURES</span>
            <h2 className="text-4xl md:text-5xl font-bold mt-3 mb-4">전체 파이프라인을 자동화</h2>
            <p className="text-zinc-400 max-w-2xl mx-auto">사진 업로드부터 3D 메쉬·텍스처·리깅까지 한 곳에서 처리합니다.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              { icon: Camera,   color: "from-pink-500 to-rose-500",      title: "다각도 촬영",  desc: "20장 이상의 사진만 있으면 시작 가능합니다. 동영상도 지원합니다." },
              { icon: Wand2,    color: "from-violet-500 to-purple-500",  title: "자동 배경 분리", desc: "BiRefNet이 피규어만 정확히 분리해 깨끗한 입력을 만듭니다." },
              { icon: Cpu,      color: "from-blue-500 to-cyan-500",      title: "COLMAP 포즈",  desc: "SfM 기반 카메라 포즈를 자동 추정합니다." },
              { icon: Layers,   color: "from-teal-500 to-emerald-500",   title: "3DGS 학습",     desc: "Gaussian Splatting으로 정밀한 3D 표현을 학습합니다." },
              { icon: Box,      color: "from-amber-500 to-orange-500",   title: "메쉬 추출",     desc: "SuGaR/GOF로 텍스처 포함된 메쉬를 즉시 추출합니다." },
              { icon: Bone,     color: "from-fuchsia-500 to-pink-500",   title: "자동 리깅 (Beta)", desc: "캐릭터형 메쉬에 자동으로 본을 심어 애니메이션 가능하게 만듭니다." },
            ].map((f, i) => {
              const Icon = f.icon;
              return (
                <motion.div key={f.title}
                  initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }} transition={{ delay: i * 0.05 }}
                  className="group relative p-6 rounded-2xl bg-zinc-900/60 border border-zinc-800 hover:border-zinc-700 transition-all">
                  <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${f.color} flex items-center justify-center mb-4 shadow-lg`}>
                    <Icon className="w-6 h-6 text-white" />
                  </div>
                  <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
                  <p className="text-sm text-zinc-400 leading-relaxed">{f.desc}</p>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── SOLUTIONS ────────────────────────────────────────── */}
      <section id="solutions" className="py-24 px-6 border-t border-zinc-900 relative">
        <div className="absolute inset-0 bg-gradient-to-b from-violet-950/10 via-transparent to-transparent pointer-events-none" />
        <div className="relative max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <span className="text-xs font-semibold text-blue-400 tracking-widest uppercase">SOLUTIONS</span>
            <h2 className="text-4xl md:text-5xl font-bold mt-3 mb-4">어떤 용도로든</h2>
            <p className="text-zinc-400 max-w-2xl mx-auto">피규어 컬렉터부터 게임 개발자까지, 다양한 워크플로우에 맞춰 사용하세요.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {[
              {
                tag: "피규어 / 프린팅",
                title: "컬렉션을 디지털로 백업",
                desc: "피규어를 정밀하게 스캔해서 개인 아카이브를 만들거나 3D 프린팅 원본으로 활용합니다.",
                items: ["고해상도 OBJ + 텍스처", "프린팅 호환 메쉬", "스케일 조정 가능"],
                accent: "violet",
              },
              {
                tag: "게임 / VR",
                title: "게임 에셋 빠른 제작",
                desc: "현실의 오브젝트를 게임 엔진에 바로 가져갑니다. Unity·Unreal에서 바로 임포트 가능.",
                items: ["GLB 즉시 다운로드", "최적화된 메쉬", "PBR 텍스처 호환"],
                accent: "blue",
              },
              {
                tag: "애니메이션",
                title: "캐릭터 리깅 & 애니메이션",
                desc: "리깅을 자동화해 모션 그래픽이나 짧은 애니메이션을 빠르게 제작합니다.",
                items: ["자동 본 배치 (Beta)", "Mixamo 연동 예정", "FBX 익스포트 예정"],
                accent: "teal",
              },
            ].map((s, i) => (
              <motion.div key={s.title}
                initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }} transition={{ delay: i * 0.1 }}
                className="p-6 rounded-2xl bg-zinc-900/60 border border-zinc-800 hover:border-zinc-700 transition-all">
                <span className={`inline-block text-xs font-medium px-2.5 py-1 rounded-full mb-4 ${
                  s.accent === "violet" ? "bg-violet-950/50 text-violet-300 border border-violet-800/50" :
                  s.accent === "blue"   ? "bg-blue-950/50 text-blue-300 border border-blue-800/50" :
                                          "bg-teal-950/50 text-teal-300 border border-teal-800/50"
                }`}>{s.tag}</span>
                <h3 className="text-xl font-semibold mb-3">{s.title}</h3>
                <p className="text-sm text-zinc-400 mb-5 leading-relaxed">{s.desc}</p>
                <ul className="space-y-2">
                  {s.items.map((it) => (
                    <li key={it} className="flex items-center gap-2 text-sm text-zinc-300">
                      <Check className="w-4 h-4 text-emerald-500 shrink-0" />{it}
                    </li>
                  ))}
                </ul>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PRICING ──────────────────────────────────────────── */}
      <section id="pricing" className="py-24 px-6 border-t border-zinc-900">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <span className="text-xs font-semibold text-teal-400 tracking-widest uppercase">PRICING</span>
            <h2 className="text-4xl md:text-5xl font-bold mt-3 mb-4">간단한 가격</h2>
            <p className="text-zinc-400 max-w-2xl mx-auto">필요한 만큼만 사용하세요. 셀프 호스팅도 가능합니다.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-5xl mx-auto">
            {[
              {
                name: "Free",
                price: "₩0",
                period: "영구 무료",
                desc: "개인 프로젝트, 테스트용",
                features: ["월 3개 프로젝트", "표준 품질 (30k iter)", "GLB / OBJ 다운로드", "커뮤니티 지원"],
                cta: "지금 시작하기",
                highlight: false,
              },
              {
                name: "Pro",
                price: "₩19,900",
                period: "월 구독",
                desc: "크리에이터, 프리랜서",
                features: ["무제한 프로젝트", "고품질 (60k iter)", "리깅 기능 제공", "우선 처리 큐", "이메일 지원"],
                cta: "Pro 시작하기",
                highlight: true,
              },
              {
                name: "Enterprise",
                price: "문의",
                period: "맞춤형",
                desc: "스튜디오, 기업",
                features: ["전용 GPU 인스턴스", "온프레미스 배포", "API 접근", "SLA 보장", "전담 매니저"],
                cta: "상담 신청",
                highlight: false,
              },
            ].map((p) => (
              <div key={p.name}
                className={`relative p-7 rounded-2xl border transition-all ${
                  p.highlight
                    ? "bg-gradient-to-b from-violet-950/40 to-zinc-900/60 border-violet-700 shadow-2xl shadow-violet-900/30 scale-[1.02]"
                    : "bg-zinc-900/60 border-zinc-800 hover:border-zinc-700"
                }`}>
                {p.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-gradient-to-r from-violet-500 to-blue-500 text-white text-xs font-semibold px-3 py-1 rounded-full flex items-center gap-1">
                    <Star className="w-3 h-3" />가장 인기
                  </div>
                )}
                <div className="mb-5">
                  <h3 className="text-xl font-semibold mb-1">{p.name}</h3>
                  <p className="text-sm text-zinc-500">{p.desc}</p>
                </div>
                <div className="mb-6">
                  <span className="text-4xl font-bold">{p.price}</span>
                  <span className="text-sm text-zinc-500 ml-2">{p.period}</span>
                </div>
                <ul className="space-y-2.5 mb-7">
                  {p.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-zinc-300">
                      <Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />{f}
                    </li>
                  ))}
                </ul>
                <button onClick={() => navigate("/projects")}
                  className={`w-full py-2.5 rounded-xl text-sm font-medium transition-all ${
                    p.highlight
                      ? "bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 text-white shadow-lg shadow-violet-900/30"
                      : "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                  }`}>
                  {p.cta}
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA BAND ─────────────────────────────────────────── */}
      <section className="py-20 px-6 border-t border-zinc-900">
        <div className="max-w-4xl mx-auto text-center relative">
          <div className="absolute inset-0 bg-gradient-radial from-violet-600/20 to-transparent blur-3xl pointer-events-none" />
          <div className="relative">
            <Zap className="w-10 h-10 text-violet-400 mx-auto mb-5" />
            <h2 className="text-4xl md:text-5xl font-bold mb-5">지금 바로 시작하세요</h2>
            <p className="text-zinc-400 text-lg mb-8">사진 한 묶음으로 첫 3D 모델을 만들어보세요. 30분 안에 결과를 받아볼 수 있습니다.</p>
            <button onClick={() => navigate("/projects")}
              className="group inline-flex items-center gap-2 bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 text-white font-semibold text-lg px-8 py-4 rounded-2xl shadow-2xl shadow-violet-900/40 transition-all hover:scale-[1.02]">
              <Sparkles className="w-5 h-5" />
              생성 시작하기
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </button>
          </div>
        </div>
      </section>

      {/* ── FOOTER ───────────────────────────────────────────── */}
      <footer className="border-t border-zinc-900 py-10 px-6">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-zinc-600">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center">
              <Box className="w-3 h-3 text-white" />
            </div>
            <span>© 2026 SnapAsset3D. All rights reserved.</span>
          </div>
          <div className="flex items-center gap-5">
            <a className="hover:text-zinc-400 transition-colors cursor-pointer">개인정보처리방침</a>
            <a className="hover:text-zinc-400 transition-colors cursor-pointer">이용약관</a>
            <a className="hover:text-zinc-400 transition-colors cursor-pointer">문의하기</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
