// Every text of the interface, in one place, so that a translation can follow
// (decision P3-09). English is the primary language (D-09).

export const strings = {
  appName: "Orbit Watch",
  tagline: "Request, deliver and verify satellite observations.",
  testnetOnly: "Testnet only, no real value",
  simulatedNote: "All stations, observations, requests and reviewers here are SIMULATED.",
  simulated: "SIMULATED",
  nav: {
    label: "Main",
    network: "Network",
    openRequests: "Open requests",
  },
  skip: "Skip to content",
  loading: "Loading…",
  retry: "Try again",
  errorTitle: "The service did not answer",
  notFound: {
    title: "Page not found",
    body: "There is no page at this address.",
    home: "Go to the network page",
  },
  network: {
    title: "Network",
    intro:
      "Orbit Watch settles requests through an escrow contract on a test network. Deposits, results and votes are public there; the money has no value.",
    noChain: "This service runs without a chain: settlement uses points in a ledger, not tokens.",
    service: "Service",
    version: "Version",
    chain: "Chain",
    chainId: "Chain ID",
    escrow: "Escrow contract",
    registry: "Reviewer registry",
    token: "Token",
    eas: "Attestation service (EAS)",
    resultSchema: "Schema of automated results",
    voteSchema: "Schema of reviewer votes",
    verifier: "Verifier key of the service",
    feeRecipient: "Platform fee recipient",
    syncedBlock: "Last block read",
    explorer: "Block explorer",
    noExplorer: "none (local chain)",
  },
  openRequests: {
    title: "Open requests",
    intro:
      "Requests that invite observers. A funded request can be reserved and delivered; its deposit waits in the escrow contract.",
    none: "No open requests right now.",
    target: "Target",
    window: "Observation window",
    deadline: "Delivery deadline",
    observerReward: "Observer reward",
    reviewerReward: "Reward per review",
    requirements: "Requirements",
    minObservations: (n: number) => `at least ${n} observations`,
    maxAngle: (arcsec: number) => `angle uncertainty at most ${arcsec}″`,
    requester: "Requester",
    funded: "Funded, open for observers",
    open: "Published, waiting for funding",
    notFunded: "not funded yet",
  },
  session: {
    signIn: "Sign in",
    account: "Your account",
    signedInAs: (party: string) => `Signed in as ${party}`,
  },
  signIn: {
    title: "Sign in",
    intro:
      "Sign in with your wallet. You sign a short message that names this site; it sends no transaction and costs nothing. Your keys never leave your wallet.",
    noChain:
      "This service runs without a chain, so there are no wallets to sign in with. Use an API key on the command line.",
    chooseWallet: "Choose your wallet",
    searching: "Looking for wallets in this browser…",
    noWallet:
      "No wallet was found in this browser. Install a wallet extension, for example MetaMask or Rabby, and reload the page.",
    connecting: (wallet: string) => `Connecting to ${wallet}…`,
    switching: (network: string) => `Asking your wallet to use ${network}…`,
    confirm: "Confirm in your wallet. The message names this site and costs nothing.",
    checking: "Checking the signature…",
    signUpTitle: "Sign up",
    signUpIntro: (address: string) =>
      `The wallet ${address} has no Orbit Watch account yet. Choose what you do and a name; your account will be this wallet.`,
    role: "I am",
    requester: "a requester: I ask for observations",
    station: "an observer: I run a station",
    name: "Name",
    nameHint:
      "2 to 63 letters, digits, dots, dashes or underscores, for example SIM-HELSINKI. It is public.",
    yourParty: (party: string) => `Your account will be ${party}.`,
    signUp: "Sign up and sign in",
    reviewersNote:
      "Reviewers and administrators are added by the maintainers and sign in with a wallet they registered.",
    tryAgain: "Choose a wallet again",
    failed: "Signing in did not work",
  },
  account: {
    title: "Your account",
    notSignedIn: "You are not signed in.",
    party: "Account",
    role: "Role",
    wallet: "Wallet",
    expires: "Session ends",
    signOut: "Sign out",
    roles: {
      requester: "Requester",
      station: "Observer station",
      reviewer: "Reviewer",
      admin: "Administrator",
    },
  },
  balance: {
    title: "Balance",
    inWallet: "In your wallet",
    owed: "Waiting for you in the escrow",
    withdraw: (amount: string) => `Withdraw ${amount}`,
    nothing: "Nothing to withdraw.",
    noWallet: "This account has no wallet registered.",
  },
  transactions: {
    title: "Your transactions",
    none: "No transactions yet.",
    action: "Action",
    request: "Request",
    status: "Status",
    transaction: "Transaction",
    states: { pending: "Waiting for the chain", confirmed: "Confirmed", failed: "Failed" },
  },
  tx: {
    review: "Check and send",
    reviewIntro:
      "Your wallet will ask you to confirm each transaction and show its network fee. Testnet only: nothing here has real value.",
    send: "Send with your wallet",
    cancel: "Cancel",
    close: "Close",
    chooseWallet: (address: string) => `Send with the wallet that has the account ${address}:`,
    noWallet: "No wallet was found in this browser. Install one and sign in again.",
    wrongAccount: (connected: string, signedIn: string) =>
      `Your wallet's account is ${connected}, but you signed in with ${signedIn}. Choose that account in your wallet and try again.`,
    waiting: (title: string) => `${title}: confirm in your wallet…`,
    sent: (title: string) => `${title}: sent, waiting for the chain…`,
    done: "Done. The chain confirmed every transaction.",
    pendingNote:
      "The chain has not confirmed it yet. It stays in your transactions with its status.",
    failedOnChain: (error: string) => `The chain did not accept it: ${error}`,
    declined: "You declined in your wallet. Nothing was sent.",
    notSent: (detail: string) => `The wallet did not send the transaction: ${detail}`,
    problem: "The transaction was not completed",
    contracts: {
      escrow: "Orbit Watch escrow",
      token: (symbol: string) => `${symbol} token`,
      eas: "Ethereum Attestation Service",
    },
    withdraw: {
      title: "Withdraw your credit",
      detail: "Everything the escrow owes you moves to your wallet.",
    },
    approve: {
      title: (amount: string) => `Allow the escrow to take ${amount}`,
      detail: "Only the escrow may take it, and only when it records the deposit.",
    },
    fund: {
      title: (id: string, amount: string) => `Deposit ${amount} for ${id}`,
      detail: (observer: string, reviewer: string, fee: string) =>
        `Observer reward ${observer}, three review rewards of ${reviewer}, platform fee ${fee}. What is not paid out comes back to you.`,
    },
    escrowCalls: {
      reserve: (id: string) => `Reserve ${id}`,
      deliver: (id: string) => `Record your delivery for ${id}`,
      challenge: (id: string) => `Challenge the result of ${id}`,
      cancel: (id: string) => `Cancel ${id} and get the deposit back`,
      settle: (id: string) => `Settle ${id}`,
    },
    vote: {
      title: (id: string) => `Record your vote on ${id}`,
      detail: "Your vote becomes a public EAS attestation signed by your wallet.",
    },
    refused: {
      empty: "The service asked for no transaction.",
      unreadable: "The transaction's data could not be read, so it was not sent.",
      chain: (asked: number, network: string) =>
        `The transaction is for chain ${asked}, not ${network || "this service's chain"}, so it was not sent.`,
      sender: (from: string) =>
        `The transaction would be sent from ${from}, not from your wallet, so it was not sent.`,
      value:
        "The transaction would send ether, which Orbit Watch never asks for, so it was not sent.",
      request: "The transaction is about another request than the one shown, so it was not sent.",
      function: (name: string) => `The call ${name} is not one you make here, so it was not sent.`,
      contract: (to: string) =>
        `${to} is not one of Orbit Watch's contracts, so the transaction was not sent.`,
    },
    reverted: {
      unknown: "The chain refuses this transaction, so it was not sent.",
      named: (name: string) => `The chain refuses this transaction (${name}), so it was not sent.`,
      known: {
        NothingToWithdraw:
          "The chain refuses this transaction: there is nothing to withdraw any more. It was probably withdrawn already, for example in another tab.",
        WrongStatus:
          "The chain refuses this transaction: the request is no longer in a state that allows it.",
        NotRequester: "The chain refuses this transaction: only the requester may do this.",
        NotAParty: "The chain refuses this transaction: only the request's parties may do this.",
        NotAssigned: "The chain refuses this transaction: you are not a reviewer of this round.",
        AlreadyVoted: "The chain refuses this transaction: you have voted already.",
        AlreadyFunded: "The chain refuses this transaction: the request is funded already.",
      },
    },
  },
  footer: {
    source: "Source code",
    licence: "Code Apache 2.0, data CC BY 4.0",
  },
} as const;
