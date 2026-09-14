import { useNavigate, useLocation, Link } from "react-router-dom";
import { Box, LogIn, Sparkles, User as UserIcon, LogOut, FolderOpen, Image as ImageIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuthStore } from "../stores/useAuthStore";

const NAV_ITEMS = [
  { label: "갤러리",   path: "/" },
  { label: "내 프로젝트", path: "/projects", auth: true },
  { label: "생성하기", path: "/create", auth: true },
];

interface TopNavProps {
  variant?: "transparent" | "solid";
}

export default function TopNav({ variant = "solid" }: TopNavProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, clear, hydrate } = useAuthStore();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => { hydrate(); }, [hydrate]);
  useEffect(() => {
    if (!menuOpen) return;
    const fn = () => setMenuOpen(false);
    window.addEventListener("click", fn);
    return () => window.removeEventListener("click", fn);
  }, [menuOpen]);

  const isActive = (path: string) => {
    if (path === "/") return location.pathname === "/";
    return location.pathname.startsWith(path);
  };

  const logout = () => {
    clear();
    setMenuOpen(false);
    navigate("/", { replace: true });
  };

  return (
    <header className={`sticky top-0 z-50 border-b transition-colors ${
      variant === "transparent"
        ? "bg-zinc-950/40 backdrop-blur-xl border-zinc-900/50"
        : "bg-zinc-950/80 backdrop-blur-xl border-zinc-800"
    }`}>
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
        <button onClick={() => navigate("/")} className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center shadow-lg shadow-violet-900/30 group-hover:shadow-violet-700/40 transition-shadow">
            <Box className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-base bg-gradient-to-r from-violet-300 to-blue-300 bg-clip-text text-transparent">
            SnapAsset3D
          </span>
        </button>

        <nav className="hidden md:flex items-center gap-1">
          {NAV_ITEMS.filter((i) => !i.auth || user).map((item) => (
            <button key={item.label} onClick={() => navigate(item.path)}
              className={`px-3 py-1.5 text-sm rounded-lg transition-all ${
                isActive(item.path)
                  ? "text-white bg-zinc-800/60"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
              }`}>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          {user ? (
            <div className="relative" onClick={(e) => e.stopPropagation()}>
              <button onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 transition-all">
                <div className="w-6 h-6 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center text-xs font-semibold text-white">
                  {user.username[0].toUpperCase()}
                </div>
                <span className="text-sm text-zinc-200">{user.username}</span>
              </button>
              {menuOpen && (
                <div className="absolute right-0 mt-2 w-52 bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl py-1.5 z-50">
                  <div className="px-3 py-2 border-b border-zinc-800">
                    <div className="text-sm text-zinc-200 font-medium truncate">{user.username}</div>
                    <div className="text-xs text-zinc-500 truncate">{user.email}</div>
                  </div>
                  <Link to="/projects" onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors">
                    <FolderOpen className="w-4 h-4" />내 프로젝트
                  </Link>
                  <Link to="/create" onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors">
                    <Sparkles className="w-4 h-4" />새 생성
                  </Link>
                  <button onClick={logout}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-300 hover:bg-zinc-800 transition-colors">
                    <LogOut className="w-4 h-4" />로그아웃
                  </button>
                </div>
              )}
            </div>
          ) : (
            <>
              <button onClick={() => navigate("/login")}
                className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 text-sm text-zinc-400 hover:text-white transition-colors">
                <LogIn className="w-3.5 h-3.5" />로그인
              </button>
              <button onClick={() => navigate("/signup")}
                className="flex items-center gap-1.5 bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 text-white text-sm font-medium px-4 py-1.5 rounded-lg shadow-lg shadow-violet-900/30 transition-all">
                <Sparkles className="w-3.5 h-3.5" />무료 가입하기
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
