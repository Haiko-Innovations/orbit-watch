# Privacy notice

Orbit Watch public testnet service · version of 21 November 2026

This notice says what personal data the Orbit Watch service keeps, why, for how long and who else handles it. It covers the public testnet service and its web application. Orbit Watch is open source: the code that does all of this is public, and the [data inventory](https://github.com/Haiko-Innovations/orbit-watch/blob/main/docs/personal-data.md) lists every table and log in detail.

## Who is responsible

The controller is **Haiko Innovations Oy**, a Finnish company. For anything about your data, email [info@haikoinnovations.com](mailto:info@haikoinnovations.com?subject=Orbit%20Watch%20privacy) with "Orbit Watch privacy" in the subject line.

## What the service keeps

The service keeps as little as it can. There are no analytics, no trackers, no advertising and no content from other sites.

- **Your account.** The name you choose when you sign up, such as `station:SIM-HELSINKI`, which is public, and your wallet address, which is public on the blockchain anyway. The service also keeps the message you signed to sign up and its signature, which show that the wallet is yours.
- **Signing in.** The message your wallet signs to sign in, with your address, this site's address and its times. The service keeps it for an hour after it expires. Your session: your account, your address, this site's address and when the session started and ends. The session is deleted when you sign out or when it ends after at most 12 hours.
- **Your station's profile, if you run a station.** Its name, its place, its height and the SIMULATED instrument it uses. The place is kept to two decimals of a degree, which is about a kilometre: a station may be someone's home. Only you and the administrators see the profile, and you can delete it on the page "Your station".
- **What you do in the service.** Your requests and their titles, the observation files you deliver, the verification reports, and the reasons you give when you challenge a result or review a delivery. An observation file names your station's place, to the same two decimals; the service refuses files that are more precise. The parties of a request and the administrators see these. When a request is settled and its embargo of at most 30 days has passed, its request, observations and report are published for anyone under the CC BY 4.0 licence.
- **Your transactions.** The hashes and status of the transactions you report to the service. The transactions themselves are on the blockchain.
- **Copies of answers.** When you change something, the service keeps a copy of its answer for 24 hours, so that if your browser asks again, the change is not made twice.
- **IP addresses.** The service does not store your IP address. To keep anyone from overloading it, it counts calls per address, and for that it keeps only a keyed hash of the address. Each count is deleted when its time window ends, within an hour. The service writes no IP address to its own logs. Our hosting provider handles your IP address to deliver the pages and to protect the service from attacks, and its logs are kept for at most 30 days.
- **Email.** If you write to us, we keep your message for as long as it takes to handle it.

The service does not collect anything else about you. You need a wallet and a name to have an account; everything else you give is up to you. Please do not put personal data in titles, names or reasons: they are shown to others and may be published.

## On the blockchain

The service runs on Base Sepolia, a public test blockchain. What you do there with your wallet is public and permanent: your wallet address, the transactions you sign, and the attestations and votes that name your requests, files and reasons by their SHA-256 hashes. **No one, including us, can delete or change what is on the blockchain.** Think about this before you use a wallet address that is linked to you elsewhere: you can make a new wallet just for testing.

## Observations that others have published

Orbit Watch's public repository also holds real observations of satellites that observers published themselves in SCORE, the IAU's Satellite Constellation Observation Repository, under the CC BY 4.0 licence. Replays of such observations through the service will hold them too. We did not get these data from the observers themselves, so this section says what the law asks us to tell them (GDPR article 14).

- **What.** For each observation: its time, the position measured, the uncertainties, the instrument, the observer's place as published in SCORE, SCORE's ID of the observation, and the observers' ORCID iDs, which name the people who made it.
- **From where.** [SCORE](https://score.cps.iau.org), where the observers published them for anyone to use under CC BY 4.0: a publicly accessible source.
- **Why, and on what basis.** To measure and show how Orbit Watch's verification works on real observations, and to credit the observers as the licence asks. The legal basis is our legitimate interest in a verification method that is tested on real data and open to review (article 6(1)(f)). The place is kept as published, because verification needs the exact place.
- **Who sees it.** Anyone: the repository is public, as SCORE is.
- **How long.** As long as the examples and the validation set that hold them are in the repository. If an observer asks, their observations are removed from the next version of the repository and from the service. Copies others have made, and the repository's history, stay.

The observers have the same rights as everyone else, below. They can also ask SCORE about what they published there.

## Why, and on what basis

- To provide the service you use under the [terms of use](#/terms): your account, signing in, your station's profile, your requests, deliveries and reviews, and publishing the settled data as the terms say. The legal basis is the contract, that is, the terms of use (GDPR article 6(1)(b)).
- To keep the service secure and available: the limits per IP address and the hosting provider's logs. The legal basis is our legitimate interest in running a secure service (article 6(1)(f)).
- To keep a verifiable record of each request, so that anyone can check what was delivered and decided. The legal basis is our legitimate interest in an open and verifiable network (article 6(1)(f)).

Each delivery is first checked automatically, which decides whether it passes. The check has no legal or similarly significant effect on you, since the testnet tokens have no value, and any party can challenge its result, which sends the delivery to reviewers.

## Cookies

The service sets one cookie, `__Host-ow_session`, and only when you sign in. It keeps you signed in for at most 12 hours. Scripts cannot read it, and it is sent only to this site. It is strictly necessary for signing in, which you ask for, so under section 205 of the Finnish Act on Electronic Communications Services (917/2014) it needs no consent. The service stores nothing else in your browser. Your wallet extension is your own software and keeps its own data.

## Who else handles your data

- **Vercel Inc.**, a United States company, hosts the service and the web application on our behalf. The service runs in Frankfurt, and Vercel's network delivers the pages from the site nearest to you. It processes your IP address and requests.
- **Neon**, part of Databricks, Inc., hosts the service's database in Frankfurt on our behalf.
- **GitHub, Inc.** keeps the daily backups of the database. They are encrypted before they leave, so GitHub cannot read them.
- **The blockchain.** Base Sepolia, and the attestation service on it, are public: anyone can read what is there. The service reads the blockchain through a provider of blockchain access, to which it sends nothing about you that is not already public on the chain.

Vercel and Databricks are certified under the EU–U.S. Data Privacy Framework, and Vercel's and Databricks' data processing terms include the European Commission's standard contractual clauses. We do not sell or share your data with anyone else.

## How long

- Sign-in messages: an hour after they expire.
- Sessions: until you sign out, at most 12 hours.
- Counts per IP address: until their window ends, at most an hour.
- Copies of answers: 24 hours.
- The hosting provider's logs: at most 30 days.
- Your station's profile: until you delete it.
- Your account, requests, deliveries, reports and reasons: as long as the testnet service runs, since they are the record of the network. When the service closes, its database is deleted.
- Backups: each daily, encrypted backup is kept for 14 days, so something deleted from the service is gone from the backups 14 days later.
- Published data: published under CC BY 4.0, so copies others have made stay with them.

## Your rights

You can ask for a copy of your data, have it corrected or deleted, restrict its use, object to its use for our legitimate interests, and receive the data you gave in a machine-readable form. Email [info@haikoinnovations.com](mailto:info@haikoinnovations.com?subject=Orbit%20Watch%20privacy). We may ask you to sign a message with your wallet to show that the account is yours. We answer within a month.

Some data cannot be deleted: what is on the blockchain, and copies of published data that others have made. We keep the record of a request where it is needed to settle it or to answer a challenge.

You can also complain to the Finnish data protection authority, the Office of the Data Protection Ombudsman: [tietosuoja.fi](https://tietosuoja.fi/en).

## Changes

When this notice changes, its version date changes, and the history of every change is public in the [repository](https://github.com/Haiko-Innovations/orbit-watch/commits/main/docs/legal/privacy-notice.md).
