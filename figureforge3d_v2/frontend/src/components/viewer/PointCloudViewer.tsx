/**
 * frontend/src/components/viewer/PointCloudViewer.tsx
 *
 * 고급 포인트클라우드 뷰어
 * - 자동 Y축 회전 (autoRotate)
 * - 사용자 터치/드래그 시 회전 멈춤
 * - 새로고침 버튼으로 원래 뷰로 복귀 + 자동 회전 재개
 * - 단계별 색상 (COLMAP=초록, 3DGS중간=보라, 3DGS완료=파랑)
 */
import { useEffect, useRef, useState, useCallback } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader";
import { RotateCcw, Loader2, AlertCircle, Maximize2 } from "lucide-react";

interface Props {
  url: string;
  color?: string;
  pointSize?: number;
  label?: string;
  stage?: "colmap" | "gs7k" | "gs30k" | "mesh";
}

const STAGE_CONFIG = {
  colmap: {
    color: "#4ade80",
    glow: "#22c55e",
    label: "COLMAP 포인트클라우드",
    desc: "카메라 위치 추정 완료",
    pointSize: 3,
  },
  gs7k: {
    color: "#c084fc",
    glow: "#a855f7",
    label: "3DGS 중간 결과 (7k)",
    desc: "학습 진행 중...",
    pointSize: 1.2,
  },
  gs30k: {
    color: "#60a5fa",
    glow: "#3b82f6",
    label: "3DGS 완료 (30k)",
    desc: "메쉬 추출 중...",
    pointSize: 1,
  },
  mesh: {
    color: "#f59e0b",
    glow: "#f59e0b",
    label: "완성된 메쉬",
    desc: "처리 완료!",
    pointSize: 1,
  },
};

