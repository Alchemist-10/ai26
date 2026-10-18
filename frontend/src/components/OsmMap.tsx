import { useEffect, useMemo, useRef, useState } from "react"
import { LocateFixed, Minus, Plus } from "lucide-react"
import { cn } from "@/lib/utils"

export interface MapPoint {
  id: string
  lat: number
  lon: number
  label?: string
  detail?: string
  color?: string
  active?: boolean
  size?: number
}

export interface MapLine {
  id: string
  points: [number, number][]
  color: string
  width?: number
  opacity?: number
  dashed?: boolean
}

const CENTER = { lat: 9.9736, lon: 76.3005 }
const DEFAULT_ZOOM = 12
const TILE_SIZE = 256

function worldPosition(lat: number, lon: number, zoom: number) {
  const scale = TILE_SIZE * 2 ** zoom
  const x = ((lon + 180) / 360) * scale
  const sin = Math.sin((lat * Math.PI) / 180)
  const y = (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale
  return { x, y }
}

export function OsmMap({
  points,
  lines = [],
  onPointClick,
  className,
  ariaLabel = "OpenStreetMap of Kochi camera locations",
}: {
  points: MapPoint[]
  lines?: MapLine[]
  onPointClick?: (id: string) => void
  className?: string
  ariaLabel?: string
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [zoom, setZoom] = useState(DEFAULT_ZOOM)
  const [center, setCenter] = useState(CENTER)

  useEffect(() => {
    const node = containerRef.current
    if (!node) return
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height })
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const viewport = useMemo(() => {
    const centerPx = worldPosition(center.lat, center.lon, zoom)
    return { left: centerPx.x - size.width / 2, top: centerPx.y - size.height / 2 }
  }, [center, size, zoom])
  const tiles = useMemo(() => {
    const minX = Math.floor(viewport.left / TILE_SIZE) - 1
    const maxX = Math.floor((viewport.left + size.width) / TILE_SIZE) + 1
    const minY = Math.floor(viewport.top / TILE_SIZE) - 1
    const maxY = Math.floor((viewport.top + size.height) / TILE_SIZE) + 1
    const count = 2 ** zoom
    return Array.from({ length: Math.max(0, maxX - minX + 1) * Math.max(0, maxY - minY + 1) }, (_, index) => {
      const x = minX + (index % (maxX - minX + 1))
      const y = minY + Math.floor(index / (maxX - minX + 1))
      return { x, y, wrappedX: ((x % count) + count) % count }
    }).filter((tile) => tile.y >= 0 && tile.y < count)
  }, [size, viewport, zoom])

  return (
    <div ref={containerRef} className={cn("relative isolate overflow-hidden bg-[#dce8e5]", className)}>
      {tiles.map((tile) => (
        <img
          key={`${tile.x}-${tile.y}-${zoom}`}
          src={`https://tile.openstreetmap.org/${zoom}/${tile.wrappedX}/${tile.y}.png`}
          alt=""
          aria-hidden="true"
          className="pointer-events-none absolute max-w-none"
          style={{ left: tile.x * TILE_SIZE - viewport.left, top: tile.y * TILE_SIZE - viewport.top, width: TILE_SIZE, height: TILE_SIZE }}
        />
      ))}
      {size.width > 0 && (
        <svg viewBox={`0 0 ${size.width} ${size.height}`} className="absolute inset-0 h-full w-full" aria-label={ariaLabel} role="img">
          {lines.map((line) => (
            <polyline
              key={line.id}
              points={line.points
                .map(([lat, lon]) => {
                  const position = worldPosition(lat, lon, zoom)
                  return `${position.x - viewport.left},${position.y - viewport.top}`
                })
                .join(" ")}
              fill="none"
              stroke={line.color}
              strokeWidth={line.width ?? 7}
              strokeDasharray={line.dashed ? "8 6" : undefined}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={line.opacity ?? 0.85}
            />
          ))}
          {points.map((point) => {
            const position = worldPosition(point.lat, point.lon, zoom)
            const x = position.x - viewport.left
            const y = position.y - viewport.top
            const active = point.active
            const color = point.color ?? (active ? "#ff5c72" : "#22d3c8")
            return (
              <g
                key={point.id}
                transform={`translate(${x},${y})`}
                className={cn(onPointClick && "cursor-pointer")}
                onClick={() => onPointClick?.(point.id)}
                role={onPointClick ? "button" : undefined}
                tabIndex={onPointClick ? 0 : undefined}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") onPointClick?.(point.id)
                }}
              >
                {active && <circle r={(point.size ?? 7) + 8} fill="none" stroke={color} strokeWidth="2" opacity="0.75" />}
                <circle r={point.size ?? 7} fill={color} stroke="#071017" strokeWidth="2.5" />
                <circle r="2" fill="#071017" opacity="0.8" />
                {point.label && (
                  <g transform={`translate(0,-${(point.size ?? 7) + 10})`}>
                    <rect x={-24} y={-10} width={48} height={15} rx={3} fill="#071017" opacity="0.86" />
                    <text textAnchor="middle" y="1" fill="#e6edf3" className="font-mono text-[8px] font-semibold">{point.label}</text>
                  </g>
                )}
                <title>{[point.label, point.detail].filter(Boolean).join(" · ") || point.id}</title>
              </g>
            )
          })}
        </svg>
      )}
      <div className="absolute right-3 top-3 flex flex-col overflow-hidden rounded-md border border-black/15 bg-[#071017]/90 shadow-lg backdrop-blur-sm">
        <button type="button" aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(16, value + 1))} className="p-2 text-white hover:bg-white/10"><Plus className="h-4 w-4" /></button>
        <button type="button" aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(9, value - 1))} className="border-t border-white/10 p-2 text-white hover:bg-white/10"><Minus className="h-4 w-4" /></button>
        <button type="button" aria-label="Reset map view" onClick={() => { setZoom(DEFAULT_ZOOM); setCenter(CENTER) }} className="border-t border-white/10 p-2 text-white hover:bg-white/10"><LocateFixed className="h-4 w-4" /></button>
      </div>
      <div className="absolute bottom-2 left-2 rounded bg-[#071017]/85 px-2 py-1 text-[9px] text-white/80 backdrop-blur-sm">© OpenStreetMap contributors</div>
    </div>
  )
}
