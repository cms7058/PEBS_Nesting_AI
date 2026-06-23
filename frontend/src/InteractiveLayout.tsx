import type { KonvaEventObject } from "konva/lib/Node";
import { useEffect, useMemo, useState } from "react";
import { Layer, Line, Rect, Stage, Text } from "react-konva";
import { bbox, polysOverlap, type Pt } from "./geometry";

interface LayoutPart {
  id: string;
  points: Pt[];
  area: number;
}
interface LayoutData {
  sheet_width: number;
  used_length: number;
  utilization: number;
  parts: LayoutPart[];
}

// 内部表示：每个零件用「局部点(相对自身 bbox 原点)」+「位置(mm)」表达，方便拖拽。
interface Item {
  id: string;
  local: Pt[]; // 相对 (0,0)
  pos: Pt; // 板坐标偏移(mm)
  area: number;
}

const VIEW_W = 720; // 画布像素宽

export function InteractiveLayout({ data }: { data: LayoutData }) {
  const [items, setItems] = useState<Item[]>([]);
  const sheetW = data.sheet_width;

  useEffect(() => {
    setItems(
      data.parts.map((p) => {
        const b = bbox(p.points);
        return {
          id: p.id,
          local: p.points.map(([x, y]) => [x - b.minx, y - b.miny] as Pt),
          pos: [b.minx, b.miny] as Pt,
          area: p.area,
        };
      })
    );
  }, [data]);

  // 绝对多边形(mm)
  const absPolys = useMemo(
    () => items.map((it) => it.local.map(([x, y]) => [x + it.pos[0], y + it.pos[1]] as Pt)),
    [items]
  );

  // 实时利用率：用料板长 = 所有零件最大 y；利用率 = 总件面积 /(板宽 × 用料板长)
  const totalArea = useMemo(() => items.reduce((s, it) => s + it.area, 0), [items]);
  const usedLen = useMemo(() => {
    let m = 0;
    for (const poly of absPolys) for (const [, y] of poly) if (y > m) m = y;
    return m || 1;
  }, [absPolys]);
  const liveUtil = totalArea / (sheetW * usedLen);

  // 重叠 / 越界 标记
  const flags = useMemo(() => {
    const bad = new Array(items.length).fill(false);
    for (let i = 0; i < absPolys.length; i++) {
      const b = bbox(absPolys[i]);
      if (b.minx < 0 || b.maxx > sheetW || b.miny < 0) bad[i] = true; // 越界
      for (let j = i + 1; j < absPolys.length; j++) {
        if (polysOverlap(absPolys[i], absPolys[j])) {
          bad[i] = true;
          bad[j] = true;
        }
      }
    }
    return bad;
  }, [absPolys, sheetW]);

  const overlapCount = flags.filter(Boolean).length;

  const scale = VIEW_W / sheetW;
  const viewH = Math.max(usedLen * scale * 1.15, 200);
  const palette = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f"];

  return (
    <div>
      <div className="livebar">
        <span>
          实时利用率 <b style={{ color: overlapCount ? "#e15759" : "#59a14f" }}>
            {(liveUtil * 100).toFixed(1)}%
          </b>
        </span>
        <span>板长 {usedLen.toFixed(0)} mm</span>
        <span style={{ color: overlapCount ? "#e15759" : "#8b93a3" }}>
          {overlapCount ? `⚠ ${overlapCount} 件重叠/越界` : "✓ 无重叠"}
        </span>
      </div>
      <div className="canvaswrap">
        <Stage width={VIEW_W} height={viewH} scaleX={scale} scaleY={scale}>
          <Layer>
            <Rect x={0} y={0} width={sheetW} height={usedLen} fill="#ffffff"
              stroke="#333" strokeWidth={2 / scale} />
            {items.map((it, i) => (
              <Line
                key={it.id}
                x={it.pos[0]}
                y={it.pos[1]}
                points={it.local.flat()}
                closed
                fill={flags[i] ? "#e1575999" : palette[i % palette.length] + "cc"}
                stroke={flags[i] ? "#e15759" : "#222"}
                strokeWidth={(flags[i] ? 2 : 0.6) / scale}
                draggable
                onDragMove={(e: KonvaEventObject<DragEvent>) => {
                  const np = [...items];
                  np[i] = { ...np[i], pos: [e.target.x(), e.target.y()] };
                  setItems(np);
                }}
              />
            ))}
          </Layer>
          <Layer listening={false}>
            <Text x={2} y={2} text={`利用率 ${(liveUtil * 100).toFixed(1)}%`}
              fontSize={14 / scale} fill="#333" />
          </Layer>
        </Stage>
      </div>
      <p className="hint">拖动零件实时重排;红色表示重叠或越出板边。「重新自动排料」可恢复最优解。</p>
    </div>
  );
}
