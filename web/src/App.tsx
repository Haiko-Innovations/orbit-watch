import { lazy, Suspense, useEffect, useRef } from "react";
import { type ChainInfo, chainInfo, currentSession, getJson, type Health } from "./api";
import { Logo } from "./components/Logo";
import { Loaded } from "./components/Status";
import { TestnetBanner } from "./components/TestnetBanner";
import { AccountPage } from "./pages/AccountPage";
import { NetworkPage } from "./pages/NetworkPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OpenRequestsPage } from "./pages/OpenRequestsPage";
import { paths, type Route, useRoute } from "./router";
import { strings } from "./strings";
import { useResource } from "./useResource";

interface Service {
  health: Health;
  chain: ChainInfo | null;
}

async function loadService(): Promise<Service> {
  const [health, chain] = await Promise.all([getJson<Health>("/v1/health"), chainInfo()]);
  return { health, chain };
}

// The wallet code (viem) loads only with the sign-in page.
const SignInPage = lazy(() => import("./pages/SignInPage"));

const titles: Record<Route["page"], string> = {
  network: strings.network.title,
  "open-requests": strings.openRequests.title,
  "sign-in": strings.signIn.title,
  account: strings.account.title,
  "not-found": strings.notFound.title,
};

function NavLink({
  href,
  current,
  children,
}: {
  href: string;
  current: boolean;
  children: string;
}) {
  return (
    <a href={href} aria-current={current ? "page" : undefined}>
      {children}
    </a>
  );
}

export function App() {
  const route = useRoute();
  const [service, reload] = useResource(loadService);
  const [session, reloadSession] = useResource(currentSession);
  const main = useRef<HTMLElement>(null);
  const first = useRef(true);

  // A new page gets its own title, and keyboard and screen reader users land on its heading.
  useEffect(() => {
    document.title = `${titles[route.page]} · ${strings.appName}`;
    if (first.current) {
      first.current = false;
      return;
    }
    main.current?.querySelector<HTMLElement>("h1")?.focus();
  }, [route.page]);

  const chain = service.state === "ready" ? service.value.chain : null;
  const signedIn = session.state === "ready" ? session.value : null;
  return (
    <>
      <button
        type="button"
        className="skip-link"
        onClick={() => main.current?.querySelector<HTMLElement>("h1")?.focus()}
      >
        {strings.skip}
      </button>
      <TestnetBanner notice={chain?.notice ?? null} />
      <header className="site-header">
        <a className="brand" href={paths.network}>
          <Logo />
          <span>{strings.appName}</span>
        </a>
        <nav aria-label={strings.nav.label}>
          <NavLink href={paths.network} current={route.page === "network"}>
            {strings.nav.network}
          </NavLink>
          <NavLink href={paths.openRequests} current={route.page === "open-requests"}>
            {strings.nav.openRequests}
          </NavLink>
          {signedIn ? (
            <NavLink href={paths.account} current={route.page === "account"}>
              {signedIn.party}
            </NavLink>
          ) : (
            <NavLink href={paths.signIn} current={route.page === "sign-in"}>
              {strings.session.signIn}
            </NavLink>
          )}
        </nav>
      </header>
      <main ref={main} id="main">
        {route.page === "not-found" ? (
          <NotFoundPage />
        ) : (
          <Loaded resource={service} reload={reload}>
            {({ health, chain }) => {
              switch (route.page) {
                case "network":
                  return <NetworkPage health={health} chain={chain} />;
                case "open-requests":
                  return <OpenRequestsPage chain={chain} />;
                case "sign-in":
                  return (
                    <Suspense fallback={<p className="muted">{strings.loading}</p>}>
                      <SignInPage chain={chain} onSignedIn={reloadSession} />
                    </Suspense>
                  );
                case "account":
                  return (
                    <Loaded resource={session} reload={reloadSession}>
                      {(current) => (
                        <AccountPage session={current} chain={chain} onSignedOut={reloadSession} />
                      )}
                    </Loaded>
                  );
              }
            }}
          </Loaded>
        )}
      </main>
      <footer className="site-footer">
        <span>
          {strings.appName}
          {service.state === "ready" ? ` ${service.value.health.version}` : ""} ·{" "}
          {strings.footer.licence}
        </span>
        <a
          href="https://github.com/Haiko-Innovations/orbit-watch"
          target="_blank"
          rel="noopener noreferrer"
        >
          {strings.footer.source}
        </a>
      </footer>
    </>
  );
}
