import { useEffect, useState } from "react";

// Pages live behind the hash ("#/requests"), so the service serves one file and needs no
// routing rules of its own (decision D-25).

export type Route = { page: "network" } | { page: "open-requests" } | { page: "not-found" };

export const paths = {
  network: "#/",
  openRequests: "#/requests",
} as const;

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
  switch (path) {
    case "/":
      return { page: "network" };
    case "/requests":
      return { page: "open-requests" };
    default:
      return { page: "not-found" };
  }
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const changed = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  return route;
}
