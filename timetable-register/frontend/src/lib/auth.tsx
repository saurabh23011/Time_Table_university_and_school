"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "./api";
import type { Institution, Role, User } from "./types";

interface AuthState {
  ready: boolean;
  user: User | null;
  institutions: Institution[];
  institution: Institution | null;
  iid: number | null;
  setInstitutionId: (id: number) => void;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshInstitutions: () => Promise<void>;
  can: (min: Role) => boolean;
}

const RANK: Record<Role, number> = {
  student: 0,
  teacher: 1,
  department_admin: 2,
  institution_admin: 3,
  super_admin: 4,
};

const Ctx = createContext<AuthState | null>(null);
const INST_KEY = "tt_institution";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [iid, setIid] = useState<number | null>(null);

  const loadInstitutions = useCallback(async (u: User) => {
    const list = await api<Institution[]>("/api/institutions");
    setInstitutions(list);
    let chosen = u.institution_id;
    if (u.role === "super_admin") {
      let stored: number | null = null;
      try {
        stored = Number(window.localStorage.getItem(INST_KEY)) || null;
      } catch {
        stored = null;
      }
      chosen = list.find((i) => i.id === stored)?.id ?? list[0]?.id ?? null;
    }
    setIid(chosen);
  }, []);

  useEffect(() => {
    (async () => {
      if (!getToken()) {
        setReady(true);
        return;
      }
      try {
        const me = await api<{ user: User }>("/api/auth/me");
        setUser(me.user);
        await loadInstitutions(me.user);
      } catch {
        setToken(null);
      } finally {
        setReady(true);
      }
    })();
  }, [loadInstitutions]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api<{ access_token: string; user: User }>("/api/auth/login", {
        method: "POST",
        body: { email, password },
        auth: false,
      });
      setToken(res.access_token);
      setUser(res.user);
      await loadInstitutions(res.user);
    },
    [loadInstitutions],
  );

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setInstitutions([]);
    setIid(null);
    window.location.href = "/login";
  }, []);

  const setInstitutionId = useCallback((id: number) => {
    setIid(id);
    try {
      window.localStorage.setItem(INST_KEY, String(id));
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      ready,
      user,
      institutions,
      institution: institutions.find((i) => i.id === iid) ?? null,
      iid,
      setInstitutionId,
      login,
      logout,
      refreshInstitutions: async () => {
        if (user) await loadInstitutions(user);
      },
      can: (min: Role) => (user ? RANK[user.role] >= RANK[min] : false),
    }),
    [ready, user, institutions, iid, setInstitutionId, login, logout, loadInstitutions],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}
