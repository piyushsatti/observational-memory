// observational-memory for OpenCode 2: a thin plugin over `$HOME/.local/bin/observational-memory`.
//
// OpenCode 2 plugins default-export {id, setup(ctx)} (https://opencode.ai/v2/docs/build/plugins/).
// No imports from @opencode/plugin, so the file needs no package.json or install step.
//
// - Turn end (session.execution.succeeded, or session.idle): the session's messages from
//   ctx.session.context go to `observational-memory hook opencode stop` on stdin; it mirrors them to an
//   append-only JSONL and starts the observer, detached.
// - Compaction: the session "compaction" hook runs before the summary model call. `hook opencode
//   compacting` catches the observer up and answers {"context": notes}; the notes are pushed onto the
//   compaction's system prompt, so they go into the summary input. A child session (a subagent's)
//   sends its parent's id at turn end and compaction alike; its notes go to the parent's ledger.
// - `recall`: a plugin tool that runs `observational-memory recall <id>`.
// - Recursion guard: the observer's model call (`opencode run --standalone`) runs with
//   OBSERVATIONAL_MEMORY_CHILD=1, which its private server inherits; there this plugin registers nothing.

import { spawn, spawnSync } from "node:child_process"
import { homedir } from "node:os"
import { join } from "node:path"

const BIN = join(process.env.HOME || homedir(), ".local", "bin", "observational-memory")
const TURN_END = new Set(["session.execution.succeeded", "session.idle"])

// Runs the script with `input` on stdin; resolves {code, stdout}, never rejects.
function run(args, input, timeoutMs) {
  return new Promise((resolve) => {
    let stdout = ""
    let done = false
    const finish = (code) => {
      if (done) return
      done = true
      clearTimeout(timer)
      resolve({ code, stdout })
    }
    let child
    try {
      child = spawn(BIN, args, { stdio: ["pipe", "pipe", "ignore"] })
    } catch {
      return resolve({ code: -1, stdout: "" })
    }
    const timer = setTimeout(() => {
      try {
        child.kill()
      } catch {}
      finish(-1)
    }, timeoutMs)
    child.on("error", () => finish(-1))
    child.on("close", (code) => finish(code))
    child.stdout.on("data", (d) => (stdout += d))
    child.stdin.on("error", () => {})
    child.stdin.end(input ?? "")
  })
}

function sessionOf(event) {
  const p = event.properties ?? event.data ?? {}
  return p.sessionID ?? event.sessionID
}

export default {
  id: "observational-memory",
  async setup(ctx) {
    if (process.env.OBSERVATIONAL_MEMORY_CHILD) return
    const here = ctx.location?.directory

    const messages = async (sessionID) => {
      try {
        return await ctx.session.context({ sessionID })
      } catch {
        return []
      }
    }
    const parentOf = async (sessionID) => {
      try {
        const s = await ctx.session.get({ sessionID })
        return s?.parentID ?? s?.parent?.id ?? null
      } catch {
        return null
      }
    }

    const busy = new Set()
    const turnEnd = async (sessionID) => {
      if (busy.has(sessionID)) return
      busy.add(sessionID)
      try {
        const payload = {
          session_id: sessionID,
          parent_session_id: await parentOf(sessionID),
          directory: here,
          messages: await messages(sessionID),
        }
        // Synchronous: OpenCode does not wait on this subscription, and `opencode run` shuts its server
        // down right after the turn, which could cut an async pipe off mid-payload. The script only
        // mirrors the messages and starts the observer detached, so the block is short.
        try {
          spawnSync(BIN, ["hook", "opencode", "stop"], {
            input: JSON.stringify(payload),
            stdio: ["pipe", "ignore", "ignore"],
            timeout: 30_000,
          })
        } catch {}
      } finally {
        busy.delete(sessionID)
      }
    }

    const controller = new AbortController()
    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          if (!TURN_END.has(event.type)) continue
          const where = event.location?.directory
          if (where && here && where !== here) continue // another location's plugin instance has it
          const sessionID = sessionOf(event)
          if (sessionID) void turnEnd(sessionID)
        }
      } catch {}
    })()

    await ctx.session.hook("compaction", async (event) => {
      const payload = {
        session_id: event.sessionID,
        parent_session_id: await parentOf(event.sessionID),
        directory: here,
        messages: await messages(event.sessionID),
      }
      const { stdout } = await run(["hook", "opencode", "compacting"], JSON.stringify(payload), 120_000)
      try {
        const out = JSON.parse(stdout || "{}")
        if (out.context) event.system.push({ type: "text", text: out.context })
      } catch {}
    })

    await ctx.tool.transform((editor) => {
      editor.add({
        name: "recall",
        description:
          "Return the exact transcript lines behind a memory id (the 12-character hex id in brackets in observational-memory's notes). Use it when a note matters and its exact source is needed; it is not a search.",
        input: {
          type: "object",
          properties: { id: { type: "string", description: "The observation or reflection id, e.g. d4e5f6a1b2c3" } },
          required: ["id"],
          additionalProperties: false,
        },
        execute: async (input) => {
          const { stdout, code } = await run(["recall", String(input?.id ?? "")], "", 30_000)
          return { content: stdout.trim() || `observational-memory recall failed (exit ${code})` }
        },
      })
    })

    return () => controller.abort()
  },
}
