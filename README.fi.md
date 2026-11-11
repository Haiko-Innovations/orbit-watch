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

> **Tila: vaihe 0, avoin ydin.** Ei rahaa, ei lohkoketjua, ei palvelimia.
> Tilaukset koskevat vain siviilikohteita. **Simuloitu data on aina merkitty
> simuloiduksi**, ja automaattinen tarkistus on prototyyppi, ei
> tuotantovalmis tieteellinen validointi.

## Kokeile (kolme komentoa)

Tarvitset Python 3.12:n tai uudemman.

```sh
pip install "orbit-watch @ git+https://github.com/Haiko-Innovations/orbit-watch.git#subdirectory=core"
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

## Tarkista oma asemasi

```sh
orbit-watch fetch-gp --group cubesat -o cubesat.json     # julkiset radat CelesTrakista
orbit-watch score-station my-night.iod --sites my-site.json --catalog cubesat.json
```

Laatumittari näyttää kulma- ja aikatarkkuutesi, löytää kellovirheet, jotka
näkyvät useassa kohteessa yhtä aikaa, ja näyttää, miten asemasi kehittyy yö
yöltä. Katso [docs/quality-meter.md](docs/quality-meter.md) ja
[examples/real-iod/](examples/real-iod) (englanniksi).

## Mitä vaihe 0 sisältää

| Osa | Komento | Dokumentaatio (englanniksi) |
|---|---|---|
| Havaintoformaatti (JSON Schema), IOD- ja CCSDS TDM -muuntimet | `convert` | [observation-format.md](docs/observation-format.md) |
| Havaintoasemasimulaattori (SGP4, kohina, ajoitusvirheet, puuttuvat havainnot) | `simulate` | [simulator.md](docs/simulator.md) |
| Deterministinen, versioitu tarkistusmoottori | `validate` | [verification.md](docs/verification.md) |
| Aseman laatumittari | `score-station` | [quality-meter.md](docs/quality-meter.md) |
| Julkinen ratadata ja siviilikohteiden sallittu lista | `fetch-gp`, `allowlist build` | [data-sources.md](docs/data-sources.md) |
| Lähetys API:in | `submit` | tulee vaiheessa 1 |

Python-koodi on hakemistossa [`core/`](core). Simuloidut esimerkit ovat
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

Koko suunnitelma on tiedostossa [docs/plan.fi.md](docs/plan.fi.md).

- **Vaihe 0 (nyt):** avoin ydin: formaatti, simulaattori, tarkistus, laatumittari, CLI.
- **Vaihe 1:** tilaukset tilakoneella, optimistinen tarkistus haastejaksolla ja
  2/3-tarkistajakierroksella, API sekä pelkkiä pisteitä kirjaava
  ledger-tilityssovitin.
- **Vaihe 2:** tilitys EVM L2 -**testiverkossa** EAS-attestaatioilla. Ei
  pääverkkoa, ei omaa tokenia.
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
