import { ReactNode, useEffect } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuthStore } from "../stores/useAuthStore";

interface Props {
  children: ReactNode;
  /** true 면 로그인 안 한 경우 /login 으로 redirect */
  required?: boolean;
}

export default function AuthGuard({ children, required = true }: Props) {
  const location = useLocation();
  const { user, initialized, hydrate } = useAuthStore();

  useEffect(() => { hydrate(); }, [hydrate]);

  if (!initialized) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-violet-500 animate-spin" />
      </div>
    );
  }

  if (required && !user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  return <>{children}</>;
}
