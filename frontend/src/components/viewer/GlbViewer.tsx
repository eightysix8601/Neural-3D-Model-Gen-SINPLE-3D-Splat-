/**
 * 재사용 가능한 GLB 3D 뷰어. ProjectDetailPage, ModelDetailPage 등에서 공통 사용.
 *
 * 자동 회전 + OrbitControls. 우상단 뒤집기 토글 — TripoSG 워커 패치 전에 만들어진
 * 모델이 위아래 뒤집혀 저장돼 있어, 사용자가 보면서 한번 누르면 정자세로 볼 수 있다.
 */
import { Suspense, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Stage, Center, useGLTF } from "@react-three/drei";
import { FlipVertical2, RotateCcw } from "lucide-react";
import ErrorBoundary from "../ErrorBoundary";

interface Props {
  url: string;
  /** 자동 회전 ON/OFF. 기본 true. */
  autoRotate?: boolean;
  /** 시작 시 위아래 뒤집힌 상태로 표시. 기본 false. */
  defaultFlipped?: boolean;
  /** 뒤집기 토글 노출. 기본 true. */
  showFlipToggle?: boolean;
}

function GlbModel({ url, flipped }: { url: string; flipped: boolean }) {
  const gltf = useGLTF(url);
  return (
    <group rotation={flipped ? [Math.PI, 0, 0] : [0, 0, 0]}>
      <primitive object={gltf.scene} />
    </group>
  );
}

export default function GlbViewer({
  url,
  autoRotate = true,
  defaultFlipped = false,
  showFlipToggle = true,
}: Props) {
  const [flipped, setFlipped] = useState(defaultFlipped);
  const [rotateOn, setRotateOn] = useState(autoRotate);

  return (
    <div className="relative w-full h-full">
      <ErrorBoundary>
        <Canvas
          camera={{ position: [0, 0, 2.5], fov: 45 }}
          dpr={[1, 2]}
          gl={{ antialias: true, preserveDrawingBuffer: true }}>
          <color attach="background" args={["#0a0a0a"]} />
          <ambientLight intensity={0.6} />
          <directionalLight position={[5, 5, 5]} intensity={1.2} />
          <Suspense fallback={null}>
            <Stage environment="city" intensity={0.4} adjustCamera={1.2} shadows={false}>
              <Center>
                <GlbModel url={url} flipped={flipped} />
              </Center>
            </Stage>
          </Suspense>
          <OrbitControls
            enableDamping
            dampingFactor={0.08}
            autoRotate={rotateOn}
            autoRotateSpeed={0.6}
            minDistance={1}
            maxDistance={10}
          />
        </Canvas>
      </ErrorBoundary>

      {/* 컨트롤 — 우상단 */}
      <div className="absolute top-3 right-3 flex items-center gap-1.5 pointer-events-auto">
        <button onClick={() => setRotateOn((v) => !v)} title="자동 회전 토글"
          className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium backdrop-blur border transition-all ${
            rotateOn
              ? "bg-violet-500/80 border-violet-400 text-white"
              : "bg-black/60 border-white/10 text-zinc-300 hover:border-zinc-500"
          }`}>
          <RotateCcw className="w-3 h-3" />{rotateOn ? "회전 ON" : "회전 OFF"}
        </button>
        {showFlipToggle && (
          <button onClick={() => setFlipped((v) => !v)} title="위아래 뒤집기"
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium backdrop-blur border transition-all ${
              flipped
                ? "bg-amber-500/80 border-amber-400 text-white"
                : "bg-black/60 border-white/10 text-zinc-300 hover:border-zinc-500"
            }`}>
            <FlipVertical2 className="w-3 h-3" />뒤집기
          </button>
        )}
      </div>

      {/* 좌하단 안내 */}
      <div className="absolute bottom-3 left-3 pointer-events-none">
        <span className="px-2 py-1 rounded-full bg-black/60 backdrop-blur text-[10px] text-zinc-300 border border-white/10">
          드래그로 회전 · 스크롤로 줌
        </span>
      </div>
    </div>
  );
}
