import {
  boxesOverlap,
  circleIntersectsBox,
  placeLabels as placeLabelsJs,
} from "./graphLabelPlacer.js";

export interface LabelBBox {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface PlacedLabel {
  nodeId: number;
  text: string;
  x: number;
  y: number;
  position: "below" | "above";
  bbox: LabelBBox;
}

export interface NodeForPlacement {
  id: number;
  x?: number;
  y?: number;
  title: string;
  radius: number;
}

export interface PlaceLabelsOptions {
  nodes: NodeForPlacement[];
  candidateIds: number[];
  selectedId?: number | null;
  hoveredId?: number | null;
  maxLabels?: number;
  fontSize?: number;
  measureWidth?: (text: string) => number;
}

export { boxesOverlap, circleIntersectsBox };

export function placeLabels(options: PlaceLabelsOptions): Map<number, PlacedLabel> {
  return placeLabelsJs(options as any) as Map<number, PlacedLabel>;
}
