# Tiekartta ja tilanne

[English](roadmap.md) · **Suomi**

> Tämä on käännös. Jos englanninkielinen ja suomenkielinen versio eroavat, englanninkielinen versio pätee.

Tämä sivu kertoo, missä Orbit Watch on nyt ja mitä seuraavaksi tehdään. Koko
aloitussuunnitelma on tiedostossa [plan.fi.md](plan.fi.md), päätökset
perusteluineen tiedostossa [decisions.md](decisions.md) (englanniksi) ja
julkaistut muutokset [muutoslokissa](../CHANGELOG.md) (englanniksi). Työtä
seurataan [GitHubin milestoneissa](https://github.com/Haiko-Innovations/orbit-watch/milestones).

Jokainen pull request, joka saa tiekartan vaiheen valmiiksi, päivittää myös tämän sivun.

## Tilanne (11.11.2026)

**Vaihe 0, avoin ydin, on valmis** ja julkaistu
[versiona 0.1.0](https://github.com/Haiko-Innovations/orbit-watch/releases/tag/v0.1.0).
**Vaihe 1 on käynnissä:** päätökset on hyväksytty, ja vaiheet 1.1 (tilauksen
elinkaari), 1.2 (tilitys ja pistekirjanpito), 1.3 (optimistinen tarkistus) ja
1.4 (tarkistajien tarkkuus) ja 1.5 (tallennus) ovat valmiit.

| Vaiheen 0 valmiskriteeri | Tila |
|---|---|
| `pip install` ja yksi komento tuottavat simuloidun aineiston ja tarkistusraportin | ✅ `orbit-watch demo` |
| Kaikki kuusi testiaineistoa saavat oikean tuloksen ja ymmärrettävän selityksen | ✅ tarkistetaan CI:ssä tavulleen Python 3.12:lla ja 3.15:llä |
| Laatumittari toimii simuloidulla datalla | ✅ |
| …ja yhdellä oikealla julkisella IOD-esimerkillä | ❌ avoin: katso [#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8) |
| README, CONTRIBUTING, toimintaohje, issue-pohjat, good first issuet | ✅ |

Puuttuva oikea esimerkki on dataongelma, ei koodiongelma: tuoreet julkiset
IOD-havainnot koskevat lähes kaikki salaisia kohteita, joita Orbit Watch ei
käsittele. Se ei estä vaihetta 1.

## Seuraavat askeleet

### Vaiheen 0 jatkotyöt (milestone "Phase 0 follow-up")

Rinnakkain vaiheen 1 kanssa, lähinnä yhteisöä varten:

- ✅ Julkaistu 0.1.0. Kiinnitetään repositorio Haiko Innovationsin profiiliin.
- Oikea IOD-esimerkki siviilikohteesta luvan kanssa ([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).
- Good first issuet: vanhemmat IOD-ekvinoksit ([#4](https://github.com/Haiko-Innovations/orbit-watch/issues/4)),
  radan aikajärjestyksen tarkistus ([#5](https://github.com/Haiko-Innovations/orbit-watch/issues/5)),
  järjestelmäkameran asemaprofiili ([#6](https://github.com/Haiko-Innovations/orbit-watch/issues/6)).
- Simulaattorin valaistusmalli ([#7](https://github.com/Haiko-Innovations/orbit-watch/issues/7)).

### Vaihe 1: tilaukset, optimistinen tarkistus ja API (tavoiteversio 0.2.0)

Vaihe 1 laajentaa yksittäiset tarkistukset koko tilauksen elinkaareksi, yhä
ilman rahaa: pelkkiä pisteitä kirjaava ledger-sovitin noudattaa täsmälleen
samoja sääntöjä kuin myöhempi rahallinen tilitys. Vaiheet ovat
riippuvuusjärjestyksessä, ja kukin on yksi pull request (enintään kaksi).
Toimialalogiikka tehdään ensin ilman tallennusta ja verkkoa, jotta se voidaan
testata kattavasti; tallennus ja API tulevat sen jälkeen.

| Vaihe | Sisältö | Valmis, kun |
|---|---|---|
| ✅ **1.1 Tilauksen elinkaari** ([#11](https://github.com/Haiko-Innovations/orbit-watch/issues/11)) | Tilakone: luonnos → avoin → (rahoitettu) → varattu → toimitettu → tarkistettu → haastejakso → hyväksytty / hylätty / riidanalainen → tilitetty, sekä vanhentunut. Ehtojen tilannekuva tiivisteineen. Ulkoa annettava kello aikakatkaisuja varten. | Jokainen sallittu ja kielletty siirtymä on testattu; tilakaavio dokumentaatiossa. |
| ✅ **1.2 Tilityssovitin ja ledger** ([#12](https://github.com/Haiko-Innovations/orbit-watch/issues/12)) | Rajapinta `fund`, `reserve`, `attest`, `settle`, `refund`. Ledger-sovitin: kokonaislukupisteet, kahdenkertainen kirjanpito, idempotenssiavaimet. Skenaariosarja, joka jokaisen sovittimen on läpäistävä. | Talletus = palkkiot + palautukset jokaisessa skenaariossa; toistettu tilitys ei vaikuta toista kertaa. |
| ✅ **1.3 Optimistinen tarkistus** ([#13](https://github.com/Haiko-Innovations/orbit-watch/issues/13)) | Automaattinen raportti → haastejakso (oletus 24 h, kiinnitetään ehtoihin) → haastettaessa kolme ennalta hyväksyttyä tarkistajaa, 2/3 ratkaisee, kukaan ei tarkista omaa toimitustaan. Riitasääntö. Tarkistajat saavat palkkion tehdystä tarkistuksesta lopputuloksesta riippumatta. | Haastamaton, haastettu-hyväksytty, haastettu-hylätty ja ei enemmistöä (riita) testattu päästä päähän ledgerillä. |
| ✅ **1.4 Tarkistajien tarkkuus** ([#14](https://github.com/Haiko-Innovations/orbit-watch/issues/14)) | Simulaattorin tunnetun vastauksen aineistoja sekoitetaan tarkistajien tehtäviin; tarkkuus tarkistajittain. | Kaiken hyväksyvän tarkistajan tarkkuus näkyy matalana; testattu. |
| ✅ **1.5 Tallennus** ([#15](https://github.com/Haiko-Innovations/orbit-watch/issues/15)) | SQLite-skeema ja migraatiot tilauksille, varauksille, toimituksille, raporteille, haasteille ja ledgerin kirjauksille; tiivisteellä osoitettu tiedostovarasto. | Tila säilyy uudelleenkäynnistyksen yli; migraatiot testattu tyhjästä. |
| **1.6 API** ([#16](https://github.com/Haiko-Innovations/orbit-watch/issues/16)) | HTTP-rajapinta elinkaarelle. Roolikohtaiset API-avaimet: aseman avaimella voi vain toimittaa, ei koskaan siirtää pisteitä. Idempotenssiavain jokaisessa muuttavassa kutsussa. | Kaksoistoimitus ja kaksoistilitys eivät vaikuta kahdesti; testattu API:n kautta. |
| **1.7 Komentorivi** ([#17](https://github.com/Haiko-Innovations/orbit-watch/issues/17)) | `submit` sekä uudet komennot tilauksille, varauksille, haasteille ja tarkistuksille API:a vasten. | Koko ketju toimii komentoriviltä. |
| **1.8 Datan julkaisu ja vaiheen 1 demo** ([#18](https://github.com/Haiko-Innovations/orbit-watch/issues/18)) | Lisenssi (oletus CC BY 4.0), enintään 30 päivän embargo, tiedostojen säilytys ja pysyvät latausosoitteet. Vaiheen 1 demo ja raportti. | Vaiheen 1 valmiskriteerit tiedostossa [plan.fi.md](plan.fi.md) täyttyvät; julkaistaan 0.2.0. |

Päätökset P-01–P-07 tiedostossa [decisions.md](decisions.md#phase-1-decisions)
hyväksyttiin 11.11.2026 ([#10](https://github.com/Haiko-Innovations/orbit-watch/issues/10)).
Vaihe 1.1 on kuvattu tiedostossa [lifecycle.md](lifecycle.md), vaihe 1.2
tiedostossa [settlement.md](settlement.md), vaihe 1.3 tiedostossa
[optimistic-verification.md](optimistic-verification.md), vaihe 1.4
tiedostossa [reviewer-accuracy.md](reviewer-accuracy.md) ja vaihe 1.5
tiedostossa [storage.md](storage.md) (englanniksi).

### Vaiheet 2 ja 3 (myöhemmin)

- **Vaihe 2:** tilitys EVM L2 -testiverkossa EAS-attestaatioilla saman
  sovitinrajapinnan ja saman skenaariosarjan takana kuin ledger. Ei pääverkkoa.
- **Vaihe 3:** verkkosovellus roolikohtaisine näkymineen.

Nämä suunnitellaan tarkemmin vasta, kun vaihe 1 on valmis.

## Miten työskentelemme

- Yksi pull request kerrallaan `main`-haarasta, ja ylläpitäjä yhdistää sen
  squash-mergellä, kun `tarkistus` on mennyt läpi. Ei pinottuja pull
  requesteja: squash-mergen kanssa ne menevät konfliktiin
  ([D-10](decisions.md#d-10-one-pull-request-at-a-time-on-main)).
- Jokainen käyttäjälle näkyvä muutos lisää rivin [muutoslokin](../CHANGELOG.md)
  `Unreleased`-osioon.
- Julkaisut tehdään ohjeen [releasing.md](releasing.md) mukaan: yksi
  minor-versio vaihetta kohden niin kauan kuin versio on 0.x, patch-versiot korjauksille.
