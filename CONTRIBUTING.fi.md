# Osallistuminen Orbit Watchiin

[English](CONTRIBUTING.md) · **Suomi**

> Tämä on käännös. Jos englanninkielinen ja suomenkielinen versio eroavat, englanninkielinen versio pätee.

Kiitos kiinnostuksesta! Orbit Watch on avoin protokolla ja referenssitoteutus
satelliittihavaintojen tilaamiseen, toimittamiseen, riippumattomaan
tarkistamiseen ja tilitykseen. Se on yhteisöprojekti, johon ovat tervetulleita
harrastajahavaitsijat, tähtitieteilijät ja kehittäjät.

Osallistumalla sitoudut noudattamaan [toimintaohjetta](CODE_OF_CONDUCT.md) (englanniksi).

## Mistä aloittaa

- [`good first issue`](https://github.com/Haiko-Innovations/orbit-watch/labels/good%20first%20issue)
  -merkityt tehtävät ovat pieniä ja itsenäisiä. Tyypillisiä esimerkkejä:
  - **uusi tarkistus** (esimerkiksi havaintotiheyden tarkistus),
  - **uusi havaintoformaatti** tai puuttuva osa IOD:stä tai CCSDS TDM:stä,
  - **uusi simuloitu asemaprofiili** (esimerkiksi kiikarilla havaitseva visuaalihavaitsija).
- Kysymykset ja ideat ovat tervetulleita issueina. Käytä issue-pohjia.
- Jos havaitset satelliitteja itse, aseman laatumittarin kokeileminen omalla
  datalla ja palaute siitä, mikä oli epäselvää, on arvokas panos.

## Perussäännöt

Nämä tulevat [projektisuunnitelmasta](README.fi.md), eikä niistä neuvotella yksittäisessä PR:ssä:

1. **Vain siviilikohteet.** Tilaukset saavat kohdistua vain sallittujen listalla
   oleviin kohteisiin, ja lista muodostetaan julkisesta GP-luettelosta. Älä lisää
   tukea sotilas-, tiedustelu- tai salaisille kohteille.
2. **Simuloitu data merkitään aina.** Jokaisessa simuloidussa aineistossa on
   `"simulated": true` (JSON), simulaatiomerkintä (IOD) tai simulaatiokommentti
   (TDM). Näitä merkintöjä ei koskaan poisteta.
3. **Tarkistus on deterministinen.** Sama syöte tuottaa tavulleen saman raportin
   jokaisella koneella ja jokaisella tuetulla Python-versiolla. Raportteihin ei
   saa vaikuttaa kellonaika, siemenetön satunnaisuus tai järjestämätön
   iterointi. Jos muutat tarkistuslogiikkaa, nosta menetelmän versiota.
4. **Ytimessä ei ole lohkoketjua eikä rahaa.** Tilitys on vaihdettava sovitin,
   joka tulee myöhemmissä vaiheissa.
5. **Tarkista lähteet, älä arvaa.** Kun käytät kirjastoa, datalähdettä tai
   standardia, linkitä PR:ssä sen ajantasainen virallinen dokumentaatio. Älä
   kirjoita versioita, osoitteita tai URL-osoitteita muistista.
6. **Kunnioita datan tarjoajia.** Ratadataa lataavan koodin pitää noudattaa
   tarjoajan käyttöehtoja (CelesTrakilla: lataa kerran päivitystä kohden ja
   lopeta heti, jos vastaus on muu kuin 200).

## Kehitysympäristö

Python-ydin on hakemistossa [`core/`](core). Tarvitset Python 3.12:n tai uudemman.

[uv](https://docs.astral.sh/uv/):lla (CI käyttää tätä):

```sh
cd core
uv sync --locked
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Pelkällä pipillä:

```sh
cd core
python -m venv .venv
. .venv/bin/activate
pip install -e . pytest ruff
pytest
```

## Pull requestit

- Tee työ haarassa ja avaa pull request `main`-haaraan. PR:t yhdistetään squash-mergellä.
- CI:n (`tarkistus`-tarkistus) pitää mennä läpi: lint, testit vanhimmalla ja
  uusimmalla tuetulla Pythonilla, tavallinen `pip install`, salaisuuksien
  skannaus ja haavoittuvuustarkistus.
- Lisää tai päivitä testit. Jokaiseen virhekorjaukseen kuuluu testi, joka epäonnistuu ilman korjausta.
- Pidä PR:t rajattuina. Uusi tarkistus, uusi formaatti tai uusi asemaprofiili on hyvä koko.
- Älä commitoi salaisuuksia, API-avaimia tai henkilötietoja. Muiden ihmisten
  oikeat havainnot tarvitsevat luvan ja lähdemerkinnän ennen kuin ne lisätään repositorioon.

## Kieli

Ensisijainen kieli on englanti: koodi, kommentit, dokumentaatio,
commit-viestit, issuet ja pull requestit. Osalla keskeisistä dokumenteista on
suomenkielinen käännös (`*.fi.md`). Jos muutat dokumenttia, jolla on käännös,
päivitä myös käännös tai kerro PR:ssä, ettet pystynyt, niin ylläpitäjä tekee
sen. Jos versiot eroavat, englanninkielinen versio pätee.

## Lisenssi

Orbit Watch on lisensoitu [Apache License 2.0](LICENSE) -lisenssillä. Lähettämällä
muutoksen hyväksyt, että se lisensoidaan samoilla ehdoilla (lisenssin kohta 5).
Orbit Watchin kautta julkaistun havaintodatan oletuslisenssi on CC BY 4.0.

## Tietoturva

Älä raportoi tietoturvaongelmia julkisissa issueissa. Katso [SECURITY.md](SECURITY.md).
