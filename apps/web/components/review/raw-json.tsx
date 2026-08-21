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
        <div className="text-muted-foreground mb-1 text-xs font-medium">{label}</div>
      ) : null}
      <pre className="bg-muted/50 text-foreground max-h-96 overflow-auto rounded-lg border p-3 font-mono text-xs leading-relaxed">
        {text}
      </pre>
    </div>
  )
}
