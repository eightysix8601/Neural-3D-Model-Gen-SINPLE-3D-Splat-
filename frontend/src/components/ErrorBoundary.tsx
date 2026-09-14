/**
 * 3D 뷰어 등에서 발생하는 렌더 에러가 앱 전체를 검은 화면으로 만들지 않게 한다.
 * (예: GLB 로드 실패 시 useGLTF 가 Suspense 밖으로 throw → 트리 언마운트)
 */
import { Component, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  /** key 가 바뀌면 에러 상태 자동 리셋 (예: 새 모델 URL) */
  resetKey?: string | number | null;
}
interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  componentDidCatch(error: unknown) {
    console.error("[ErrorBoundary]", error);
  }

  private reset = () => this.setState({ hasError: false });

  render() {
    if (!this.state.hasError) return this.props.children;
    if (this.props.fallback !== undefined) return this.props.fallback;
    return (
      <div className="w-full h-full flex flex-col items-center justify-center gap-3 bg-zinc-900 text-center p-6">
        <AlertTriangle className="w-8 h-8 text-amber-400" />
        <p className="text-sm text-zinc-300">3D 미리보기를 불러오지 못했습니다</p>
        <p className="text-xs text-zinc-600 max-w-xs">
          모델 파일은 오른쪽 패널의 “파일” 탭에서 그대로 다운로드할 수 있습니다.
        </p>
        <button
          onClick={this.reset}
          className="mt-1 flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-xs transition-colors"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          다시 시도
        </button>
      </div>
    );
  }
}

export default ErrorBoundary;
