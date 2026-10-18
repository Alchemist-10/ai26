import { NLQueryChat } from "@/components/NLQueryChat"
import { MessageSquareText } from "lucide-react"

export function QueryPage() {
  return (
    <div className="h-full overflow-hidden bg-black font-sans text-white p-4 sm:p-6 flex flex-col items-center">
      <div className="mx-auto flex h-full max-w-3xl w-full flex-col gap-3">
        {/* Top Header Card */}
        <div className="flex flex-col gap-1 rounded-md border border-zinc-800 bg-zinc-950 p-4 flex-none">
          <div className="flex items-center gap-2">
            <MessageSquareText className="h-4 w-4 text-zinc-400" />
            <h1 className="text-sm font-semibold text-white tracking-wide">Ask the Grid</h1>
          </div>
          <p className="text-xs text-zinc-400 font-sans leading-relaxed">
            Query supported plate sightings, camera-local vehicle counts, camera activity, and configured rule alerts.
          </p>
        </div>

        {/* Chat Component Box */}
        <div className="min-h-0 flex-1 rounded-md border border-zinc-800 bg-zinc-950 p-4">
          <NLQueryChat />
        </div>
      </div>
    </div>
  )
}
