"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, ThreeEvent } from "@react-three/fiber";
import { OrbitControls, Html, Grid, Line } from "@react-three/drei";
import * as THREE from "three";
import { api, FacilityDetail, Candidate } from "@/lib/api";
import { useDemo } from "./DemoProvider";

const FACILITY_ID = "FAC-FAHUD-DEMO";
// Plant metres -> scene units. Keeps the site inside a ~10 unit box.
const SCALE = 0.05;

const PIPELINES: [string, string][] = [
  ["SEP-01", "C-03"], ["C-03", "T-02"], ["C-02", "V-14"],
  ["V-14", "C-03"], ["C-03", "PIG-01"], ["KOD-01", "C-02"],
];

const PALETTE = {
  green: "#1D4533",
  umber: "#5E3122",
  peach: "#F9D2BA",
  cream: "#F1E9DE",
  red: "#C4453F",
  orange: "#C97A2E",
  amber: "#B08A2E",
  normal: "#3B7A57",
  steel: "#8C8C84",
  blue: "#33689C",
};

// Coverage geometry mirrors the attribution engine: a sensor "sees" sources
// upwind of it within a lateral spread that grows with distance (Briggs D).
const COVERAGE_REACH_M = 75;
const COVERAGE_HALF_ANGLE_DEG = 11;
const NEARFIELD_RADIUS_M = 12;

export interface TwinFrame {
  sensors: Map<string, number>;
  wind_speed_ms: number;
  wind_dir_deg: number;
  pressure_barg: number | null;
  flow_kg_h: number | null;
}

function toScene(x_m: number, y_m: number): [number, number, number] {
  // plant +x east -> scene +x, plant +y north -> scene -z (so north is "away")
  return [x_m * SCALE, 0, -y_m * SCALE];
}

function sevColor(ppm: number, baseline: number): string {
  const excess = ppm - baseline;
  if (excess > 15) return PALETTE.red;
  if (excess > 3) return PALETTE.orange;
  if (excess > 0.8) return PALETTE.amber;
  return PALETTE.normal;
}

const labelStyle: React.CSSProperties = {
  fontFamily: "-apple-system, Segoe UI, Roboto, sans-serif",
  whiteSpace: "nowrap",
  pointerEvents: "none",
};

// ---------------------------------------------------------------------------
// Equipment primitives — deliberately simple, readable silhouettes
// ---------------------------------------------------------------------------

function Compressor({ highlight }: { highlight: boolean }) {
  const body = highlight ? PALETTE.red : PALETTE.green;
  return (
    <group>
      <mesh position={[0, 0.05, 0]}>
        <boxGeometry args={[1.6, 0.1, 0.9]} />
        <meshStandardMaterial color="#c9bfae" />
      </mesh>
      <mesh position={[-0.3, 0.4, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.3, 0.3, 0.9, 24]} />
        <meshStandardMaterial color={body} metalness={0.3} roughness={0.5} />
      </mesh>
      <mesh position={[0.5, 0.35, 0]}>
        <boxGeometry args={[0.55, 0.5, 0.5]} />
        <meshStandardMaterial color={PALETTE.umber} metalness={0.2} roughness={0.6} />
      </mesh>
      <mesh position={[-0.3, 0.8, 0]}>
        <cylinderGeometry args={[0.08, 0.08, 0.3, 12]} />
        <meshStandardMaterial color={PALETTE.steel} metalness={0.6} />
      </mesh>
    </group>
  );
}

function ControlValve() {
  return (
    <group>
      <mesh position={[0, 0.2, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.12, 0.12, 0.6, 16]} />
        <meshStandardMaterial color={PALETTE.steel} metalness={0.6} roughness={0.4} />
      </mesh>
      <mesh position={[0, 0.45, 0]}>
        <cylinderGeometry args={[0.08, 0.08, 0.4, 12]} />
        <meshStandardMaterial color={PALETTE.steel} metalness={0.6} />
      </mesh>
      <mesh position={[0, 0.7, 0]}>
        <cylinderGeometry args={[0.18, 0.18, 0.12, 16]} />
        <meshStandardMaterial color={PALETTE.blue} />
      </mesh>
    </group>
  );
}

