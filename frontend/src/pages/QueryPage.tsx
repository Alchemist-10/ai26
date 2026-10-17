import { NLQueryChat } from "@/components/NLQueryChat"
import { MessageSquareText } from "lucide-react"

export function QueryPage() {
  return (
    <div className="h-full overflow-hidden bg-[#08090d] text-zinc-100 p-4 sm:p-6 flex flex-col items-center select-none">
      <div className="mx-auto flex h-full max-w-3xl w-full flex-col gap-3.5">
        {/* Top Header Card */}
        <div className="flex flex-col gap-1 rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-4 flex-none backdrop-blur-md shadow-sm">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30">
              <MessageSquareText className="h-4 w-4" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-white tracking-tight">Detection Grid Query Engine</h1>
              <p className="text-[11px] text-zinc-400">
                Deterministic cross-camera sightings, spatial corridor metrics, and license plate lookups.
              </p>
            </div>
          </div>
        </div>

        {/* Chat Component Box */}
        <div className="min-h-0 flex-1 rounded-2xl border border-white/[0.08] bg-[#0c0e15]/90 p-4 backdrop-blur-md shadow-lg flex flex-col">
          <NLQueryChat />
        </div>
      </div>
    </div>
  )
}