export default function PointCloudViewer({
  url,
  color,
  pointSize,
  label,
  stage = "gs30k",
}: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    controls: OrbitControls;
    animId: number;
    isUserInteracting: boolean;
  } | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pointCount, setPointCount] = useState(0);
  const [isAutoRotating, setIsAutoRotating] = useState(true);

  const cfg = STAGE_CONFIG[stage];
  const finalColor = color || cfg.color;
  const finalPointSize = pointSize || cfg.pointSize;

  const resetView = useCallback(() => {
    if (!sceneRef.current) return;
    const { controls, camera } = sceneRef.current;
    camera.position.set(0, 0.5, 3);
    camera.lookAt(0, 0, 0);
    controls.target.set(0, 0, 0);
    controls.update();
    controls.autoRotate = true;
    sceneRef.current.isUserInteracting = false;
    setIsAutoRotating(true);
  }, []);

  useEffect(() => {
    if (!mountRef.current || !url) return;
    const mount = mountRef.current;

    // ── Scene Setup ──────────────────────────────────────────────────────────
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#09090b");
    scene.fog = new THREE.Fog("#09090b", 8, 20);

    const W = mount.clientWidth || 600;
    const H = mount.clientHeight || 400;

    const camera = new THREE.PerspectiveCamera(42, W / H, 0.001, 100);
    camera.position.set(0, 0.5, 3);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    mount.appendChild(renderer.domElement);

    // ── Controls ─────────────────────────────────────────────────────────────
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.autoRotate = false;
    controls.autoRotateSpeed = 0;
    controls.enablePan = true;
    controls.minDistance = 0.5;
    controls.maxDistance = 15;
    controls.target.set(0, 0, 0);

    let isUserInteracting = false;

    const onInteractStart = () => {
      isUserInteracting = true;
      controls.autoRotate = false;
      setIsAutoRotating(false);
    };

    renderer.domElement.addEventListener("pointerdown", onInteractStart);
    renderer.domElement.addEventListener("wheel", onInteractStart);

    sceneRef.current = { renderer, scene, camera, controls, animId: 0, isUserInteracting };

    // ── Grid ─────────────────────────────────────────────────────────────────
    const gridHelper = new THREE.GridHelper(4, 20, "#1a1a2e", "#1a1a2e");
    (gridHelper.material as THREE.Material).opacity = 0.3;
    (gridHelper.material as THREE.Material).transparent = true;
    scene.add(gridHelper);

    // ── Ambient Light ─────────────────────────────────────────────────────────
    scene.add(new THREE.AmbientLight(0xffffff, 0.4));
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(5, 10, 5);
    scene.add(dirLight);

    // ── Load PLY ─────────────────────────────────────────────────────────────
    const loader = new PLYLoader();
    setLoading(true);
    setError(null);

    // loader.load(
    //   url,
    // MinIO URL → 백엔드 프록시로 변환
    const projectId = url.match(/projects\/([^/]+)\//)?.[1];
    const proxyUrl = projectId
      ? `/api/v1/projects/${projectId}/preview/file`
      : url;

    loader.load(
      proxyUrl,
      (geometry) => {
        geometry.computeBoundingBox();
        geometry.computeBoundingSphere();

        const bbox = geometry.boundingBox!;
        const center = new THREE.Vector3();
        bbox.getCenter(center);
        geometry.translate(-center.x, -center.y, -center.z);

        // 크기 정규화
        const size = new THREE.Vector3();
        bbox.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z);
        const scale = 2.0 / maxDim;
        geometry.scale(scale, scale, scale);

        const count = geometry.attributes.position.count;
        setPointCount(count);

        // 포인트 색상
        let material: THREE.PointsMaterial;
        if (geometry.attributes.color) {
          material = new THREE.PointsMaterial({
            size: finalPointSize * 0.008,
            vertexColors: true,
            sizeAttenuation: true,
            transparent: true,
            opacity: 0.9,
          });
        } else {
          material = new THREE.PointsMaterial({
            size: finalPointSize * 0.008,
            color: new THREE.Color(finalColor),
            sizeAttenuation: true,
            transparent: true,
            opacity: 0.85,
          });
        }

        const points = new THREE.Points(geometry, material);
        scene.add(points);

        // 카메라 위치 자동 조정
        const sphere = geometry.boundingSphere!;
        const dist = sphere.radius * 2.5;
        camera.position.set(0, sphere.radius * 0.3, dist);
        controls.update();

        setLoading(false);
      },
      undefined,
      (err) => {
        console.error("PLY 로드 실패:", err);
        setError("포인트클라우드 로드 실패");
        setLoading(false);
      }
    );

    // ── Animate ───────────────────────────────────────────────────────────────
    let animId = 0;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();
    if (sceneRef.current) sceneRef.current.animId = animId;

    // ── Resize ────────────────────────────────────────────────────────────────
    const handleResize = () => {
      if (!mount) return;
      const W2 = mount.clientWidth;
      const H2 = mount.clientHeight;
      camera.aspect = W2 / H2;
      camera.updateProjectionMatrix();
      renderer.setSize(W2, H2);
    };
    const resizeObs = new ResizeObserver(handleResize);
    resizeObs.observe(mount);

    return () => {
      cancelAnimationFrame(animId);
      renderer.domElement.removeEventListener("pointerdown", onInteractStart);
      renderer.domElement.removeEventListener("wheel", onInteractStart);
      resizeObs.disconnect();
      controls.dispose();
      renderer.dispose();
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement);
    };
  }, [url, finalColor, finalPointSize]);

  return (
    <div className="relative w-full h-full rounded-2xl overflow-hidden bg-zinc-950">
      {/* Three.js 마운트 포인트 */}
      <div ref={mountRef} className="w-full h-full" />

      {/* 로딩 오버레이 */}
      {loading && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-950/80 backdrop-blur-sm">
          <div className="relative">
            <div className="w-16 h-16 rounded-full border-2 border-zinc-800 flex items-center justify-center">
              <Loader2 className="w-7 h-7 animate-spin" style={{ color: cfg.glow }} />
            </div>
            <div className="absolute inset-0 rounded-full animate-ping opacity-20" style={{ background: cfg.glow }} />
          </div>
          <p className="text-sm text-zinc-400 mt-4">포인트클라우드 로딩 중...</p>
        </div>
      )}

      {/* 에러 오버레이 */}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <AlertCircle className="w-8 h-8 text-red-500 mb-2" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* 상단 라벨 */}
      {!loading && !error && (
        <div className="absolute top-3 left-3 right-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: cfg.glow }} />
            <div>
              <p className="text-xs font-medium text-zinc-200">{label || cfg.label}</p>
              <p className="text-xs text-zinc-500">{cfg.desc}</p>
            </div>
          </div>
          {pointCount > 0 && (
            <span className="text-xs text-zinc-600 bg-zinc-900/80 px-2 py-1 rounded-lg">
              {pointCount.toLocaleString()}pts
            </span>
          )}
        </div>
      )}

      {/* 하단 컨트롤 */}
      {!loading && !error && (
        <div className="absolute bottom-3 right-3 flex items-center gap-2">
          {/* 자동 회전 상태 표시 */}
          <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition-all ${
            isAutoRotating
              ? "bg-zinc-800/80 text-zinc-400"
              : "bg-zinc-900/80 text-zinc-600"
          }`}>
            <div className={`w-1.5 h-1.5 rounded-full ${isAutoRotating ? "animate-spin" : ""}`}
              style={{ background: isAutoRotating ? cfg.glow : "#52525b",
                animationDuration: "2s", animationTimingFunction: "linear" }} />
            {isAutoRotating ? "자동 회전 중" : "수동 조작 중"}
          </div>

          {/* 리셋 버튼 */}
          <button
            onClick={resetView}
            className="flex items-center gap-1.5 px-2.5 py-1.5 bg-zinc-800/80 hover:bg-zinc-700/80 text-zinc-400 hover:text-zinc-200 rounded-lg text-xs transition-all backdrop-blur-sm"
            title="초기 뷰로 리셋"
          >
            <RotateCcw className="w-3 h-3" />
            리셋
          </button>
        </div>
      )}

      {/* 조작 힌트 (처음 5초만 표시) */}
      {!loading && !error && isAutoRotating && (
        <div className="absolute bottom-3 left-3">
          <p className="text-xs text-zinc-600">드래그하여 회전 · 스크롤하여 확대</p>
        </div>
      )}
    </div>
  );
}