function Tank() {
  return (
    <group>
      <mesh position={[0, 0.5, 0]}>
        <cylinderGeometry args={[0.5, 0.5, 1.0, 32]} />
        <meshStandardMaterial color="#d9d2c4" metalness={0.2} roughness={0.7} />
      </mesh>
      <mesh position={[0, 1.02, 0]}>
        <cylinderGeometry args={[0.52, 0.52, 0.05, 32]} />
        <meshStandardMaterial color={PALETTE.steel} />
      </mesh>
      <mesh position={[0, 1.2, 0]}>
        <cylinderGeometry args={[0.06, 0.06, 0.35, 12]} />
        <meshStandardMaterial color={PALETTE.steel} metalness={0.6} />
      </mesh>
    </group>
  );
}

function HorizontalVessel() {
  return (
    <group>
      <mesh position={[0, 0.45, 0]} rotation={[0, 0, Math.PI / 2]}>
        <capsuleGeometry args={[0.32, 1.1, 8, 24]} />
        <meshStandardMaterial color="#d9d2c4" metalness={0.2} roughness={0.7} />
      </mesh>
      {[-0.45, 0.45].map((x) => (
        <mesh key={x} position={[x, 0.15, 0]}>
          <boxGeometry args={[0.1, 0.3, 0.5]} />
          <meshStandardMaterial color={PALETTE.steel} />
        </mesh>
      ))}
    </group>
  );
}

function VerticalDrum() {
  return (
    <group>
      <mesh position={[0, 0.55, 0]}>
        <capsuleGeometry args={[0.28, 0.7, 8, 24]} />
        <meshStandardMaterial color="#d9d2c4" metalness={0.2} roughness={0.7} />
      </mesh>
      {[0, 1, 2].map((i) => (
        <mesh key={i} position={[Math.cos((i * Math.PI * 2) / 3) * 0.25, 0.1, Math.sin((i * Math.PI * 2) / 3) * 0.25]}>
          <cylinderGeometry args={[0.04, 0.04, 0.2, 8]} />
          <meshStandardMaterial color={PALETTE.steel} />
        </mesh>
      ))}
    </group>
  );
}

function PigLauncher() {
  return (
    <group>
      <mesh position={[0, 0.3, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.18, 0.12, 1.2, 20]} />
        <meshStandardMaterial color={PALETTE.steel} metalness={0.6} roughness={0.4} />
      </mesh>
      <mesh position={[0.62, 0.3, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.24, 0.24, 0.08, 20]} />
        <meshStandardMaterial color={PALETTE.umber} />
      </mesh>
    </group>
  );
}

function EquipmentModel({ type, highlight }: { type: string; highlight: boolean }) {
  switch (type) {
    case "compressor": return <Compressor highlight={highlight} />;
    case "control_valve": return <ControlValve />;
    case "tank_vent": return <Tank />;
    case "separator": return <HorizontalVessel />;
    case "knockout_drum": return <VerticalDrum />;
    case "pig_launcher": return <PigLauncher />;
    default:
      return (
        <mesh position={[0, 0.3, 0]}>
          <boxGeometry args={[0.6, 0.6, 0.6]} />
          <meshStandardMaterial color={PALETTE.steel} />
        </mesh>
      );
  }
}

function PulseRing({ color, radius = 1.0 }: { color: string; radius?: number }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const s = 1 + 0.15 * Math.sin(clock.elapsedTime * 3);
    ref.current.scale.set(s, s, s);
    (ref.current.material as THREE.MeshBasicMaterial).opacity = 0.55 + 0.3 * Math.sin(clock.elapsedTime * 3);
  });
  return (
    <mesh ref={ref} position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[radius, radius * 1.15, 48]} />
      <meshBasicMaterial color={color} transparent opacity={0.7} side={THREE.DoubleSide} />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// Sensor post
