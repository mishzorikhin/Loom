// Сообщения сервера (tsim/server.py) и скомпилированная сеть (tsim/compiler.py: net_json).

export type P2 = [number, number];

export interface LinkJ {
  id: string;
  kind: "lane" | "conn";
  pts: P2[];
  len: number;
  w: number;
  speed: number;
  junction: string;
  group: string;
  movement: string;
  turns: string[];
  from: number;
  to: number;
  next: number[];
  conflicts: [string, number, number, string, string][]; // other, idx, s_self, kind, rule
}

export interface GroupJ {
  name: string;
  kind: "car" | "ped";
  links: number[];
  crosswalks: number[];
}

export interface JunctionJ {
  id: string;
  kind: "signal" | "midblock";
  pos: P2;
  groups: GroupJ[];
  phases: { id: string; green: string[] }[];
  bounds: Record<string, [number, number]>;
  safe: Record<string, number>;
  approaches: number[];
}

export interface NetJ {
  hash: string;
  name: string;
  links: LinkJ[];
  crosswalks: { id: string; junction: string; pts: P2[]; width: number; group: string; edge: number }[];
  sw_edges: { pts: P2[]; kind: string; cw: number }[];
  junctions: JunctionJ[];
  boundaries: Record<string, { pos: P2 }>;
  render: RenderJ;
}

export interface RenderJ {
  roads: { id: string; left: P2[]; right: P2[]; boundary: [boolean, boolean] }[];
  junctions: { id: string; pts: P2[] }[];
  sidewalks: { pts: P2[]; width: number; kind: string }[];
  medians: { pts: P2[]; width: number }[];
  lines: { pts: P2[]; style: "solid" | "dashed"; w: number }[];
  arrows: { pos: P2; dir: number; turns: string[] }[];
  stops: { pts: P2[]; w: number }[];
  zebras: { id: string; pts: P2[]; width: number }[];
  hatches: { pts: P2[]; width: number }[];
  heads: { junction: string; group: string; kind: "car" | "ped"; pos: P2; pole: P2; facing: number; movements?: string[] }[];
  bbox: [number, number, number, number];
}

export interface SceneryJ {
  buildings: { pos: P2; w: number; d: number; h: number; a: number; style: number; roof: number }[];
  trees: { pos: P2; r: number; kind: number }[];
  lamps: { pos: P2; a: number }[];
  ground: [number, number, number, number];
}

export interface SignalSnap {
  phase: number;
  stage: "green" | "change" | "all_red";
  t: number;
  green_t: number;
  target: number;
  dur: Record<string, number>;
  state: string;
}

export interface SimEvent {
  id: number;
  t: number;
  clock: string;
  kind: "crash" | "near_miss" | "red_run" | "jaywalk" | "stuck";
  pos: P2;
  sub?: string;
  cause?: string;
  cars?: number[];
  peds?: number[];
  junction?: string;
  value?: number;
}

export interface Metrics {
  cars: number;
  peds: number;
  spawned: number;
  done: number;
  travel: number;
  delay: number;
  stops: number;
  waiting: number;
  crashes: number;
  causes: Record<string, number>;
  near: Record<string, number>;
  red_runs: number;
  jaywalks: number;
  stuck: number;
  hard_brakes: number;
  peds_done: number;
  ped_wait: number;
  blocked_spawn: number;
}

export interface SeriesPoint {
  t: number;
  clock: string;
  done: number;
  crashes: number;
  near: number;
  delay: number;
  cars: number;
  peds: number;
}

export interface Settings {
  world: string;
  seed: number;
  controller: string;
  demand: number;
  peds: number;
  timing: number;
  block_box: boolean;
  start_hour: number;
}

// машина: id, путь, s, смещение перестроения, скорость, флаги, вид, цвет, причина, в пути с, ждёт с
export type CarRow = [number, number, number, number, number, number, number, number, number, number, number];
// пешеход: id, ребро, s по ребру, смещение, состояние, вид, цвет, направление
export type PedRow = [number, number, number, number, number, number, number, number];

export interface FrameMsg {
  type: "frame";
  t: number;
  clock: string;
  hour: number;
  cars: CarRow[];
  peds: PedRow[];
  signals: Record<string, SignalSnap>;
  events: SimEvent[];
  metrics: Metrics;
  series?: SeriesPoint[];
  run: { running: boolean; speed: number; effective: number; settings: Settings };
  full?: boolean;
}

export interface HelloMsg {
  type: "hello";
  worlds: { id: string; title: string }[];
  controllers: { id: string; title: string }[];
  speeds: number[];
  settings: Settings;
}

export interface NetMsg {
  type: "net";
  world: string;
  net: NetJ;
  scenery: SceneryJ;
}

export const FLAG = { BRAKE: 1, CRASH: 2, LEFT: 4, RIGHT: 8, DISTRACT: 16, RED_RUN: 32 } as const;
