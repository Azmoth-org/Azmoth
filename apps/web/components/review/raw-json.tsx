/**
 * A raw JSON block. Used wherever the UI must show what it received without interpreting it —
 * proof steps, error details, unexpected response shapes.
 */

export function RawJson({ value, label }: { value: unknown; label?: string }) {
  let text: string
  try {
    text = JSON.stringify(value, null, 2) ?? String(value)
  } catch {
    text = String(value)
  }

  return (
    <div className="min-w-0">
      {label ? (
        <div className="mb-1 text-xs font-medium text-muted-foreground">
          {label}
        </div>
      ) : null}
      <pre className="max-h-96 overflow-auto rounded-lg border bg-muted/50 p-3 font-mono text-xs leading-relaxed text-foreground">
        {text}
      </pre>
    </div>
  )
}
