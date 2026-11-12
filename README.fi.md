# Orbit Watch (työnimi)

[English](README.md) · **Suomi**

> Tämä on käännös. Jos englanninkielinen ja suomenkielinen versio eroavat, englanninkielinen versio pätee.

**Avoin protokolla ja referenssitoteutus satelliittihavaintojen tilaamiseen,
toimittamiseen, riippumattomaan tarkistamiseen ja tilitykseen.**

Laukaisun jälkeen kerralla irrotetaan kymmeniä pieniä satelliitteja, eivätkä
kuutiosatelliittitiimit usein tiedä, mikä julkinen ratatieto on heidän
satelliittinsa. Orbit Watchissa tiimi julkaisee tilauksen ("tunnista ja seuraa
kohdetta X aikaikkunassa Y"). Harrastaja-asemat havaitsevat, ja toimitus
tarkistetaan automaattisesti ja toistettavasti julkista ratadataa vasten.
Havaitsijat hyötyvät heti ensimmäisestä päivästä: laatumittari kertoo, kuinka
tarkka heidän asemansa on.

> **Tila: vaihe 1 on valmis (versio 0.2.0).** Tilaukset, optimistinen
> tarkistus, pistekirjanpito, HTTP-rajapinta ja komentoriviasiakas toimivat
> paikallisesti, **ilman rahaa ja ilman lohkoketjua**. Tilaukset koskevat vain
> siviilikohteita. **Simuloitu data on aina merkitty simuloiduksi**, ja
> automaattinen tarkistus on prototyyppi, ei tuotantovalmis tieteellinen
> validointi. Vaihe 2, tilitys Base Sepolia -**testiverkossa**, on alkanut:
> hakemiston [`contracts/`](contracts) escrow-sopimus noudattaa vaiheen 1
> tilityssääntöjä ja kieltäytyy toimimasta muualla kuin testiverkossa ja
> paikallisessa ketjussa.
> Katso [tiekartta](docs/roadmap.fi.md),
> [vaiheen 1 yhteenveto](docs/phase-1-summary.fi.md) ja [muutosloki](CHANGELOG.md).

## Kokeile (kolme komentoa)

Tarvitset Python 3.12:n tai uudemman.

```sh
pip install "orbit-watch @ git+https://github.com/Haiko-Innovations/orbit-watch.git@v0.2.0#subdirectory=core"
orbit-watch demo
cat orbit-watch-demo/datasets/wrong_target/report.txt
```

`orbit-watch demo` simuloi samaan tilaukseen kuusi toimitusta ja tarkistaa jokaisen:

| Aineisto | Mikä se on | Tulos |
|---|---|---|
| `acceptable` | hyvä CMOS-asema GPS-ajastuksella | hyväksytty (pass) |
| `invalid` | rikkinäinen tiedosto | hylätty: formaatti |
| `late` | havaittu pyydetyn aikaikkunan jälkeen | hylätty: aikaikkuna, havaintojen vähimmäismäärä |
| `duplicate` | samat havainnot toimitettu uudelleen | hylätty: kaksoiskappaleet |
| `wrong_target` | viereinen kuutiosatelliitti, merkitty pyydetyksi | hylätty: ratajäännökset |
| `too_imprecise` | visuaalihavaitsija kiikareilla | hylätty: ilmoitettu epävarmuus |

Jokainen raportti kertoo menetelmän ja sen version, jokaisen syötteen SHA-256-tiivisteen
ja jokaisen tarkistuksen perustelun. Sama syöte tuottaa tavulleen saman
raportin millä tahansa koneella: CI tarkistaa tämän kahdella Python-versiolla.

### Koko tilauksen ketju (vaihe 1)

```sh
orbit-watch demo --phase 1
cat orbit-watch-demo-phase1/transcript.md
```

Viisi simuloitua tilausta simuloidulla kellolla: hyväksytty, haasteen jälkeen
hylätty, ilman haastetta hylätty, riidanalainen ja vanhentunut. Loki näyttää
jokaisen askeleen, pisteet ja tarkistajien profiilit. Ketjun voi ajaa itse
HTTP-rajapinnan kautta (`pip install "orbit-watch[api] @ …"`, sitten
`orbit-watch serve`); katso [docs/api.md](docs/api.md) (englanniksi).

## Tarkista oma asemasi

```sh
orbit-watch fetch-gp --group cubesat -o cubesat.json     # julkiset radat CelesTrakista
orbit-watch score-station my-night.iod --sites my-site.json --catalog cubesat.json
```

Laatumittari näyttää kulma- ja aikatarkkuutesi, löytää kellovirheet, jotka
näkyvät useassa kohteessa yhtä aikaa, ja näyttää, miten asemasi kehittyy yö
yöltä. Katso [docs/quality-meter.md](docs/quality-meter.md) ja
[examples/real-iod/](examples/real-iod) (englanniksi).

## Mitä siinä on

| Osa | Komento | Dokumentaatio (englanniksi) |
|---|---|---|
| Havaintoformaatti (JSON Schema), IOD- ja CCSDS TDM -muuntimet | `convert` | [observation-format.md](docs/observation-format.md) |
| Havaintoasemasimulaattori (SGP4, kohina, ajoitusvirheet, puuttuvat havainnot) | `simulate` | [simulator.md](docs/simulator.md) |
| Deterministinen, versioitu tarkistusmoottori | `validate` | [verification.md](docs/verification.md) |
| Aseman laatumittari | `score-station` | [quality-meter.md](docs/quality-meter.md) |
| Julkinen ratadata ja siviilikohteiden sallittu lista | `fetch-gp`, `allowlist build` | [data-sources.md](docs/data-sources.md) |
| Tilauksen elinkaari, optimistinen tarkistus, tarkistajakierrokset | | [lifecycle.md](docs/lifecycle.md), [optimistic-verification.md](docs/optimistic-verification.md) |
| Tilityssäännöt ja pistekirjanpito | | [settlement.md](docs/settlement.md) |
| Tarkistajien tarkkuus tunnetun vastauksen tehtävillä | | [reviewer-accuracy.md](docs/reviewer-accuracy.md) |
| Tallennus (SQLite, tiedostot tiivisteen mukaan) | | [storage.md](docs/storage.md) |
| HTTP-rajapinta ja komentoriviasiakas | `serve`, `request`, `reserve`, `submit`, `challenge`, `review`, `admin` | [api.md](docs/api.md) |
| Avoin data (CC BY 4.0, embargo, pysyvät osoitteet) | `public` | [data-publication.md](docs/data-publication.md) |
| Escrow-sopimus, EAS-attestaatiot ja tarkistajarekisteri Base Sepolia -**testiverkkoon** (vaihe 2, kesken) | `forge test` | [escrow.md](docs/escrow.md), [attestations.md](docs/attestations.md), [kuka voi muuttaa mitä](contracts/README.md#privileges-who-can-change-what) |
| Testiverkon tilityssovitin (Python, `evm`-lisäosa) | | [evm-adapter.md](docs/evm-adapter.md) |
| Palvelu, rajapinta ja komentorivi **testiverkossa**: omat lompakot, allekirjoitus omalla avainsäilöllä, transaktiot lohkoselainlinkkeineen | `orbit-watch serve --network base-sepolia …`, `orbit-watch wallet register` | [chain-service.md](docs/chain-service.md) |
| Sopimukset **Base Sepoliassa**: osoitteet, faucetit, kuka hallitsee mitäkin avainta, käyttöönotto | `forge script script/DeployOrbitWatch.s.sol` | [base-sepolia.md](docs/base-sepolia.md) |

Python-koodi on hakemistossa [`core/`](core) ja Solidity-sopimukset hakemistossa [`contracts/`](contracts). Simuloidut esimerkit ovat
hakemistossa [`examples/`](examples).

### Mikä on simuloitua

- Kaikki tämän repositorion asemat, havainnot ja testiaineistot sekä sisäänrakennetun
  luettelon neljä kohdetta (numerot 339001–339009, merkintä `(SIMULATED)`).
- Simuloidut tiedostot kertovat sen itse (`"simulated": true` tai merkintärivi
  IOD- ja TDM-tiedostoissa), eikä simuloitu toimitus voi koskaan täyttää oikeaa tilausta.
- Oikeaa ratadataa ei koskaan commitoida repositorioon; `fetch-gp` lataa sen tarvittaessa.

### Sallittu lista: vain siviilikohteet

Tilaukset voivat kohdistua vain sallitulla listalla oleviin kohteisiin. Lista
muodostetaan julkisen luettelon siviiliryhmistä, joista poistetaan sotilasryhmä:

```sh
orbit-watch fetch-gp --group cubesat -o cubesat.json
orbit-watch fetch-gp --group military -o military.json
orbit-watch allowlist build --include cubesat.json --exclude military.json -o allowlist.json
```

Työkalu poistaa lisäksi nimet, jotka vastaavat varovaisia sotilas- ja
tiedustelusatelliittien nimimalleja. Salaisilla kohteilla ei ole julkista
rataa, joten ne eivät voi koskaan päätyä listalle.

## Osallistu

Harrastajahavaitsijat, tähtitieteilijät ja kehittäjät ovat kaikki tervetulleita.
[good first issue](https://github.com/Haiko-Innovations/orbit-watch/labels/good%20first%20issue)
-merkityt tehtävät ovat pieniä ja itsenäisiä: uusi tarkistus, uusi
havaintoformaatti tai uusi simuloitu asemaprofiili. Aloita
[CONTRIBUTING.fi.md](CONTRIBUTING.fi.md):stä ja noudata
[toimintaohjetta](CODE_OF_CONDUCT.md).

## Tiekartta

Nykytila ja seuraavat askeleet: [docs/roadmap.fi.md](docs/roadmap.fi.md).
Päätökset perusteluineen: [docs/decisions.md](docs/decisions.md) (englanniksi).
Koko aloitussuunnitelma: [docs/plan.fi.md](docs/plan.fi.md).

- **Vaihe 0 (valmis, 0.1.0):** avoin ydin: formaatti, simulaattori, tarkistus, laatumittari, CLI.
- **Vaihe 1 (valmis, 0.2.0):** tilaukset tilakoneella, optimistinen tarkistus
  haastejaksolla ja 2/3-tarkistajakierroksella, API sekä pelkkiä pisteitä
  kirjaava ledger-tilityssovitin.
- **Vaihe 2 (käynnissä):** tilitys EVM L2 -**testiverkossa**
  EAS-attestaatioilla. Ei pääverkkoa, ei omaa tokenia.
- **Vaihe 3:** verkkosovellus roolikohtaisine näkymineen.

## Avoimet kysymykset

- **Nimi:** "Orbit Watch" on työnimi; tavaramerkki- ja verkkotunnustarkistuksia
  ei ole tehty (lähellä ovat "Orbital Watch" ja DARPA OrbitOutlook).
- **Oikea IOD-esimerkki:** tuoreet julkiset IOD-havainnot koskevat lähes kaikki
  salaisia kohteita; haluamme pyytää havaitsijalta siviilikohteen esimerkin ja
  luvan julkaista se (katso [examples/real-iod/](examples/real-iod)).
- **Vakuudet** varauksille ja tarkistajille leimasinhyväksynnän ja salaisen yhteistyön estämiseksi.
- **Täysi riitojenratkaisu.**
- **Yhteistyö:** IAU CPS (SatChecker ja SCORE), Unistellar ja SETI, SatNOGS
  sekä SeeSat-L-harrastajayhteisö.
- **Sääntely**, jos joskus mukaan tulee oikeaa rahaa (MiCA, maksupalvelut).
  Sopimus ei koskaan säilytä varoja kenenkään puolesta.

## Lisenssi

Koodi: [Apache License 2.0](LICENSE). Orbit Watchin kautta julkaistun
havaintodatan oletuslisenssi on CC BY 4.0. Orbit Watchia ylläpitävät
[Haiko Innovations](https://haikoinnovations.com) ja projektiin osallistujat.
