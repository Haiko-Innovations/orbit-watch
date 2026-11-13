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
        | "not-found";
    }
  | { page: "request"; id: string };

export const paths = {
  network: "#/",
  openRequests: "#/requests",
  signIn: "#/sign-in",
  account: "#/account",
  myRequests: "#/my-requests",
  newRequest: "#/new-request",
  request: (id: string) => `#/requests/${encodeURIComponent(id)}`,
} as const;

const REQUEST_ID = /^\/requests\/([A-Za-z0-9._-]{1,64})$/;

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
    default: {
      const request = REQUEST_ID.exec(decodeURIComponent(path));
      return request?.[1] ? { page: "request", id: request[1] } : { page: "not-found" };
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
