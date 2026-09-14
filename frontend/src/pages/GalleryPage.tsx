import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Sparkles, Zap, Camera, Wand2, ArrowRight, Box, Image as ImageIcon,
  Cpu, Layers, TrendingUp, Clock,
} from "lucide-react";
import toast from "react-hot-toast";
import TopNav from "../components/TopNav";
import GalleryCard from "../components/GalleryCard";
import DragRow from "../components/DragRow";
import { listCategories, listGallery, type Category, type GalleryItem } from "../utils/api";
import { useAuthStore } from "../stores/useAuthStore";

const CATEGORIES: { key: Category | "all"; label: string; emoji: string }[] = [
  { key: "all",       label: "전체",   emoji: "✨" },
  { key: "character", label: "캐릭터", emoji: "🧙" },
  { key: "vehicle",   label: "차량",   emoji: "🚗" },
  { key: "furniture", label: "가구",   emoji: "🪑" },
  { key: "animal",    label: "동물",   emoji: "🐶" },
  { key: "food",      label: "음식",   emoji: "🍔" },
  { key: "prop",      label: "소품",   emoji: "🎁" },
  { key: "building",  label: "건물",   emoji: "🏠" },
  { key: "other",     label: "기타",   emoji: "📦" },
];

export default function GalleryPage() {
  const navigate = useNavigate();
  const { user, hydrate } = useAuthStore();
  const [tab, setTab] = useState<Category | "all">("all");
  const [sort, setSort] = useState<"recent" | "popular">("recent");
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [popular, setPopular] = useState<GalleryItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => { hydrate(); }, [hydrate]);

  useEffect(() => {
    listCategories()
      .then((rs) => {
        const m: Record<string, number> = {};
        rs.forEach((r) => (m[r.key] = r.count));
        setCounts(m);
      })
      .catch(() => {});
    listGallery({ sort: "popular", limit: 16 })
      .then(setPopular)
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    listGallery({
      category: tab === "all" ? undefined : tab,
      sort,
      limit: 48,
    })
      .then(setItems)
      .catch((e: Error) => toast.error(e.message))
      .finally(() => setLoading(false));
  }, [tab, sort]);

  const totalCount = useMemo(
    () => Object.values(counts).reduce((a, b) => a + b, 0),
    [counts],
  );

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <TopNav variant="transparent" />

      {/* ── HERO + 두 모드 ─────────────────────────── */}
      <section className="relative pt-12 pb-10 px-6 overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-[900px] h-[600px] bg-gradient-radial from-violet-600/25 via-blue-600/10 to-transparent blur-3xl" />
        </div>
        <div className="relative max-w-7xl mx-auto">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-violet-700/40 bg-violet-950/30 text-xs text-violet-300 mb-5">
            <Sparkles className="w-3.5 h-3.5" />사진 → 3D 메쉬, 더 빠르게
          </motion.div>
          <motion.h1 initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
            className="text-4xl md:text-6xl font-bold leading-tight tracking-tight mb-4">
            상상하는{" "}
            <span className="bg-gradient-to-r from-violet-400 via-blue-400 to-teal-400 bg-clip-text text-transparent">
              모든 것
            </span>
            을 3D로
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            className="text-zinc-400 text-lg max-w-2xl mb-8">
            한 장의 이미지로 5분 안에 메쉬를 받거나, 다각도 촬영으로 고정밀 텍스처 메쉬를 만드세요.
          </motion.p>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
            className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl">
            <button onClick={() => navigate(user ? "/create?mode=tripo" : "/login")}
              className="group relative text-left p-6 rounded-2xl bg-gradient-to-br from-violet-900/60 to-zinc-900 border border-violet-700/40 hover:border-violet-500 transition-all shadow-xl shadow-violet-900/20">
              <div className="absolute top-4 right-4 text-xs px-2 py-0.5 rounded-full bg-violet-500/20 border border-violet-500/40 text-violet-200">NEW</div>
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center mb-3 shadow-lg">
                <Zap className="w-5 h-5 text-white" />
              </div>
              <h3 className="text-xl font-semibold mb-1">스마트 메시 생성</h3>
              <p className="text-sm text-zinc-400 mb-3">이미지 1장 → 약 1~3분. TripoSG/TripoSF 기반.</p>
              <div className="flex items-center gap-1.5 text-sm text-violet-300 font-medium">
                시작하기 <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </div>
            </button>

            <button onClick={() => navigate(user ? "/create?mode=highres" : "/login")}
              className="group relative text-left p-6 rounded-2xl bg-gradient-to-br from-blue-900/40 to-zinc-900 border border-blue-700/30 hover:border-blue-500 transition-all shadow-xl shadow-blue-900/10">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-teal-500 flex items-center justify-center mb-3 shadow-lg">
                <Layers className="w-5 h-5 text-white" />
              </div>
              <h3 className="text-xl font-semibold mb-1">고정밀 모델 생성</h3>
              <p className="text-sm text-zinc-400 mb-3">다각도 사진 → COLMAP + SuGaR/GOF/NeRF. 텍스처 포함.</p>
              <div className="flex items-center gap-1.5 text-sm text-blue-300 font-medium">
                시작하기 <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </div>
            </button>
          </motion.div>
        </div>
      </section>

      {/* ── 인기 ───────────────────────────────────── */}
      {popular.length > 0 && (
        <section className="px-6 py-6 border-t border-zinc-900">
          <div className="max-w-7xl mx-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-rose-400" />인기 작품
              </h2>
              <span className="text-xs text-zinc-500">드래그해서 둘러보세요</span>
            </div>
            <DragRow>
              {popular.map((it) => <GalleryCard key={it.id} item={it} />)}
            </DragRow>
          </div>
        </section>
      )}

      {/* ── 카테고리 + 정렬 ──────────────────────── */}
      <section className="px-6 py-6 border-t border-zinc-900">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
            <div className="flex items-center gap-1 flex-wrap">
              {CATEGORIES.map((c) => {
                const cnt = c.key === "all" ? totalCount : (counts[c.key] ?? 0);
                const active = tab === c.key;
                return (
                  <button key={c.key} onClick={() => setTab(c.key)}
                    className={`px-3 py-1.5 rounded-full text-sm border transition-all ${
                      active
                        ? "bg-violet-600 border-violet-500 text-white shadow-md shadow-violet-900/30"
                        : "bg-zinc-900 border-zinc-800 text-zinc-300 hover:border-zinc-700"
                    }`}>
                    <span className="mr-1">{c.emoji}</span>{c.label}
                    <span className="ml-1.5 text-xs text-zinc-500">{cnt}</span>
                  </button>
                );
              })}
            </div>
            <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-0.5">
              <button onClick={() => setSort("recent")}
                className={`px-3 py-1 rounded-md text-xs flex items-center gap-1 ${
                  sort === "recent" ? "bg-zinc-800 text-white" : "text-zinc-400"
                }`}>
                <Clock className="w-3 h-3" />최신
              </button>
              <button onClick={() => setSort("popular")}
                className={`px-3 py-1 rounded-md text-xs flex items-center gap-1 ${
                  sort === "popular" ? "bg-zinc-800 text-white" : "text-zinc-400"
                }`}>
                <TrendingUp className="w-3 h-3" />인기
              </button>
            </div>
          </div>

          {loading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
              {Array.from({ length: 12 }).map((_, i) => (
                <div key={i} className="aspect-square bg-zinc-900 border border-zinc-800 rounded-2xl animate-pulse" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-20">
              <Box className="w-12 h-12 text-zinc-700 mx-auto mb-4" />
              <p className="text-zinc-400">아직 공개된 작품이 없습니다</p>
              <p className="text-zinc-600 text-sm mt-1">처음 작품을 만들어 갤러리에 공개해보세요</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
              {items.map((it) => (
                <div key={it.id}>
                  <GalleryCard item={it} />
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <footer className="border-t border-zinc-900 py-8 px-6 mt-10">
        <div className="max-w-7xl mx-auto space-y-3 text-xs text-zinc-600">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center">
                <Box className="w-3 h-3 text-white" />
              </div>
              <span>© 2026 SnapAsset3D</span>
            </div>
            <span>다각도 → 고정밀 / 단일 이미지 → 스마트 메시</span>
          </div>
          <p className="text-[10px] text-zinc-700 max-w-3xl leading-relaxed">
            Mesh generation powered by{" "}
            <a href="https://github.com/VAST-AI-Research/TripoSG" target="_blank" rel="noopener"
              className="underline hover:text-zinc-500">VAST AI TripoSG</a>.
            Textures via front-view projection (in-house).
          </p>
        </div>
      </footer>
    </div>
  );
}
