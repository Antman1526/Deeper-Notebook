import { BrainCircuit, RotateCcw } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { StudyCard } from '@/lib/types/study'

export function StudyDashboard({ cards }: { cards: StudyCard[] }) {
  const weakTopics = [...cards]
    .sort((left, right) => right.lapse_count - left.lapse_count)
    .filter((card) => card.lapse_count > 0)
    .slice(0, 3)

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card>
        <CardHeader className="flex-row items-center gap-2 space-y-0"><BrainCircuit className="h-4 w-4 text-primary" /><CardTitle className="text-sm">Due today</CardTitle></CardHeader>
        <CardContent><p className="text-3xl font-semibold">{cards.length}</p><p className="mt-1 text-xs text-muted-foreground">Evidence-backed cards ready for review.</p></CardContent>
      </Card>
      <Card>
        <CardHeader className="flex-row items-center gap-2 space-y-0"><RotateCcw className="h-4 w-4 text-amber-600" /><CardTitle className="text-sm">Weak topics</CardTitle></CardHeader>
        <CardContent>
          {weakTopics.length ? <ul className="space-y-1 text-sm">{weakTopics.map((card) => <li key={card.id} className="flex justify-between gap-3"><span className="truncate">{card.artifact_id}</span><span className="text-muted-foreground">{card.lapse_count} lapses</span></li>)}</ul> : <p className="text-sm text-muted-foreground">No repeat misses in the current due set.</p>}
        </CardContent>
      </Card>
    </div>
  )
}
