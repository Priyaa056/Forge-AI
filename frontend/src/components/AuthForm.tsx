import { Link } from "@tanstack/react-router";
import { Eye, EyeOff, Info, Loader2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Logo, ThemeToggle, btnPrimary } from "./brand";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const signup = mode === "signup";
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!/^\S+@\S+\.\S+$/.test(email)) return setError("Enter a valid email address.");
    if (pw.length < 8) return setError("Password must be at least 8 characters.");
    if (signup && pw !== pw2) return setError("Passwords don't match.");
    setLoading(true);
    // No auth backend is connected yet — do not pretend sign-in succeeded.
    setTimeout(() => {
      setLoading(false);
      setError("Sign-in isn't connected yet. Connect the FORGE AI authentication service to enable this.");
    }, 400);
  };

  const field =
    "w-full rounded-xl border bg-background px-4 py-3 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-ring/25";

  return (
    <div className="relative grid min-h-screen place-items-center bg-grid px-4 py-10">
      <div className="absolute left-6 top-5"><Logo /></div>
      <div className="absolute right-6 top-5"><ThemeToggle /></div>
      <form onSubmit={submit} noValidate className="w-full max-w-md rounded-2xl border bg-card p-8 shadow-soft">
        <h1 className="text-2xl font-bold">{signup ? "Create your account" : "Welcome back"}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {signup ? "Start turning ideas into apps." : "Log in to continue building."}
        </p>
        <div className="mt-6 space-y-4">
          <label className="block text-sm font-medium">Email
            <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={`${field} mt-1.5`} placeholder="you@company.com" />
          </label>
          <label className="block text-sm font-medium">Password
            <div className="relative mt-1.5">
              <input type={show ? "text" : "password"} autoComplete={signup ? "new-password" : "current-password"} value={pw} onChange={(e) => setPw(e.target.value)} className={`${field} pr-11`} />
              <button type="button" onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </label>
          {signup && (
            <label className="block text-sm font-medium">Confirm password
              <input type={show ? "text" : "password"} autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} className={`${field} mt-1.5`} />
            </label>
          )}
        </div>
        {error && <p role="alert" className="mt-4 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        <button disabled={loading} className={`${btnPrimary} mt-6 w-full py-3`}>
          {loading && <Loader2 className="size-4 animate-spin" />}
          {signup ? "Sign up" : "Log in"}
        </button>
        <p className="mt-5 text-center text-sm text-muted-foreground">
          {signup ? "Already have an account? " : "New to FORGE AI? "}
          <Link to={signup ? "/login" : "/signup"} className="font-semibold text-primary hover:underline">
            {signup ? "Log in" : "Sign up"}
          </Link>
        </p>
        <p className="mt-5 flex gap-2 rounded-lg bg-accent px-3 py-2 text-xs text-accent-foreground">
          <Info className="mt-0.5 size-3.5 shrink-0" /> Authentication backend not connected yet — password recovery will appear once it is.
        </p>
      </form>
    </div>
  );
}