// ---------------------------------------------------------------------------

function SensorPost({ color, elevated, ppm, tag }: { color: string; elevated: boolean; ppm: number; tag: string }) {
  const glow = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (!glow.current) return;
    const s = elevated ? 1 + 0.35 * Math.sin(clock.elapsedTime * 5) : 1;
    glow.current.scale.set(s, s, s);
  });
  return (
    <group>
      <mesh position={[0, 0.5, 0]}>
        <cylinderGeometry args={[0.03, 0.03, 1.0, 8]} />
        <meshStandardMaterial color={PALETTE.steel} />
      </mesh>
      <mesh ref={glow} position={[0, 1.05, 0]}>
        <sphereGeometry args={[0.12, 16, 16]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={elevated ? 1.2 : 0.3} />
      </mesh>
      <Html position={[0, 1.4, 0]} center distanceFactor={12} style={{ pointerEvents: "none" }}>
        <div
          style={{
            ...labelStyle,
            background: "rgba(255,255,255,0.92)",
            border: `1px solid ${color}`,
            borderRadius: 6,
            padding: "2px 7px",
            fontSize: 11,
            fontWeight: 700,
            color: elevated ? color : PALETTE.green,
          }}
        >
          {tag}{elevated ? ` · ${ppm.toFixed(1)} ppm` : ""}
        </div>
      </Html>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Coverage wedge: where THIS sensor can detect a source under the current wind
// ---------------------------------------------------------------------------

function CoverageWedge({ windToRad }: { windToRad: number }) {
  // Sources upwind of the sensor are detectable, so the wedge points INTO the
  // wind (opposite to plume travel).
  const upwind = windToRad + Math.PI;
  const reach = COVERAGE_REACH_M * SCALE;
  const half = (COVERAGE_HALF_ANGLE_DEG * Math.PI) / 180;
  const shape = useMemo(() => {
    const s = new THREE.Shape();
    s.moveTo(0, 0);
    const steps = 14;
    for (let i = 0; i <= steps; i++) {
      const a = -half + (2 * half * i) / steps;
      // Shape lies in XY; we rotate the mesh flat onto the ground.
      s.lineTo(Math.sin(a) * reach, Math.cos(a) * reach);
    }
    s.lineTo(0, 0);
    return s;
  }, [reach, half]);

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, -upwind]} position={[0, 0.015, 0]}>
        <shapeGeometry args={[shape]} />
        <meshBasicMaterial color={PALETTE.normal} transparent opacity={0.16} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.012, 0]}>
        <circleGeometry args={[NEARFIELD_RADIUS_M * SCALE, 32]} />
        <meshBasicMaterial color={PALETTE.normal} transparent opacity={0.22} depthWrite={false} />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Plume: particles advected downwind from the source
// ---------------------------------------------------------------------------

