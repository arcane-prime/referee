"use client";

import { CSSProperties, PointerEvent, ReactNode, useCallback, useRef, useState } from "react";

const MIN_PERCENT = 25;
const MAX_PERCENT = 75;
const KEYBOARD_STEP = 2;

function clamp(percent: number): number {
  return Math.min(MAX_PERCENT, Math.max(MIN_PERCENT, percent));
}

export default function SplitPane({
  left,
  right,
  initialPercent = 62,
  leftLabel,
  rightLabel,
}: {
  left: ReactNode;
  right: ReactNode;
  initialPercent?: number;
  leftLabel: string;
  rightLabel: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [percent, setPercent] = useState(() => clamp(initialPercent));
  const [dragging, setDragging] = useState(false);

  const trackPointer = useCallback((clientX: number) => {
    const container = containerRef.current;
    if (!container) return;

    const bounds = container.getBoundingClientRect();
    if (bounds.width === 0) return;

    setPercent(clamp(((clientX - bounds.left) / bounds.width) * 100));
  }, []);

  const onPointerDown = useCallback((event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
  }, []);

  const onPointerMove = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (!dragging) return;
      trackPointer(event.clientX);
    },
    [dragging, trackPointer],
  );

  const onPointerUp = useCallback((event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDragging(false);
  }, []);

  const onKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setPercent((current) => clamp(current - KEYBOARD_STEP));
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      setPercent((current) => clamp(current + KEYBOARD_STEP));
    }
  }, []);

  return (
    <div
      ref={containerRef}
      className={`split${dragging ? " split--dragging" : ""}`}
      style={{ "--split-left": `${percent}%` } as CSSProperties}
    >
      <div className="split__pane split__pane--left" aria-label={leftLabel}>
        {left}
      </div>

      <div
        className="split__divider"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panels"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={MIN_PERCENT}
        aria-valuemax={MAX_PERCENT}
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onKeyDown={onKeyDown}
      >
        <span className="split__grip" aria-hidden="true" />
      </div>

      <div className="split__pane split__pane--right" aria-label={rightLabel}>
        {right}
      </div>
    </div>
  );
}

/*
 Notes

 The two panes scroll independently rather than the page scrolling as a whole.
 That is the entire point: the parse and the review are read against each
 other, and a single column forces a scroll between every comparison.

 Width lives in a CSS custom property rather than in inline flex-basis so the
 narrow-viewport media query can drop back to a stacked layout by overriding
 one rule. An inline flex-basis would win over the media query and would have
 to be fought with !important.

 Pointer events are used instead of mouse events so a trackpad, a touchscreen
 and a pen all work from one code path. setPointerCapture is what makes the
 drag survive the cursor leaving the divider, which is otherwise the standard
 bug in a hand-rolled splitter: move fast and the pane stops following.

 The divider is focusable and responds to the arrow keys because a control
 that only answers to a drag cannot be operated without a pointing device. It
 carries separator semantics with a value so a screen reader can report the
 current position rather than an unlabelled div.

 Clamping to 25-75% keeps either pane from being dragged to nothing. A pane
 collapsed to zero looks like a rendering fault and there is no visible handle
 left to recover it with.
*/
