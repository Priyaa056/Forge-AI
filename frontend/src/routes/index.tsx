import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowRight, ClipboardList, Palette, Server, Database, ShieldCheck, FlaskConical, Rocket,
  MessageSquareText, Cpu, Globe, Code2, Eye, Download, Layers,
} from "lucide-react";
import robot from "@/assets/robot.png";
import { Logo, ThemeToggle, btnPrimary, btnGhost } from "@/components/brand";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "FORGE AI — Your Idea, Your App." },
      { name: "description", content: "Seven autonomous AI agents turn your natural-language idea into a deployable full-stack app." },
      { property: "og:title", content: "FORGE AI — Your Idea, Your App." },
      { property: "og:description", content: "Seven autonomous AI agents turn your idea into a deployable full-stack app." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

const agents = [
  { n: "PM Agent", d: "Turns your idea into a spec", i: ClipboardList },
  { n: "UI Agent", d: "Designs every screen", i: Palette },
  { n: "Backend Agent", d: "Writes the APIs", i: Server },
  { n: "Database Agent", d: "Models your data", i: Database },
  { n: "Auth Agent", d: "Secures user access", i: ShieldCheck },
  { n: "QA Agent", d: "Tests what was built", i: FlaskConical },
  { n: "Deploy Agent", d: "Ships it live", i: Rocket },
];

function Section({ id, eyebrow, title, children }: { id?: string; eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="mx-auto max-w-6xl px-6 py-24">
      <p className="text-sm font-semibold uppercase tracking-widest text-primary">{eyebrow}</p>
      <h2 className="mt-2 max-w-xl text-3xl font-bold md:text-4xl">{title}</h2>
      <div className="mt-12">{children}</div>
    </section>
  );
}

function Index() {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Logo />
          <nav className="hidden gap-8 text-sm text-muted-foreground md:flex">
            <a href="#how" className="hover:text-foreground">How it works</a>
            <a href="#agents" className="hover:text-foreground">Agents</a>
            <a href="#features" className="hover:text-foreground">Features</a>
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link to="/login" className="hidden px-3 text-sm font-semibold sm:block">Log in</Link>
            <Link to="/signup" className={`${btnPrimary} px-4 py-2`}>Sign up</Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden bg-grid">
        <div className="mx-auto max-w-6xl px-6 pb-20 pt-20 text-center md:pt-28">
          <h1 className="text-6xl font-extrabold md:text-8xl">
            FORGE <span className="text-primary">AI</span>
          </h1>
          <p className="mt-4 font-display text-2xl font-medium text-muted-foreground md:text-3xl">Your Idea, Your App.</p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <Link to="/signup" className={btnPrimary}>Start Building <ArrowRight className="size-4" /></Link>
            <a href="#how" className={btnGhost}>See How It Works</a>
          </div>

          <div className="relative mx-auto mt-16 max-w-4xl">
            <img src={robot} alt="FORGE AI robot mascot" width={816} height={816} className="animate-float absolute -right-6 -top-24 z-10 w-36 md:-right-14 md:w-48" />
            <div className="rounded-2xl border bg-card p-2 text-left shadow-soft">
              <div className="flex items-center gap-1.5 border-b px-3 pb-2">
                <span className="size-2.5 rounded-full bg-muted-foreground/30" /><span className="size-2.5 rounded-full bg-muted-foreground/30" /><span className="size-2.5 rounded-full bg-muted-foreground/30" />
                <span className="ml-3 text-xs text-muted-foreground">forge.ai/workspace</span>
              </div>
              <div className="grid gap-4 p-5 md:grid-cols-[1.3fr_1fr]">
                <div className="rounded-xl border bg-background p-4">
                  <p className="text-xs font-semibold text-muted-foreground">PROMPT</p>
                  <p className="mt-2 text-sm">Build a booking app for my yoga studio with class schedules, payments and member logins.</p>
                  <div className="mt-4 flex justify-end"><span className={`${btnPrimary} px-3 py-1.5 text-xs`}>Generate</span></div>
                </div>
                <div className="space-y-2">
                  {agents.slice(0, 4).map((a, i) => (
                    <div key={a.n} className="flex items-center gap-3 rounded-lg border bg-background px-3 py-2 text-sm">
                      <a.i className="size-4 text-primary" />
                      <span className="flex-1">{a.n}</span>
                      <span className={`size-2 rounded-full ${i < 2 ? "bg-success" : i === 2 ? "bg-primary animate-pulse" : "bg-muted-foreground/30"}`} />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Section id="how" eyebrow="How it works" title="From a sentence to a shipped app in three steps.">
        <div className="grid gap-6 md:grid-cols-3">
          {[
            { i: MessageSquareText, t: "Describe", d: "Write your idea in plain language." },
            { i: Cpu, t: "Orchestrate", d: "Seven agents plan, build and test it." },
            { i: Globe, t: "Launch", d: "Preview live, download, or deploy." },
          ].map((s, k) => (
            <div key={s.t} className="rounded-2xl border bg-card p-6 shadow-soft">
              <div className="flex items-center justify-between">
                <div className="grid size-11 place-items-center rounded-xl bg-accent text-accent-foreground"><s.i className="size-5" /></div>
                <span className="font-display text-4xl font-bold text-muted-foreground/25">0{k + 1}</span>
              </div>
              <h3 className="mt-5 text-lg font-semibold">{s.t}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{s.d}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section id="agents" eyebrow="Seven-agent architecture" title="A full product team, working in sequence.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
          {agents.map((a, k) => (
            <div key={a.n} className="relative rounded-2xl border bg-card p-4 transition hover:-translate-y-1 hover:border-primary">
              <span className="text-xs font-semibold text-muted-foreground">0{k + 1}</span>
              <a.i className="mt-3 size-6 text-primary" />
              <h3 className="mt-3 text-sm font-semibold">{a.n}</h3>
              <p className="mt-1 text-xs text-muted-foreground">{a.d}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section id="features" eyebrow="Capabilities" title="Everything you need to go from idea to production.">
        <div className="grid gap-px overflow-hidden rounded-2xl border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {[
            { i: Code2, t: "Real full-stack code", d: "Frontend, API and database — yours to keep." },
            { i: Eye, t: "Live preview", d: "Watch your generated app run instantly." },
            { i: FlaskConical, t: "Automated QA", d: "Every build is tested before you see it." },
            { i: ShieldCheck, t: "Auth built in", d: "Secure sign-in out of the box." },
            { i: Download, t: "Download ZIP", d: "Export the full source any time." },
            { i: Layers, t: "Project history", d: "Revisit every prompt and build." },
          ].map((f) => (
            <div key={f.t} className="bg-card p-6">
              <f.i className="size-5 text-primary" />
              <h3 className="mt-4 font-semibold">{f.t}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{f.d}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section eyebrow="Generated preview" title="See your app running before you ship it.">
        <div className="rounded-2xl border bg-card p-2 shadow-soft">
          <div className="flex items-center justify-between border-b px-3 pb-2 text-xs text-muted-foreground">
            <span>Preview · yoga-studio-booking</span>
            <div className="flex gap-2"><span className="rounded-md border px-2 py-0.5">Open</span><span className="rounded-md border px-2 py-0.5">Test</span><span className="rounded-md border px-2 py-0.5">Download ZIP</span></div>
          </div>
          <div className="grid gap-4 p-6 md:grid-cols-3">
            <div className="col-span-full h-10 rounded-lg bg-muted" />
            {[1, 2, 3].map((n) => (
              <div key={n} className="rounded-xl border p-4">
                <div className="h-24 rounded-lg bg-accent" />
                <div className="mt-3 h-3 w-2/3 rounded bg-muted" />
                <div className="mt-2 h-3 w-1/3 rounded bg-muted" />
              </div>
            ))}
          </div>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">Illustration only.</p>
      </Section>

      <section className="mx-auto max-w-6xl px-6 pb-24">
        <div className="relative overflow-hidden rounded-3xl border bg-card p-12 text-center shadow-soft">
          <img src={robot} alt="" width={816} height={816} loading="lazy" className="mx-auto w-24" />
          <h2 className="mt-4 text-3xl font-bold md:text-4xl">Ready to forge your app?</h2>
          <Link to="/signup" className={`${btnPrimary} mt-8`}>Start Building <ArrowRight className="size-4" /></Link>
        </div>
      </section>

      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 py-8 text-sm text-muted-foreground sm:flex-row">
          <Logo />
          <p>© 2026 FORGE AI. Your Idea, Your App.</p>
        </div>
      </footer>
    </div>
  );
}