function Plume({
  source,
  windToRad,
  windSpeed,
  intensity,
}: {
  source: [number, number, number];
  windToRad: number;
  windSpeed: number;
  intensity: number;
}) {
  const COUNT = 260;
  const ref = useRef<THREE.Points>(null);
  const state = useMemo(() => {
    const life = new Float32Array(COUNT);
    const seed = new Float32Array(COUNT * 2);
    for (let i = 0; i < COUNT; i++) {
      life[i] = Math.random();
      seed[i * 2] = Math.random() * 2 - 1;
      seed[i * 2 + 1] = Math.random() * 2 - 1;
    }
    return { life, seed };
  }, []);
  const positions = useMemo(() => new Float32Array(COUNT * 3), []);

  useFrame((_, delta) => {
    if (!ref.current) return;
    const dirX = Math.sin(windToRad);
    const dirZ = -Math.cos(windToRad);
    const px = -dirZ, pz = dirX;
    const speed = Math.max(0.6, windSpeed * 0.35);
    const attr = ref.current.geometry.getAttribute("position") as THREE.BufferAttribute;
    for (let i = 0; i < COUNT; i++) {
      state.life[i] += delta * 0.18;
      if (state.life[i] > 1) state.life[i] -= 1;
      const t = state.life[i];
      const dist = t * speed * 6;
      const spread = 0.15 + dist * 0.28;
      const lateral = state.seed[i * 2] * spread;
      const rise = 0.9 + t * 1.4 + state.seed[i * 2 + 1] * spread * 0.5;
      attr.setXYZ(i, source[0] + dirX * dist + px * lateral, source[1] + rise, source[2] + dirZ * dist + pz * lateral);
    }
    attr.needsUpdate = true;
    (ref.current.material as THREE.PointsMaterial).opacity = 0.15 + 0.55 * intensity;
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={positions} count={COUNT} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial color={PALETTE.red} size={0.22} transparent opacity={0.5} sizeAttenuation depthWrite={false} />
    </points>
  );
}

function WindArrow({ windToRad, speed }: { windToRad: number; speed: number }) {
  const len = 1.2 + Math.min(speed, 8) * 0.15;
  return (
    <group position={[-6.2, 0.1, 5.4]} rotation={[0, -windToRad, 0]}>
      <mesh position={[0, 0, -len / 2]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.04, 0.04, len, 8]} />
        <meshStandardMaterial color={PALETTE.blue} />
      </mesh>
      <mesh position={[0, 0, -len]} rotation={[-Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.16, 0.4, 12]} />
        <meshStandardMaterial color={PALETTE.blue} />
      </mesh>
      <Html position={[0, 0.5, 0]} center distanceFactor={12} style={{ pointerEvents: "none" }}>
        <div style={{ ...labelStyle, fontSize: 10, fontWeight: 700, color: PALETTE.blue }}>WIND</div>
      </Html>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Attribution overlay: evidence lines + score labels + leader plume cone
// ---------------------------------------------------------------------------

function AttributionOverlay({
  candidates,
  byTag,
  detectingSensors,
  windToRad,
}: {
  candidates: Candidate[];
  byTag: Map<string, FacilityDetail["equipment"][number]>;
  detectingSensors: { tag: string; pos: [number, number, number] }[];
  windToRad: number;
}) {
  const shown = candidates.slice(0, 4);
  const leader = shown[0];
  const leaderEq = leader ? byTag.get(leader.tag) : undefined;

  return (
    <group>
      {shown.map((c, i) => {
        const eq = byTag.get(c.tag);
        if (!eq) return null;
        const from = toScene(eq.x_m, eq.y_m);
        const isLeader = i === 0;
        const color = isLeader ? PALETTE.red : PALETTE.steel;
        const alpha = isLeader ? 0.9 : Math.max(0.18, c.score_pct / 100);
        return (
          <group key={c.equipment_id}>
            {detectingSensors.map((s) => (
              <Line
                key={s.tag}
                points={[[from[0], 0.6, from[2]], [s.pos[0], 1.05, s.pos[2]]]}
                color={color}
                lineWidth={isLeader ? 2.2 : 1}
                transparent
                opacity={alpha}
                dashed={!isLeader}
                dashSize={0.18}
                gapSize={0.12}
              />
            ))}
            <Html position={[from[0], 2.15, from[2]]} center distanceFactor={12} style={{ pointerEvents: "none" }}>
              <div
                style={{
                  ...labelStyle,
                  background: isLeader ? PALETTE.red : "rgba(255,255,255,0.94)",
                  color: isLeader ? "#fff" : PALETTE.green,
                  border: `1px solid ${isLeader ? PALETTE.red : "#d9cdbb"}`,
                  borderRadius: 999,
                  padding: "3px 10px",
                  fontSize: 12,
                  fontWeight: 800,
                  boxShadow: "0 1px 3px rgba(29,69,51,0.15)",
                }}
              >
                {c.tag} {c.score_pct.toFixed(0)}%
              </div>
            </Html>
          </group>
        );
      })}

      {leaderEq && (
        <mesh
          position={(() => {
            const p = toScene(leaderEq.x_m, leaderEq.y_m);
            const len = 3.4;
            return [p[0] + Math.sin(windToRad) * (len / 2), 0.55, p[2] - Math.cos(windToRad) * (len / 2)];
          })()}
          rotation={[Math.PI / 2, 0, -windToRad + Math.PI]}
        >
          <coneGeometry args={[0.9, 3.4, 24, 1, true]} />
          <meshBasicMaterial color={PALETTE.red} transparent opacity={0.09} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      )}
    </group>
  );
}

// ---------------------------------------------------------------------------
// Scene
// ---------------------------------------------------------------------------

function Scene({
  facility,
  leaderTag,
  frame,
  eventLive,
  plumeIntensity,
  showCoverage,
  showAttribution,
  candidates,
  selectedTag,
  onSelect,
}: {
  facility: FacilityDetail;
  leaderTag: string | null;
  frame: TwinFrame;
  eventLive: boolean;
  plumeIntensity: number;
  showCoverage: boolean;
  showAttribution: boolean;
  candidates: Candidate[];
  selectedTag: string | null;
  onSelect: (tag: string | null) => void;
}) {
  const windToDeg = (frame.wind_dir_deg + 180) % 360;
  const windToRad = (windToDeg * Math.PI) / 180;

  const byTag = useMemo(() => {
    const m = new Map<string, FacilityDetail["equipment"][number]>();
    facility.equipment.forEach((e) => m.set(e.tag, e));
    return m;
  }, [facility]);

  const source = byTag.get(leaderTag ?? "C-03") ?? byTag.get("C-03");

  const detectingSensors = useMemo(
    () =>
      facility.sensors
        .filter((s) => (frame.sensors.get(s.tag) ?? s.baseline_ppm) - s.baseline_ppm > 0.8 || ["S3", "S4"].includes(s.tag))
        .filter((s) => ["S3", "S4"].includes(s.tag))
        .map((s) => ({ tag: s.tag, pos: toScene(s.x_m, s.y_m) })),
    [facility, frame],
  );

  return (
    <>
      <ambientLight intensity={0.75} />
      <directionalLight position={[8, 12, 6]} intensity={1.1} castShadow />
      <directionalLight position={[-6, 6, -4]} intensity={0.35} />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]} receiveShadow onClick={() => onSelect(null)}>
        <planeGeometry args={[16, 16]} />
        <meshStandardMaterial color={showCoverage ? "#e6d9c6" : PALETTE.cream} />
      </mesh>
      <Grid
        position={[0, 0, 0]}
        args={[16, 16]}
        cellSize={0.5}
        cellThickness={0.5}
        cellColor="#e0d6c7"
        sectionSize={2.5}
        sectionThickness={0.9}
        sectionColor="#d3c6b3"
        fadeDistance={22}
        infiniteGrid={false}
      />

      {PIPELINES.map(([a, b]) => {
        const ea = byTag.get(a), eb = byTag.get(b);
        if (!ea || !eb) return null;
        const pa = toScene(ea.x_m, ea.y_m), pb = toScene(eb.x_m, eb.y_m);
        return <Line key={`${a}-${b}`} points={[[pa[0], 0.25, pa[2]], [pb[0], 0.25, pb[2]]]} color="#b8ab98" lineWidth={2.5} />;
      })}

      {showCoverage &&
        facility.sensors.map((s) => (
          <group key={`cov-${s.id}`} position={toScene(s.x_m, s.y_m)}>
            <CoverageWedge windToRad={windToRad} />
          </group>
        ))}

      {facility.equipment.map((eq) => {
        const pos = toScene(eq.x_m, eq.y_m);
        const isLeader = leaderTag === eq.tag;
        const isSelected = selectedTag === eq.tag;
        return (
          <group
            key={eq.id}
            position={pos}
            onClick={(e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onSelect(eq.tag); }}
            onPointerOver={() => (document.body.style.cursor = "pointer")}
            onPointerOut={() => (document.body.style.cursor = "default")}
          >
            <EquipmentModel type={eq.type} highlight={isLeader} />
            {isLeader && <PulseRing color={PALETTE.red} />}
            {isSelected && !isLeader && <PulseRing color={PALETTE.blue} radius={0.9} />}
            {isSelected && isLeader && <PulseRing color={PALETTE.blue} radius={1.3} />}
            {!showAttribution && (
              <Html position={[0, 1.55, 0]} center distanceFactor={12} style={{ pointerEvents: "none" }}>
                <div
                  style={{
                    ...labelStyle,
                    background: isLeader ? PALETTE.red : "rgba(255,255,255,0.92)",
                    color: isLeader ? "#fff" : PALETTE.green,
                    border: `1px solid ${isLeader ? PALETTE.red : "#d9cdbb"}`,
                    borderRadius: 6,
                    padding: "2px 8px",
                    fontSize: 11,
                    fontWeight: 700,
                  }}
                >
                  {eq.tag}
                  <span style={{ fontWeight: 500, opacity: 0.8, marginLeft: 6, fontSize: 10 }}>{eq.operating_state}</span>
                </div>
              </Html>
            )}
          </group>
        );
      })}

      {facility.sensors.map((s) => {
        const pos = toScene(s.x_m, s.y_m);
        const raw = frame.sensors.get(s.tag);
        const ppm = raw === undefined || Number.isNaN(raw) ? s.baseline_ppm : raw;
        const color = sevColor(ppm, s.baseline_ppm);
        const elevated = ppm - s.baseline_ppm > 0.8;
        return (
          <group key={s.id} position={pos}>
            <SensorPost color={color} elevated={elevated} ppm={ppm} tag={s.tag} />
          </group>
        );
      })}

      {eventLive && source && (
        <Plume source={toScene(source.x_m, source.y_m)} windToRad={windToRad} windSpeed={frame.wind_speed_ms} intensity={plumeIntensity} />
      )}

      {showAttribution && candidates.length > 0 && (
        <AttributionOverlay candidates={candidates} byTag={byTag} detectingSensors={detectingSensors} windToRad={windToRad} />
      )}

      <WindArrow windToRad={windToRad} speed={frame.wind_speed_ms} />

      <OrbitControls enablePan minDistance={4} maxDistance={22} maxPolarAngle={Math.PI / 2.15} target={[0, 0.3, 0]} />
    </>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export function Schematic3D({
  height = 520,
  frameOverride = null,
  showCoverage = false,
  showAttribution = false,
  forceAttribution = false,
  selectedTag = null,
  onSelect,
}: {
  height?: number;
  /** When provided (replay), drives the scene instead of the live socket. */
  frameOverride?: TwinFrame | null;
  showCoverage?: boolean;
  showAttribution?: boolean;
  /** Replay sets this once the scrubber passes the attribution milestone. */
  forceAttribution?: boolean;
  selectedTag?: string | null;
  onSelect?: (tag: string | null) => void;
}) {
  const demo = useDemo();
  const [facility, setFacility] = useState<FacilityDetail | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [internalSelected, setInternalSelected] = useState<string | null>(null);

  const selected = selectedTag ?? internalSelected;
  const select = onSelect ?? setInternalSelected;

  useEffect(() => {
    api.get<FacilityDetail>(`/api/facilities/${FACILITY_ID}`).then(setFacility).catch(() => {});
  }, []);

  const attributionStages = ["attributed", "quantified", "prioritised", "investigated", "recommended", "work_order", "repaired", "verifying", "avoided"];
  const liveAttributed = !!demo.currentStageKey && attributionStages.includes(demo.currentStageKey);

  useEffect(() => {
    if (!demo.eventId) { setCandidates([]); return; }
    api.get<{ candidates: Candidate[] }>(`/api/events/${demo.eventId}/candidates`)
      .then((d) => setCandidates(d.candidates))
      .catch(() => {});
  }, [demo.eventId, demo.currentStageKey]);

  const liveFrame = useMemo<TwinFrame>(() => {
    const m = new Map<string, number>();
    demo.lastTick?.sensors.forEach((s) => m.set(s.tag, s.ch4_ppm));
    return {
      sensors: m,
      wind_speed_ms: demo.lastTick?.weather.wind_speed_ms ?? 5.1,
      wind_dir_deg: demo.lastTick?.weather.wind_dir_deg ?? 315,
      pressure_barg: demo.lastTick?.pressure_barg ?? null,
      flow_kg_h: demo.lastTick?.flow_kg_h ?? null,
    };
  }, [demo.lastTick]);

  const frame = frameOverride ?? liveFrame;

  // In replay the leader is only revealed once the scrubber reaches the
  // attribution milestone; live, once the backend says so.
  const attributionVisible = frameOverride ? forceAttribution : liveAttributed;
  const leaderTag = attributionVisible && candidates.length ? candidates[0].tag : null;

  const plumeIntensity = useMemo(() => {
    if (!facility) return 0;
    let maxExcess = 0;
    facility.sensors.forEach((s) => {
      const ppm = frame.sensors.get(s.tag);
      if (ppm !== undefined && !Number.isNaN(ppm)) maxExcess = Math.max(maxExcess, ppm - s.baseline_ppm);
    });
    return Math.min(1, maxExcess / 60);
  }, [facility, frame]);
  const eventLive = plumeIntensity > 0.02;

  return (
    <div className="relative overflow-hidden" style={{ height, borderRadius: 12, border: "1px solid var(--border)", background: "#F1E9DE" }}>
      <div className="absolute rounded-xl bg-white flex items-center gap-2.5 px-3.5 py-2.5 z-10" style={{ top: 14, left: 14, boxShadow: "var(--shadow)" }}>
        <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>Wind</span>
        <span style={{ fontSize: 13, fontWeight: 700 }}>
          {frame.wind_speed_ms.toFixed(1)} m/s @ {Math.round(frame.wind_dir_deg)}°
        </span>
        {frameOverride && <span className="tag-simulated" style={{ marginLeft: 6 }}>REPLAY</span>}
      </div>

      {showCoverage && (
        <div className="absolute rounded-xl bg-white px-3.5 py-2.5 z-10" style={{ top: 14, right: 14, boxShadow: "var(--shadow)", fontSize: 11.5, maxWidth: 240 }}>
          <div style={{ fontWeight: 700, color: "var(--normal-green)", marginBottom: 3 }}>Sensor coverage — current wind</div>
          <div style={{ color: "var(--text-muted)", lineHeight: 1.45 }}>
            Green wedges: sources a sensor can see upwind ({COVERAGE_REACH_M} m reach, ±{COVERAGE_HALF_ANGLE_DEG}°). Uncovered ground = a leak there could be missed under this wind.
          </div>
        </div>
      )}

      <div className="absolute rounded-xl bg-white px-3.5 py-2 z-10" style={{ bottom: 14, left: 14, boxShadow: "var(--shadow)", fontSize: 11, color: "var(--text-muted)" }}>
        Drag to orbit · scroll to zoom · click equipment to inspect
      </div>

      {facility && (
        <Canvas shadows camera={{ position: [7.5, 6.5, 9], fov: 42 }} dpr={[1, 1.75]} gl={{ antialias: true }}>
          <color attach="background" args={["#F1E9DE"]} />
          <fog attach="fog" args={["#F1E9DE", 18, 30]} />
          <Scene
            facility={facility}
            leaderTag={leaderTag}
            frame={frame}
            eventLive={eventLive}
            plumeIntensity={plumeIntensity}
            showCoverage={showCoverage}
            showAttribution={showAttribution && attributionVisible}
            candidates={candidates}
            selectedTag={selected}
            onSelect={select}
          />
        </Canvas>
      )}
    </div>
  );
}
