# Tiekartta ja tilanne

[English](roadmap.md) · **Suomi**

> Tämä on käännös. Jos englanninkielinen ja suomenkielinen versio eroavat, englanninkielinen versio pätee.

Tämä sivu kertoo, missä Orbit Watch on nyt ja mitä seuraavaksi tehdään. Koko
aloitussuunnitelma on tiedostossa [plan.fi.md](plan.fi.md), päätökset
perusteluineen tiedostossa [decisions.md](decisions.md) (englanniksi) ja
julkaistut muutokset [muutoslokissa](../CHANGELOG.md) (englanniksi). Työtä
seurataan [GitHubin milestoneissa](https://github.com/Haiko-Innovations/orbit-watch/milestones).

Jokainen pull request, joka saa tiekartan vaiheen valmiiksi, päivittää myös tämän sivun.

## Tilanne (12.11.2026)

**Vaihe 1 on valmis** ja julkaistu versiona 0.2.0: tilaukset, optimistinen
tarkistus, pistekirjanpito, tarkistajien tarkkuus, tallennus, HTTP-rajapinta,
komentoriviasiakas ja datan julkaisu. Katso [vaiheen 1 yhteenveto](phase-1-summary.fi.md).
Vaihe 0 julkaistiin
[versiona 0.1.0](https://github.com/Haiko-Innovations/orbit-watch/releases/tag/v0.1.0);
sen ainoa avoin kriteeri, oikea julkinen IOD-esimerkki, on yhä avoinna
([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).

**Nyt: vaihe 2**, tilitys testiverkossa. Sen päätökset hyväksyttiin
11.11.2026. Askeleet 2.1–2.7 ovat valmiit: sopimusprojekti, tilityssäännöt
ketjussa, EAS-attestaatiot tarkistajakierroksineen, tarkistajarekisteri
Safe-monisignatuurin (2/3) ja 48 tunnin aikalukon takana, Pythonin
`evm-testnet`-sovitin, joka läpäisee vaiheen 1 tilityksen skenaariosarjan
paikallisessa ketjussa, palvelu, rajapinta ja komentorivi ketjun päällä sekä
käyttöönotto Base Sepoliaan ([base-sepolia.md](base-sepolia.md)). Ketjussa
jokainen osapuoli allekirjoittaa omalla lompakollaan. Seuraavaksi askel 2.8:
vaiheen 2 demo Base Sepoliassa ja julkaisu 0.3.0.

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
| ✅ **1.6 API** ([#16](https://github.com/Haiko-Innovations/orbit-watch/issues/16)) | HTTP-rajapinta elinkaarelle. Roolikohtaiset API-avaimet: aseman avaimella voi vain toimittaa, ei koskaan siirtää pisteitä. Idempotenssiavain jokaisessa muuttavassa kutsussa. | Kaksoistoimitus ja kaksoistilitys eivät vaikuta kahdesti; testattu API:n kautta. |
| ✅ **1.7 Komentorivi** ([#17](https://github.com/Haiko-Innovations/orbit-watch/issues/17)) | `submit` sekä uudet komennot tilauksille, varauksille, haasteille ja tarkistuksille API:a vasten. | Koko ketju toimii komentoriviltä. |
| ✅ **1.8 Datan julkaisu ja vaiheen 1 demo** ([#18](https://github.com/Haiko-Innovations/orbit-watch/issues/18)) | Lisenssi (oletus CC BY 4.0), enintään 30 päivän embargo, tiedostojen säilytys ja pysyvät latausosoitteet. Vaiheen 1 demo ja raportti. | Vaiheen 1 valmiskriteerit tiedostossa [plan.fi.md](plan.fi.md) täyttyvät; julkaistaan 0.2.0. |

Päätökset P-01–P-07 tiedostossa [decisions.md](decisions.md#phase-1-decisions)
hyväksyttiin 11.11.2026 ([#10](https://github.com/Haiko-Innovations/orbit-watch/issues/10)).
Vaihe 1.1 on kuvattu tiedostossa [lifecycle.md](lifecycle.md), vaihe 1.2
tiedostossa [settlement.md](settlement.md), vaihe 1.3 tiedostossa
[optimistic-verification.md](optimistic-verification.md), vaihe 1.4
tiedostossa [reviewer-accuracy.md](reviewer-accuracy.md), vaihe 1.5
tiedostossa [storage.md](storage.md), vaiheet 1.6 ja 1.7 tiedostossa
[api.md](api.md) ja vaihe 1.8 tiedostossa [data-publication.md](data-publication.md)
(englanniksi).

### Vaihe 2: tilitys testiverkossa (tavoiteversio 0.3.0)

Vaihe 2 siirtää tilityksen pistekirjanpidosta EVM L2 -**testiverkon**
escrow-sopimukseen, ja automaattiset tulokset ja tarkistajien äänet tallennetaan
**EAS-attestaatioina**. Säännöt pysyvät täsmälleen vaiheen 1 sääntöinä:
testiverkkosovittimen on läpäistävä sama tilityksen skenaariosarja kuin
ledgerin. Ei pääverkkoa, ei omaa tokenia eikä oikeaa rahaa: testi-USDC:llä ei
ole arvoa.

Suunnitelman valinnat ovat **päätöksiä P2-01–P2-11** tiedostossa
[decisions.md](decisions.md#phase-2-decisions) (englanniksi), ja ne
hyväksyttiin 11.11.2026 ([#27](https://github.com/Haiko-Innovations/orbit-watch/issues/27)). Lyhyesti: **Base Sepolia**,
Circlen **testi-USDC**, EAS esiasennetussa osoitteessaan, **Foundry** ja
**OpenZeppelin Contracts**, päivittämätön escrow-sopimus, tarkistajarekisteri
**Safe-monisignatuurin ja julkisen aikalukon** takana sekä Python-sovitin
**web3.py**:llä.

| Vaihe | Sisältö | Valmis, kun |
|---|---|---|
| ✅ **2.1 Sopimusprojekti** ([#28](https://github.com/Haiko-Innovations/orbit-watch/issues/28)) | `contracts/`-Foundry-projekti, OpenZeppelin kiinnitettynä, käännös ja testit `tarkistus`-tarkistuksessa; escrow-runko `fund`- ja `refund`-toiminnoilla; kieltäytyy toimimasta muussa ketjussa kuin Base Sepoliassa tai paikallisessa Anvilissa. | `forge test` ajetaan CI:ssä; rahoitus ja palautus toimivat paikallisessa ketjussa. |
| ✅ **2.2 Tilityssäännöt ketjussa** ([#29](https://github.com/Haiko-Innovations/orbit-watch/issues/29)) | Vaiheen 1 tilityssäännöt Solidityllä: jako lukitaan rahoitettaessa, määräajat ketjussa, kenen tahansa käynnistettävä ja idempotentti tilitys, ylläpitäjillä ei pääsyä talletuksiin. | Fuzz- ja invarianttitestit: talletus = palkkiot + palautukset, tilaus tilitetään kerran, ulkopuolinen ei voi nostaa varoja. |
| ✅ **2.3 Attestaatiot** ([#30](https://github.com/Haiko-Innovations/orbit-watch/issues/30)) | EAS-skeemat automaattiselle tulokselle ja tarkistajien äänille; escrow lukee automaattisen attestaation, avaa haastejakson ja laskee rekisteröityjen tarkistajien 2/3-äänet. | Haastamaton, haastettu-hyväksytty, haastettu-hylätty ja riita tilittyvät ketjussa attestaatioista. |
| ✅ **2.4 Tarkistajarekisteri** ([#31](https://github.com/Haiko-Innovations/orbit-watch/issues/31)) | Tarkistajien osoitteiden rekisteri, jonka omistaa OpenZeppelinin TimelockController, ja sen ehdottajana Safe-monisignatuuri; oikeudet dokumentoidaan READMEen. | Tarkistajien lisäys ja poisto onnistuu vain monisignatuurin ja aikalukon kautta; testattu. |
| ✅ **2.5 Testiverkkosovitin** ([#32](https://github.com/Haiko-Innovations/orbit-watch/issues/32)) | `evm-testnet`-tilityssovitin Pythonilla (web3.py): `fund`, `reserve`, `attest`, `settle`, `refund` transaktioina ja attestaatioina. | Sovitin läpäisee tilityksen skenaariosarjan paikallista Anvil-ketjua vasten CI:ssä. |
| ✅ **2.6 Palvelu, API ja komentorivi** ([#33](https://github.com/Haiko-Innovations/orbit-watch/issues/33)) | Lompakko-osoitteet osapuolille; odottavat, vahvistetut ja epäonnistuneet transaktiot erikseen; ketju on maksujen ensisijainen lähde; linkit lohkoselaimeen; allekirjoitus käyttäjän omalla lompakolla tai avainsäilöllä. | Koko ketju toimii komentoriviltä ja API:n kautta paikallista ketjua vasten; mikään avain ei lähde omistajaltaan. |
| ✅ **2.7 Testiverkkoon vienti** ([#34](https://github.com/Haiko-Innovations/orbit-watch/issues/34)) | Base Sepolian käyttöönottoskriptit ja asetukset, skeemojen rekisteröinti, faucet-ohjeet (testi-ETH ja -USDC), testiverkkomerkinnät kaikkialla. | Sopimukset toimivat Base Sepoliassa dokumentoitujen ohjeiden mukaan. |
| **2.8 Vaiheen 2 demo** ([#35](https://github.com/Haiko-Innovations/orbit-watch/issues/35)) | Demo Base Sepoliassa erillisillä lompakoilla jokaiselle osapuolelle sekä vaiheen 2 yhteenveto. | Vaiheen 2 valmiskriteerit tiedostossa [plan.fi.md](plan.fi.md) täyttyvät; julkaistaan 0.3.0. |

### Vaihe 3 (myöhemmin)

Verkkosovellus roolikohtaisine näkymineen; suunnitellaan tarkemmin, kun vaihe 2 on valmis.

## Miten työskentelemme

- Yksi pull request kerrallaan `main`-haarasta, ja ylläpitäjä yhdistää sen
  squash-mergellä, kun `tarkistus` on mennyt läpi. Ei pinottuja pull
  requesteja: squash-mergen kanssa ne menevät konfliktiin
  ([D-10](decisions.md#d-10-one-pull-request-at-a-time-on-main)).
- Jokainen käyttäjälle näkyvä muutos lisää rivin [muutoslokin](../CHANGELOG.md)
  `Unreleased`-osioon.
- Julkaisut tehdään ohjeen [releasing.md](releasing.md) mukaan: yksi
  minor-versio vaihetta kohden niin kauan kuin versio on 0.x, patch-versiot korjauksille.
