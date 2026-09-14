import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Heart, Eye, Box } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { toggleLike, type GalleryItem } from "../utils/api";
import { useAuthStore } from "../stores/useAuthStore";

interface Props {
  item: GalleryItem;
}

const CATEGORY_LABEL: Record<string, string> = {
  other: "기타", character: "캐릭터", vehicle: "차량",
  furniture: "가구", animal: "동물", food: "음식",
  prop: "소품", building: "건물",
};

export default function GalleryCard({ item }: Props) {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [liked, setLiked] = useState(!!item.liked_by_me);
  const [likeCount, setLikeCount] = useState(item.like_count);
  const [busy, setBusy] = useState(false);

  const onLike = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!user) {
      toast("로그인이 필요합니다", { icon: "🔒" });
      navigate("/login");
      return;
    }
    if (busy) return;
    setBusy(true);
    try {
      const r = await toggleLike(item.id);
      setLiked(r.liked);
      setLikeCount(r.like_count);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <motion.div layout
      whileHover={{ y: -4 }}
      transition={{ type: "spring", stiffness: 300, damping: 24 }}
      onClick={() => navigate(`/m/${item.id}`)}
      className="group flex-shrink-0 w-64 cursor-pointer">
      <div className="relative aspect-square rounded-2xl overflow-hidden bg-zinc-900 border border-zinc-800 group-hover:border-violet-700/60 transition-all shadow-lg group-hover:shadow-violet-900/20">
        {item.thumbnail_url ? (
          <img src={item.thumbnail_url} alt={item.name}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Box className="w-12 h-12 text-zinc-700" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
        <div className="absolute bottom-2 left-2 right-2 flex items-end justify-between opacity-0 group-hover:opacity-100 transition-opacity">
          <span className="text-xs px-2 py-1 bg-black/60 backdrop-blur rounded-full text-white border border-white/10">
            {CATEGORY_LABEL[item.category] ?? item.category}
          </span>
          <div className="flex items-center gap-1">
            <button onClick={onLike} disabled={busy}
              className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs backdrop-blur transition-all ${
                liked
                  ? "bg-rose-500/80 text-white"
                  : "bg-black/60 text-white border border-white/10 hover:bg-rose-500/60"
              }`}>
              <Heart className={`w-3 h-3 ${liked ? "fill-current" : ""}`} />
              {likeCount}
            </button>
          </div>
        </div>
      </div>
      <div className="mt-2 px-1">
        <div className="text-sm font-medium text-zinc-100 truncate">{item.name}</div>
        <div className="flex items-center gap-2 text-xs text-zinc-500 mt-0.5">
          <span className="truncate">@{item.owner?.username ?? "anon"}</span>
          <span className="text-zinc-700">·</span>
          <span className="flex items-center gap-0.5"><Eye className="w-3 h-3" />{item.view_count}</span>
        </div>
      </div>
    </motion.div>
  );
}
