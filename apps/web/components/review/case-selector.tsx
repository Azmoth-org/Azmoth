"use client"

import { PlayIcon } from "lucide-react"

import { Button } from "@workspace/ui/components/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"
import { Label } from "@workspace/ui/components/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@workspace/ui/components/select"

import { SYNTHETIC_CASES, type SyntheticCase } from "@/lib/fixtures"

/**
 * Pick one of the three synthetic fixtures and run it.
 *
 * These are the same files the engine's golden tests use, so the result on screen is the result the
 * test suite pins. There is no free-text and no file-upload path on purpose: only synthetic data may
 * enter this system.
 */
export function CaseSelector({
  selected,
  onSelect,
  onRun,
  pending,
}: {
  selected: SyntheticCase
  onSelect: (id: string) => void
  onRun: () => void
  pending: boolean
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Synthetischer Fall</CardTitle>
        <CardDescription>
          Fixtures aus <span className="font-mono text-xs">logic/tests/cases/</span> — dieselben
          Fälle, gegen die die Golden-Tests der Engine laufen.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-72 space-y-2">
            <Label htmlFor="case-select">Fall</Label>
            <Select
              value={selected.id}
              onValueChange={(value) => {
                if (typeof value === "string") onSelect(value)
              }}
            >
              {/*
                The trigger label is rendered from the controlled value rather than through
                `<SelectValue />`. The primitive resolves its label on the client only — neither a
                children function nor the `items` prop changed that — so the server render, and
                therefore the first paint, showed the raw id ("case_001_knee") instead of the case
                name. Rendering it here removes that gap entirely.
              */}
              <SelectTrigger id="case-select" className="w-full">
                <span className="flex-1 text-left">{selected.label}</span>
              </SelectTrigger>
              <SelectContent>
                {SYNTHETIC_CASES.map((entry) => (
                  <SelectItem key={entry.id} value={entry.id}>
                    {entry.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button onClick={onRun} disabled={pending}>
            <PlayIcon />
            {pending ? "Engine läuft…" : "Engine ausführen"}
          </Button>
        </div>

        <p className="text-muted-foreground text-sm">{selected.description}</p>
      </CardContent>
    </Card>
  )
}
