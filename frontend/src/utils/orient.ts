/**
 * COLMAP/SfM 좌표계엔 절대적인 "위(up)"가 없어 메쉬·포인트클라우드가
 * 뒤집혀(머리 아래, 다리 위) 보인다. 형상으로 똑바로 세우는 회전을 추정한다.
 *
 * 휴리스틱 (선 피규어 가정):
 *   1) 분산이 가장 큰 좌표축 = 세로(키) 축
 *   2) 그 축의 위/아래 20% 슬랩에서 반경 퍼짐이 더 넓은 쪽 = 바닥(받침/발)
 *   3) 바닥이 -Y, 머리가 +Y 가 되도록 회전
 * 비대칭이 약한 모델이면 최소한 "키 축을 수직"으로는 맞춰주므로 현 상태보다 나빠지지 않는다.
 */
import * as THREE from "three";

export function computeUprightQuaternion(positions: ArrayLike<number>): THREE.Quaternion {
  const total = Math.floor(positions.length / 3);
  const identity = new THREE.Quaternion();
  if (total < 50) return identity;

  // 성능: 최대 ~120k 표본만 사용
  const stride = Math.max(1, Math.floor(total / 120000));
  const idx: number[] = [];
  for (let i = 0; i < total; i += stride) idx.push(i);
  const n = idx.length;

  let cx = 0, cy = 0, cz = 0;
  for (const i of idx) { cx += positions[i * 3]; cy += positions[i * 3 + 1]; cz += positions[i * 3 + 2]; }
  cx /= n; cy /= n; cz /= n;

  let vx = 0, vy = 0, vz = 0;
  for (const i of idx) {
    const dx = positions[i * 3] - cx, dy = positions[i * 3 + 1] - cy, dz = positions[i * 3 + 2] - cz;
    vx += dx * dx; vy += dy * dy; vz += dz * dz;
  }

  const axis = new THREE.Vector3(1, 0, 0);
  let maxv = vx;
  if (vy > maxv) { maxv = vy; axis.set(0, 1, 0); }
  if (vz > maxv) { maxv = vz; axis.set(0, 0, 1); }

  // 축 투영값 범위
  let tmin = Infinity, tmax = -Infinity;
  for (const i of idx) {
    const t = (positions[i * 3] - cx) * axis.x + (positions[i * 3 + 1] - cy) * axis.y + (positions[i * 3 + 2] - cz) * axis.z;
    if (t < tmin) tmin = t;
    if (t > tmax) tmax = t;
  }
  const span = tmax - tmin || 1;
  const loCut = tmin + span * 0.2;
  const hiCut = tmax - span * 0.2;

  let loR = 0, loC = 0, hiR = 0, hiC = 0;
  for (const i of idx) {
    const dx = positions[i * 3] - cx, dy = positions[i * 3 + 1] - cy, dz = positions[i * 3 + 2] - cz;
    const t = dx * axis.x + dy * axis.y + dz * axis.z;
    const rx = dx - axis.x * t, ry = dy - axis.y * t, rz = dz - axis.z * t;
    const r = Math.sqrt(rx * rx + ry * ry + rz * rz);
    if (t <= loCut) { loR += r; loC++; }
    else if (t >= hiCut) { hiR += r; hiC++; }
  }
  const loAvg = loC ? loR / loC : 0;
  const hiAvg = hiC ? hiR / hiC : 0;

  // axis(+) 끝이 더 넓으면(=바닥이면) 뒤집힌 것 → up 을 반대로
  const up = axis.clone();
  if (hiAvg > loAvg) up.negate();
  up.normalize();

  return new THREE.Quaternion().setFromUnitVectors(up, new THREE.Vector3(0, 1, 0));
}
