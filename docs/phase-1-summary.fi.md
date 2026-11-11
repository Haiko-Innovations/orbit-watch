# Vaiheen 1 yhteenveto

[English](phase-1-summary.md) · **Suomi**

> Tämä on käännös. Jos englanninkielinen ja suomenkielinen versio eroavat, englanninkielinen versio pätee.

Vaihe 1 (tilaukset, optimistinen tarkistus ja API) on valmis versiona
**0.2.0**. Tämä on [suunnitelman](plan.fi.md) pyytämä vaiheen lopun yhteenveto.

## Mikä toimii

Kaikki toimii paikallisesti, rahan sijaan pisteillä ja ilman lohkoketjua.

- **Tilauksen elinkaari**: luonnos → avoin → (rahoitettu) → varattu →
  toimitettu → haastejakso → hyväksytty / hylätty / (tarkistajakierros →
  hyväksytty / hylätty / riidanalainen), sekä vanhentunut ja peruttu. Jokainen
  tilaus päättyy tilitettynä. Puhdas tilakone, jossa ehdot jäädytetään ja
  tiivistetään ja määräajat laukeavat täsmälleen oikeaan aikaan.
- **Optimistinen tarkistus**: automaattinen tarkistus ajetaan toimituksen
  yhteydessä. Tulos jää voimaan, ellei tilaaja tai havaitsija haasta sitä 24
  tunnissa. Haaste käynnistää kolmen riippumattoman tarkistajan kierroksen.
  Tarkistajat valitaan tiivisteellä, johon kukaan ei voi vaikuttaa. Kaksi
  samaa ääntä ratkaisee, ja ilman enemmistöä tilaus on riidanalainen.
- **Tilitys** yhteisillä säännöillä pistekirjanpidon kautta: havaitsijan
  palkkio vain hyväksytystä tilauksesta, jokainen tehty tarkistus maksetaan,
  loput palautetaan, eikä mitään jää lukkoon. Säännöt ja skenaariosarja ovat
  valmiina vaiheen 2 testiverkkosovitinta varten.
- **Tarkistajien tarkkuus** mitataan tunnetun vastauksen kalibrointitehtävillä,
  joita sekoitetaan jokaisen tarkistajan jonoon.
- **Tallennus** SQLiteen ja tiivisteellä osoitettuihin tiedostoihin. Yksi
  transaktio kutsua kohden, ja tila säilyy uudelleenkäynnistyksen yli.
- **HTTP-rajapinta** roolikohtaisilla avaimilla ja idempotenssilla sekä
  **komentoriviasiakas** koko ketjulle.
- **Datan julkaisu** CC BY 4.0 -lisenssillä tilityksen ja enintään 30 päivän
  embargon jälkeen, pysyvillä latausosoitteilla.

### Valmiskriteerit

| Suunnitelman kriteeri | Tila |
|---|---|
| Koko ketju toimii ledger-sovittimella komentoriviltä ja API:n kautta | ✅ testattu päästä päähän oikean HTTP-palvelimen kautta pelkillä komentorivikomennoilla |
| Hylkäys, varauksen vanheneminen, haaste ja tarkistajakierros, riita sekä tarkistajien tarkkuus tunnetun vastauksen aineistoilla on testattu | ✅ |
| Kaksoistoimitus ja kaksoistilitys eivät vaikuta kahdesti, testattu | ✅ API:n kautta (idempotentit toistot, hylätty toinen toimitus, yksi tilityskirjaus) |

## Mikä on simuloitua

- Kaikki asemat, havainnot, tilaukset, tarkistajat ja sisäänrakennetun
  luettelon neljä kohdetta. Jokainen simuloitu dokumentti kertoo sen itse, eikä
  simuloitu havainto voi täyttää oikeaa tilausta.
- Pisteet ovat kirjanpitoa, eivät rahaa. Lohkoketjua ei vielä ole.
- Demon ja testien aika on simuloitu kello.

## Näin kokeilet

```sh
pip install "orbit-watch[api] @ git+https://github.com/Haiko-Innovations/orbit-watch.git@v0.2.0#subdirectory=core"
orbit-watch demo --phase 1          # viisi tilausta, kaikki lopputulokset, muutamassa sekunnissa
cat orbit-watch-demo-phase1/transcript.md
```

Sama tuloste on repossa hakemistossa [`examples/phase1/`](../examples/phase1).
Ketjun voi ajaa itse rajapinnan ja komentorivin kautta ohjeen
[api.md](api.md#command-line-client) (englanniksi) mukaan.

## Avoimet ongelmat seuraavaan vaiheeseen

- **Vaiheen 2 valinnat**: Base Sepolia vai Optimism Sepolia (sen mukaan, missä
  EAS ja testi-USDC ovat ajantasaisen dokumentaation mukaan saatavilla),
  EAS-skeemat automaattisille tuloksille ja äänille, Foundry sopimuksille sekä
  monisignatuuri ja aikalukko tarkistajalistalle.
- **Kalibrointi oikealla datalla** vaatii arkistoituja oikeita toimituksia,
  joiden lopputulos tiedetään. Vakiomuotoiset haastetekstit ja puuttuvat
  attestaatiot paljastaisivat kalibrointitehtävät.
- **Vakuudet** varauksille, haasteille ja tarkistajille (suunnitelman avoin kysymys).
- **Henkilötiedot**: asemien koordinaatit tulevat julkisiksi datan mukana.
- **Julkinen palvelu** (P-03) vaatii TLS:n, käyttörajat, avainten kierrätyksen
  ja ylläpitotyötä.
- **Oikea IOD-esimerkki** siviilikohteesta luvan kanssa ([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).
