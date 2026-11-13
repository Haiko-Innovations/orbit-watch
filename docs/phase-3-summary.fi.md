# Vaiheen 3 yhteenveto

[English](phase-3-summary.md) · **Suomi**

> Tämä on käännös. Jos englanninkielinen ja suomenkielinen versio eroavat, englanninkielinen versio pätee.

Vaihe 3, verkkosovellus, on valmis versiona **0.4.0**. Tämä on
[suunnitelman](plan.fi.md) pyytämä vaiheen lopun yhteenveto.

> **Vain testiverkko, ei oikeaa arvoa.** Verkkosovellus toimii paikallisesti
> ([P3-10](decisions.md#p3-10-no-public-deployment-in-phase-3)). Ketjussa
> kaikki toimii Base Sepoliassa Circlen testi-USDC:llä, jolla ei ole arvoa.
> Kaikki asemat, havainnot, tilaukset ja tarkistajat ovat SIMULOITUJA.

## Mikä toimii

- **Yksi verkkosovellus** ([web.md](web.md), englanniksi): TypeScriptillä ja
  Reactilla tehty yhden sivun sovellus. Palvelu tarjoaa sen omasta
  originistaan tiukan sisällön suojauskäytännön alla, ja sovellus käyttää vain
  dokumentoitua rajapintaa.
- **Jokainen osapuoli kirjautuu omalla lompakollaan** Sign-In with Ethereumilla.
  Lompakko löytyy EIP-6963:n kautta. Istunto on `HttpOnly`-eväste, eikä yksikään
  avain päädy sivulle tai palvelulle.
- **Transaktiot selaimessa.** Ennen kuin lompakko näkee transaktion, sivu lukee
  sen kutsudatan ja kertoo, mitä se tekee: summat, tiedoston SHA-256:n, äänen
  ja perustelut. Kaiken muun se hylkää. Transaktiot näkyvät odottavina,
  vahvistettuina tai epäonnistuneina linkkeineen lohkoselaimeen.
- **Näkymät:**
  - **tilaajan**: luonti, julkaisu, rahoitus, seuranta, haaste sekä datan ja
    raportin lataus;
  - **havaitsijan**: SIMULOITU asemaprofiili, varaus, oman tiedoston tai
    simuloitujen havaintojen toimitus sekä syy, miksi toimitus hyväksyttiin
    tai hylättiin;
  - **tarkistajan**: tehtävät, äänet perusteluineen omina EAS-attestaatioina,
    palkkiot ja tarkkuus;
  - **ylläpitäjän**: jokainen tilaus, maksu, virhe ja tapahtuma, `tick`,
    tarkistajarekisteri ja aikalukon toiminnot, Safelle valmisteltava data
    sekä simulaattori.
- **Julkiset sivut ilman kirjautumista**: verkko, avoimet tilaukset,
  attestaatioselain EAS Scan -linkkeineen ja aseman laatumittari.
- **Paikallinen ympäristö yhdellä komennolla** kehitykseen ja testeihin. Siinä
  on paikallinen ketju sopimuksineen, Safe, aikalukko, palvelu ja SIMULOIDUT
  osapuolet.
- **Vaiheen 3 demo**: koko ketju selaimessa Base Sepoliassa, jokaisella
  roolilla oma lompakko
  ([`examples/phase3/transcript.md`](../examples/phase3/transcript.md),
  englanniksi).

### Valmiskriteerit

Päätöksestä [P3-11](decisions.md#p3-11-phase-3-completion-criteria):

| Kriteeri | Tila |
|---|---|
| 1. Verkkosovellus käynnistyy dokumentoiduilla ohjeilla paikallisessa ketjussa ja Base Sepoliassa | ✅ [web.md](web.md#run-it): paikallinen ympäristö CI:ssä ja kehityksessä; demon palvelu Base Sepoliassa käynnistettiin samoilla ohjeilla |
| 2. Jokainen rooli kirjautuu omalla lompakollaan; yksikään yksityinen avain, siemenlause tai palvelimen salaisuus ei päädy selaimeen tai palveluun, testattu | ✅ jokaisen roolin päästä päähän -testi kirjautuu omalla lompakollaan. Testit tarkistavat, etteivät skriptit voi lukea istuntoevästettä ja ettei sivu säilytä mitään salaista. Demon avaimet pysyvät testiajurissa (D-33) |
| 3. Tilaaja luo, rahoittaa ja seuraa tilausta, lataa sen datan ja raportin sekä näkee maksut ja palautukset selaimessa | ✅ `requester.spec.ts`; demo Base Sepoliassa |
| 4. Havaitsija rekisteröi simuloidun aseman, varaa tilauksen, toimittaa ja seuraa palkkioita selaimessa | ✅ `observer.spec.ts` ja `transactions.spec.ts`; demo |
| 5. Tarkistaja näkee annetut tehtävät, allekirjoittaa äänet perusteluineen EAS-attestaatioina sekä näkee palkkiot ja tarkkuuden selaimessa | ✅ `reviewer.spec.ts`; demon äänet EAS Scanissa |
| 6. Ylläpitäjä näkee tilaukset, toimitukset, maksut, virheet ja tapahtumalokin, valmistelee tarkistajamuutokset Safelle ja aikalukolle sekä käynnistää simulaattorin ilman oikeuksia, joita rajapinta ei anna, testattu | ✅ `admin.spec.ts`, jossa muun kuin ylläpitäjän istunto hylätään; demon Safe ajoittaa valmistellun muutoksen Base Sepoliassa |
| 7. Odottavat, vahvistetut ja epäonnistuneet transaktiot näytetään erikseen linkkeineen lohkoselaimeen | ✅ `transactions.spec.ts` (hylätty toinen nosto); BaseScan-linkit demossa |
| 8. Aseman laatumittari ja julkinen attestaatioselain toimivat kirjautumatta | ✅ `public.spec.ts`; demo |
| 9. Testiverkkomerkintä näkyy jokaisella sivulla, ja simuloitu data on merkitty | ✅ `public.spec.ts` ja jokaisen roolin testi |
| 10. Jokaisen roolin päästä päähän -testit ja jokaisen näkymän saavutettavuustarkistukset ajetaan CI:ssä paikallista ketjua vasten | ✅ CI:n `tarkistus` ajaa jokaisen päästä päähän -testin ja kaikkien 17 näkymän katselmoinnin ([accessibility.md](accessibility.md), englanniksi) |

## Mikä on simuloitua ja mikä testiverkkoa

- Kaikki asemat, havainnot, tilaukset ja tarkistajat. Jokainen simuloitu
  dokumentti kertoo sen itse, ja sivut merkitsevät sen.
- Raha on Circlen arvotonta testi-USDC:tä Base Sepoliassa.
- **Testiverkossa yksi ylläpitäjä hallitsee kaikkia avaimia**: Safen
  allekirjoittajia, tarkistusavainta ja simuloituja osapuolia
  ([D-24](decisions.md#d-24-the-base-sepolia-deployment)).
- **Demossa jokaisen roolin puolesta allekirjoittaa testilompakko.** Siinä on
  roolin testiverkon avain, ja se ilmoittautuu sivulle kuten oikea lompakko.
  Lompakkolaajennukset, kuten MetaMask, käyttävät samaa EIP-6963-reittiä,
  mutta niillä tehtyä ajoa ei ole tallennettu.
- **Safen sovellusta ei käytetty.** Safen omistajat allekirjoittivat
  valmistellun eräajotiedoston transaktion avaimillaan sen ulkopuolella
  ([D-33](decisions.md#d-33-the-phase-3-demo-and-the-accessibility-review)).
- **Palvelu toimii paikallisesti.** Vain sopimukset ja attestaatiot ovat
  julkisia.

## Näin sen voi ajaa

Paikallisessa ketjussa ilman arvokkaita avaimia, kun käytössä on Node 26, uv
ja Foundry 1.8.6 ([web.md](web.md#run-it)):

```sh
git clone --recurse-submodules --branch v0.4.0 https://github.com/Haiko-Innovations/orbit-watch.git
cd orbit-watch
cd contracts && forge build && cd ../web && npm ci && npm run build
cd ../core && uv run python tests/local_stack.py --web ../web/dist
```

Avaa sitten <http://127.0.0.1:8787/> ja kirjaudu lompakolla paikallisessa
ketjussa (portti 8545). Osapuolten testiavaimet ovat tiedostossa
`local-stack.json`.

Demo Base Sepoliassa tarvitsee ylläpitäjän testiverkon keystoret
([web.md](web.md#the-phase-3-demo)).

## Avoimet ongelmat seuraavaan vaiheeseen

- **Julkinen käyttöönotto** (P3-10): TLS, kutsurajat, avainten kierto,
  ylläpito ja tietosuojaseloste. Palvelu tarvitsee myös taustatyön, koska nyt
  se tilittää vasta, kun joku raportoi transaktion tai kutsuu `tick`iä.
- **Saavutettavuus ihmisten kanssa**: ruudunlukijat, muut selaimet ja
  käyttäjätestit ([accessibility.md](accessibility.md#not-covered)).
- **Avaimet eri ihmisille**: Safen kolme allekirjoittajaa ja tarkistusavain
  pois ylläpitäjän koneelta.
- **Kalibrointi ketjussa**: tarkistaja erottaa kalibrointitehtävän oikeasta
  vastattuaan, koska vain oikea ääni on julkinen attestaatio (D-23, D-31).
- **Aikalukon historia**: ylläpitäjän näkymä näyttää vain toiminnot, jotka
  ajoitettiin sen jälkeen, kun palvelu alkoi seurata ketjua (D-32).
- **Vakuudet** varauksille, haasteille ja tarkistajille sekä
  **henkilötiedot**: asemien koordinaatit julkisessa datassa.
- **Oikea IOD-esimerkki** siviilikohteesta luvan kanssa
  ([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).
