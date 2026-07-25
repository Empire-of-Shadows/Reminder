import { useEffect, useMemo, useRef, useState } from "react";
import type { Guild } from "../api/types";

const HUB_R = 34;
const NODE_R = 26;
const MARGIN = 64;

interface SimNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface Pt {
  x: number;
  y: number;
}

/** Hub spokes + a ring + a few chords, so the layout reads as a web. */
function buildLinks(ids: string[]): [string, string][] {
  const links: [string, string][] = ids.map((id) => ["hub", id]);
  const n = ids.length;
  if (n >= 3) {
    for (let i = 0; i < n; i++) links.push([ids[i], ids[(i + 1) % n]]);
  }
  if (n >= 5) {
    for (let i = 0; i < n; i++) links.push([ids[i], ids[(i + 2) % n]]);
  }
  return links;
}

/** Hand-rolled force-directed layout. No external deps. Hub is pinned at the
 *  centre; guild nodes repel each other, springs pull along links, and a mild
 *  gravity keeps the cloud centred. Cools over a few hundred rAF ticks. */
function useForceLayout(ids: string[], links: [string, string][], size: { w: number; h: number }) {
  const [positions, setPositions] = useState<Record<string, Pt>>({});
  const idsKey = ids.join("|");
  const linksKey = links.map((l) => l.join(">")).join("|");

  useEffect(() => {
    const { w, h } = size;
    if (w === 0 || h === 0) return;
    const cx = w / 2;
    const cy = h / 2;

    const nodes = new Map<string, SimNode>();
    nodes.set("hub", { id: "hub", x: cx, y: cy, vx: 0, vy: 0 });
    const ring = Math.min(w, h) * 0.32;
    ids.forEach((id, i) => {
      const a = (i / Math.max(1, ids.length)) * Math.PI * 2 + Math.random() * 0.6;
      const r = ring * (0.7 + Math.random() * 0.35);
      nodes.set(id, { id, x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r, vx: 0, vy: 0 });
    });

    const linkLen = Math.min(w, h) * 0.26;
    const kRep = Math.min(w, h) ** 2 * 0.05;
    const kSpring = 0.045;

    const applyForces = (alpha: number) => {
      const arr = [...nodes.values()];
      // Pairwise repulsion (~1/d^2).
      for (let i = 0; i < arr.length; i++) {
        for (let j = i + 1; j < arr.length; j++) {
          const a = arr[i];
          const b = arr[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const d2 = dx * dx + dy * dy || 0.01;
          const d = Math.sqrt(d2);
          const f = (kRep / d2) * alpha;
          const ux = dx / d;
          const uy = dy / d;
          a.vx += ux * f;
          a.vy += uy * f;
          b.vx -= ux * f;
          b.vy -= uy * f;
        }
      }
      // Link springs toward rest length.
      for (const [s, t] of links) {
        const a = nodes.get(s);
        const b = nodes.get(t);
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const f = kSpring * (d - linkLen) * alpha;
        const ux = dx / d;
        const uy = dy / d;
        a.vx += ux * f;
        a.vy += uy * f;
        b.vx -= ux * f;
        b.vy -= uy * f;
      }
      // Integrate, damp, centre-gravity; hub stays pinned; clamp to bounds.
      for (const n of arr) {
        if (n.id === "hub") {
          n.x = cx;
          n.y = cy;
          n.vx = 0;
          n.vy = 0;
          continue;
        }
        n.vx += (cx - n.x) * 0.0025 * alpha;
        n.vy += (cy - n.y) * 0.0025 * alpha;
        n.vx *= 0.85;
        n.vy *= 0.85;
        n.x += n.vx;
        n.y += n.vy;
        n.x = Math.max(MARGIN, Math.min(w - MARGIN, n.x));
        n.y = Math.max(MARGIN, Math.min(h - MARGIN, n.y));
      }
    };

    const snapshot = (): Record<string, Pt> => {
      const snap: Record<string, Pt> = {};
      for (const n of nodes.values()) snap[n.id] = { x: n.x, y: n.y };
      return snap;
    };

    // Reduced motion: settle synchronously and paint once - no visible drift.
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      let a = 1;
      for (let k = 0; k < 400 && a > 0.02; k++) {
        applyForces(a);
        a *= 0.985;
      }
      setPositions(snapshot());
      return;
    }

    let alpha = 1;
    let raf = 0;
    const step = () => {
      applyForces(alpha);
      alpha *= 0.985;
      setPositions(snapshot());
      if (alpha > 0.02) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey, linksKey, size.w, size.h]);

  return positions;
}

function vinePath(a: Pt, b: Pt, idx: number): string {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const off = Math.min(40, len * 0.12) * (idx % 2 ? 1 : -1);
  const cx = mx + (-dy / len) * off;
  const cy = my + (dx / len) * off;
  return `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`;
}

function truncate(name: string, max = 14): string {
  return name.length > max ? name.slice(0, max - 1) + "…" : name;
}

export function GuildWeb({
  guilds,
  selectedId,
  onSelect,
}: {
  guilds: Guild[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 720, h: 520 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      if (r.width > 0 && r.height > 0) setSize({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const ids = useMemo(() => guilds.map((g) => g.id), [guilds]);
  const links = useMemo(() => buildLinks(ids), [ids]);
  const positions = useForceLayout(ids, links, size);

  const hub = positions["hub"] ?? { x: size.w / 2, y: size.h / 2 };

  return (
    <div className="guild-web" ref={ref}>
      <svg className="guild-web__svg" width={size.w} height={size.h} viewBox={`0 0 ${size.w} ${size.h}`} role="img" aria-label="Network of your servers">
        <defs>
          <clipPath id="gw-node-clip">
            <circle cx={0} cy={0} r={NODE_R} />
          </clipPath>
          <clipPath id="gw-hub-clip">
            <circle cx={0} cy={0} r={HUB_R} />
          </clipPath>
        </defs>

        <g className="guild-web__field">
          {/* Vines */}
          {links.map(([s, t], i) => {
            const a = positions[s];
            const b = positions[t];
            if (!a || !b) return null;
            const active = selectedId !== null && (s === selectedId || t === selectedId);
            return (
              <path
                key={`${s}>${t}`}
                className={"guild-web__vine" + (active ? " is-active" : "")}
                d={vinePath(a, b, i)}
                pathLength={1}
                style={{ animationDelay: `${Math.min(i * 0.04, 0.8)}s` }}
              />
            );
          })}

          {/* Hub */}
          <g className="guild-web__hub" transform={`translate(${hub.x} ${hub.y})`}>
            <circle className="guild-web__hub-halo" r={HUB_R + 10} />
            <circle r={HUB_R} fill="var(--bg-2)" />
            <image
              href="/brand/logo-mark.png"
              x={-HUB_R}
              y={-HUB_R}
              width={HUB_R * 2}
              height={HUB_R * 2}
              clipPath="url(#gw-hub-clip)"
              preserveAspectRatio="xMidYMid slice"
            />
            <circle r={HUB_R} className="guild-web__hub-ring" fill="none" />
          </g>

          {/* Guild nodes */}
          {guilds.map((g) => {
            const p = positions[g.id];
            if (!p) return null;
            const iconUrl = g.icon
              ? `https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png?size=64`
              : null;
            const selected = g.id === selectedId;
            const dim = selectedId !== null && !selected;
            const cls = [
              "guild-web__node",
              `guild-web__node--${g.panel_role}`,
              selected ? "is-selected" : "",
              dim ? "is-dim" : "",
              g.setup_required ? "is-setup" : "",
            ].filter(Boolean).join(" ");
            return (
              <g
                key={g.id}
                className={cls}
                transform={`translate(${p.x} ${p.y})`}
                onClick={() => onSelect(g.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect(g.id); }}
                aria-label={`${g.name} (${g.panel_role})`}
              >
                <circle r={NODE_R} className="guild-web__node-bg" />
                {iconUrl ? (
                  <image
                    href={iconUrl}
                    x={-NODE_R}
                    y={-NODE_R}
                    width={NODE_R * 2}
                    height={NODE_R * 2}
                    clipPath="url(#gw-node-clip)"
                    preserveAspectRatio="xMidYMid slice"
                  />
                ) : (
                  <text className="guild-web__node-initial" textAnchor="middle" dominantBaseline="central">
                    {(g.name ?? "?")[0]}
                  </text>
                )}
                <circle r={NODE_R} className="guild-web__node-ring" fill="none" />
                <text className="guild-web__node-label" y={NODE_R + 16} textAnchor="middle">
                  {truncate(g.name ?? "Unknown")}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
