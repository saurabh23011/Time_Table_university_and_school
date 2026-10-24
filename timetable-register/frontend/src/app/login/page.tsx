"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";

const DEMO = [
  { email: "superadmin@timetable.dev", who: "Super admin, all institutions" },
  { email: "admin@ait.edu.in", who: "Institution admin, Aryabhatta Institute" },
  { email: "cse.admin@ait.edu.in", who: "Department admin, Computer Science" },
  { email: "anita.sharma@ait.edu.in", who: "Teacher" },
  { email: "student.cse3a@ait.edu.in", who: "Student, CSE Sem 3 A" },
  { email: "admin@greenvalley.edu.in", who: "Institution admin, Green Valley School" },
];

// A small, static fragment of a week used as the sign-in illustration.
const SAMPLE: (null | { s: string; c: string; clash?: boolean })[][] = [
  [{ s: "Maths", c: "#2563eb" }, { s: "Data Str.", c: "#059669" }, null, { s: "Physics", c: "#e11d48" }, { s: "OOP", c: "#7c3aed" }],
  [{ s: "DLD", c: "#d97706" }, { s: "Maths", c: "#2563eb" }, { s: "OOP", c: "#7c3aed" }, { s: "Maths", c: "#2563eb", clash: true }, null],
  [null, null, null, null, null],
  [{ s: "DS Lab", c: "#0891b2" }, { s: "English", c: "#db2777" }, { s: "Data Str.", c: "#059669" }, { s: "DLD", c: "#d97706" }, { s: "Maths", c: "#2563eb" }],
];

export default function LoginPage() {
  const { login, user, ready } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && user) router.replace("/dashboard");
  }, [ready, user, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <div className="hidden flex-col justify-between border-r border-rule bg-sheet p-10 lg:flex">
        <p className="font-display text-[22px] font-bold">Timetable Register</p>
        <div>
          <div className="mb-8">
            <h1 className="max-w-[17ch] font-display text-[44px] font-semibold leading-[1.05] tracking-tight">
              Every teacher, room and class in one place at a time.
            </h1>
          </div>
          <div className="overflow-hidden rounded-[8px] border border-rule" aria-hidden>
            <div className="grid grid-cols-[64px_repeat(5,1fr)] border-b border-rule bg-paper text-[12px] font-semibold text-ink-soft">
              <span className="px-2 py-1.5" />
              {["Mon", "Tue", "Wed", "Thu", "Fri"].map((d) => (
                <span key={d} className="border-l border-rule px-2 py-1.5">{d}</span>
              ))}
            </div>
            {SAMPLE.map((row, ri) => (
              <div key={ri} className={`grid grid-cols-[64px_repeat(5,1fr)] border-b border-rule-soft last:border-b-0 ${ri === 2 ? "hatch" : ""}`}>
                <span className="tnum px-2 py-2 text-[12px] text-ink-faint">{ri === 2 ? "Lunch" : ["09:00", "10:00", "", "12:30"][ri]}</span>
                {row.map((c, ci) => (
                  <div key={ci} className="border-l border-rule-soft p-1">
                    {c && (
                      <div
                        className={`slip rounded-[4px] border-l-[3px] px-1.5 py-1 text-[12px] font-semibold ${c.clash ? "redpen-ring" : ""}`}
                        style={{ borderColor: c.c, background: `${c.c}14` }}
                      >
                        {c.s}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
          <p className="mt-3 max-w-[56ch] text-sm text-ink-soft">
            The ringed lecture shows a teacher booked in two classes at once. The register catches it the moment it
            happens and offers free periods to move it to.
          </p>
        </div>
        <p className="text-[13px] text-ink-faint">For universities, colleges and schools.</p>
      </div>

      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[380px]">
          <h2 className="font-display text-[28px] font-semibold">Sign in</h2>
          <p className="mt-1 text-ink-soft">Use the account your institution gave you.</p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <Field label="Email">
              <Input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Password">
              <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <ErrorNote error={error} />
            <Button variant="primary" className="w-full" busy={busy} type="submit">
              Sign in
            </Button>
          </form>

          <div className="mt-10 border-t border-rule pt-5">
            <p className="text-sm font-semibold">Demo accounts</p>
            <p className="text-[13px] text-ink-faint">Password for each: Demo@1234. Choose one to fill the form.</p>
            <ul className="mt-2 divide-y divide-rule-soft">
              {DEMO.map((d) => (
                <li key={d.email}>
                  <button
                    type="button"
                    onClick={() => {
                      setEmail(d.email);
                      setPassword("Demo@1234");
                    }}
                    className="w-full py-2 text-left hover:text-register"
                  >
                    <span className="block text-sm font-semibold">{d.email}</span>
                    <span className="block text-[13px] text-ink-faint">{d.who}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
