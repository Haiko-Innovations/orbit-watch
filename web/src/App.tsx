import { lazy, Suspense, useEffect, useRef } from "react";
import { type ChainInfo, chainInfo, currentSession, getJson, type Health } from "./api";
import { Logo } from "./components/Logo";
import { Loaded } from "./components/Status";
import { TestnetBanner } from "./components/TestnetBanner";
import { AccountPage } from "./pages/AccountPage";
import { MyObservationsPage } from "./pages/MyObservationsPage";
import { MyRequestsPage } from "./pages/MyRequestsPage";
import { NetworkPage } from "./pages/NetworkPage";
import { NewRequestPage } from "./pages/NewRequestPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OpenRequestsPage } from "./pages/OpenRequestsPage";
import { RequestPage } from "./pages/RequestPage";
import { StationPage } from "./pages/StationPage";
import { TaskPage } from "./pages/TaskPage";
import { TasksPage } from "./pages/TasksPage";
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
  "my-requests": strings.myRequests.title,
  "my-observations": strings.myObservations.title,
  station: strings.station.title,
  tasks: strings.tasks.title,
  task: strings.task.title,
  "new-request": strings.newRequest.title,
  request: strings.request.terms,
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
  const requestId = route.page === "request" ? route.id : null;
  const taskId = route.page === "task" ? route.id : null;
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
          {signedIn?.role === "station" ? (
            <>
              <NavLink href={paths.myObservations} current={route.page === "my-observations"}>
                {strings.nav.myObservations}
              </NavLink>
              <NavLink href={paths.station} current={route.page === "station"}>
                {strings.nav.myStation}
              </NavLink>
            </>
          ) : null}
          {signedIn?.role === "reviewer" ? (
            <NavLink href={paths.tasks} current={route.page === "tasks" || route.page === "task"}>
              {strings.nav.tasks}
            </NavLink>
          ) : null}
          {signedIn?.role === "requester" ? (
            <NavLink
              href={paths.myRequests}
              current={route.page === "my-requests" || route.page === "new-request"}
            >
              {strings.nav.myRequests}
            </NavLink>
          ) : null}
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
                  return <OpenRequestsPage chain={chain} session={signedIn} />;
                case "sign-in":
                  return (
                    <Suspense fallback={<p className="muted">{strings.loading}</p>}>
                      <SignInPage chain={chain} onSignedIn={reloadSession} />
                    </Suspense>
                  );
                case "my-requests":
                case "new-request":
                case "my-observations":
                case "station":
                case "tasks":
                case "task":
                case "request":
                  return (
                    <Loaded resource={session} reload={reloadSession}>
                      {(current) =>
                        current === null || chain === null ? (
                          <AccountPage session={null} chain={chain} onSignedOut={reloadSession} />
                        ) : route.page === "my-requests" ? (
                          <MyRequestsPage session={current} />
                        ) : route.page === "new-request" ? (
                          <NewRequestPage />
                        ) : route.page === "my-observations" ? (
                          <MyObservationsPage session={current} />
                        ) : route.page === "station" ? (
                          <StationPage session={current} />
                        ) : route.page === "tasks" ? (
                          <TasksPage session={current} />
                        ) : route.page === "task" ? (
                          <TaskPage id={taskId ?? ""} chain={chain} session={current} />
                        ) : (
                          <RequestPage id={requestId ?? ""} chain={chain} session={current} />
                        )
                      }
                    </Loaded>
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
