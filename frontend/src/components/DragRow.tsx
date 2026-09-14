import { ReactNode, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface Props {
  children: ReactNode;
}

/** 가로 드래그 + 스크롤 버튼이 있는 캐러셀 컨테이너. Tripo 메인 스타일. */
export default function DragRow({ children }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ down: boolean; x: number; left: number; moved: boolean }>({
    down: false, x: 0, left: 0, moved: false,
  });

  const onMouseDown = (e: React.MouseEvent) => {
    if (!ref.current) return;
    setDrag({ down: true, x: e.pageX, left: ref.current.scrollLeft, moved: false });
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!drag.down || !ref.current) return;
    const dx = e.pageX - drag.x;
    if (Math.abs(dx) > 4) setDrag((d) => ({ ...d, moved: true }));
    ref.current.scrollLeft = drag.left - dx;
  };
  const stopDrag = () => setDrag((d) => ({ ...d, down: false }));

  const scroll = (dir: 1 | -1) => {
    if (!ref.current) return;
    ref.current.scrollBy({ left: dir * 600, behavior: "smooth" });
  };

  return (
    <div className="relative group/row">
      <button onClick={() => scroll(-1)}
        className="absolute left-0 top-1/2 -translate-y-1/2 z-10 w-9 h-9 rounded-full bg-zinc-900/90 border border-zinc-700 hover:bg-violet-600 hover:border-violet-500 flex items-center justify-center opacity-0 group-hover/row:opacity-100 transition-all -translate-x-1/2 shadow-xl">
        <ChevronLeft className="w-4 h-4 text-white" />
      </button>
      <button onClick={() => scroll(1)}
        className="absolute right-0 top-1/2 -translate-y-1/2 z-10 w-9 h-9 rounded-full bg-zinc-900/90 border border-zinc-700 hover:bg-violet-600 hover:border-violet-500 flex items-center justify-center opacity-0 group-hover/row:opacity-100 transition-all translate-x-1/2 shadow-xl">
        <ChevronRight className="w-4 h-4 text-white" />
      </button>
      <div
        ref={ref}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={stopDrag}
        onMouseLeave={stopDrag}
        onClickCapture={(e) => { if (drag.moved) { e.preventDefault(); e.stopPropagation(); } }}
        className={`flex gap-4 overflow-x-auto pb-4 px-1 scroll-smooth select-none ${
          drag.down ? "cursor-grabbing" : "cursor-grab"
        }`}
        style={{ scrollbarWidth: "thin" }}>
        {children}
      </div>
    </div>
  );
}
