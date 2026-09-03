import { useEffect, useRef } from "react";

/** Pipeline output, pinned to the newest line. */
export default function LogPanel({ logs }: { logs: string[] }) {
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [logs.length]);

  if (logs.length === 0) return null;

  return (
    <pre className="max-h-64 overflow-auto rounded border bg-muted p-3 text-xs whitespace-pre-wrap">
      {logs.map((line, index) => (
        <div key={`${index}-${line}`}>{line}</div>
      ))}
      <div ref={bottom} />
    </pre>
  );
}
