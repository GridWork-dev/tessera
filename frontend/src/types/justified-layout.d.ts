declare module 'justified-layout' {
  interface Opts {
    containerWidth?: number;
    containerPadding?: number | { top: number; right: number; bottom: number; left: number };
    boxSpacing?: number | { horizontal: number; vertical: number };
    targetRowHeight?: number;
    targetRowHeightTolerance?: number;
    maxNumRows?: number;
    forceAspectRatio?: boolean | number;
    showWidows?: boolean;
    fullWidthBreakoutRowCadence?: boolean | number;
  }
  interface Box {
    aspectRatio: number;
    top: number;
    left: number;
    width: number;
    height: number;
  }
  interface Result {
    containerHeight: number;
    widowCount: number;
    boxes: Box[];
  }
  export default function (
    input: number[] | { width: number; height: number }[],
    opts?: Opts,
  ): Result;
}
