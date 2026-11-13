import { useEffect, useState } from "react";

// Pages live behind the hash ("#/requests"), so the service serves one file and needs no
// routing rules of its own (decision D-25).

export type Route =
  | {
      page:
        | "network"
        | "open-requests"
        | "sign-in"
        | "account"
        | "my-requests"
        | "new-request"
        | "my-observations"
        | "station"
        | "tasks"
        | "admin"
        | "attestations"
        | "quality"
        | "not-found";
    }
  | { page: "request"; id: string }
  | { page: "task"; id: string };

export const paths = {
  network: "#/",
  openRequests: "#/requests",
  signIn: "#/sign-in",
  account: "#/account",
  myRequests: "#/my-requests",
  newRequest: "#/new-request",
  myObservations: "#/my-observations",
  station: "#/station",
  tasks: "#/tasks",
  admin: "#/admin",
  attestations: "#/attestations",
  quality: "#/quality",
  task: (id: string) => `#/tasks/${encodeURIComponent(id)}`,
  request: (id: string) => `#/requests/${encodeURIComponent(id)}`,
} as const;

const REQUEST_ID = /^\/requests\/([A-Za-z0-9._-]{1,64})$/;
const TASK_ID = /^\/tasks\/([A-Za-z0-9._-]{1,128})$/;

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
  switch (path) {
    case "/":
      return { page: "network" };
    case "/requests":
      return { page: "open-requests" };
    case "/sign-in":
      return { page: "sign-in" };
    case "/account":
      return { page: "account" };
    case "/my-requests":
      return { page: "my-requests" };
    case "/new-request":
      return { page: "new-request" };
    case "/my-observations":
      return { page: "my-observations" };
    case "/station":
      return { page: "station" };
    case "/tasks":
      return { page: "tasks" };
    case "/admin":
      return { page: "admin" };
    case "/attestations":
      return { page: "attestations" };
    case "/quality":
      return { page: "quality" };
    default: {
      const decoded = decodeURIComponent(path);
      const request = REQUEST_ID.exec(decoded);
      if (request?.[1]) return { page: "request", id: request[1] };
      const task = TASK_ID.exec(decoded);
      return task?.[1] ? { page: "task", id: task[1] } : { page: "not-found" };
    }
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
