# Tiekartta ja tilanne

[English](roadmap.md) · **Suomi**

> Tämä on käännös. Jos englanninkielinen ja suomenkielinen versio eroavat, englanninkielinen versio pätee.

Tämä sivu kertoo, missä Orbit Watch on nyt ja mitä seuraavaksi tehdään. Koko
aloitussuunnitelma on tiedostossa [plan.fi.md](plan.fi.md), päätökset
perusteluineen tiedostossa [decisions.md](decisions.md) (englanniksi) ja
julkaistut muutokset [muutoslokissa](../CHANGELOG.md) (englanniksi). Työtä
seurataan [GitHubin milestoneissa](https://github.com/Haiko-Innovations/orbit-watch/milestones).

Jokainen pull request, joka saa tiekartan vaiheen valmiiksi, päivittää myös tämän sivun.

## Tilanne (13.11.2026)

**Vaihe 2 on valmis** ja julkaistu versiona 0.3.0: tilitys Base Sepolia
-testiverkossa Circlen testi-USDC:llä. Päivittämätön escrow-sopimus pitää
talletukset, automaattisen tarkistuksen tulokset ja tarkistajien äänet ovat
EAS-attestaatioita, tarkistajarekisteri on Safe-monisignatuurin (2/3) ja 48
tunnin aikalukon takana, ja palvelu, rajapinta ja komentorivi toimivat ketjun
päällä niin, että jokainen osapuoli allekirjoittaa omalla lompakollaan.
Sopimukset on viety Base Sepoliaan ([base-sepolia.md](base-sepolia.md)), ja
vaiheen 2 demo ajettiin siellä jokaiselle osapuolelle omalla lompakolla.
Katso [vaiheen 2 yhteenveto](phase-2-summary.fi.md).

Vaihe 1 julkaistiin versiona 0.2.0 ([vaiheen 1 yhteenveto](phase-1-summary.fi.md))
ja vaihe 0
[versiona 0.1.0](https://github.com/Haiko-Innovations/orbit-watch/releases/tag/v0.1.0).
Vaiheen 0 ainoa avoin kriteeri, oikea julkinen IOD-esimerkki, on yhä avoinna
([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).

**Vaihe 3 on käynnissä**: verkkosovellus. Sen päätökset P3-01–P3-11
hyväksyttiin 13.11.2026 ([#46](https://github.com/Haiko-Innovations/orbit-watch/issues/46)). Valmiina: sovelluksen projekti
hakemistossa `web/`, palvelu tarjoaa sen, julkiset sivut ja paikallinen
ympäristö yhdellä komennolla (3.1), kirjautuminen lompakolla (3.2),
transaktiot selaimessa saldoineen ja nostoineen (3.3), tilaajan näkymä (3.4)
sekä havaitsijan näkymä (3.5)
([web.md](web.md), englanniksi).

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
| ✅ **2.8 Vaiheen 2 demo** ([#35](https://github.com/Haiko-Innovations/orbit-watch/issues/35)) | Demo Base Sepoliassa erillisillä lompakoilla jokaiselle osapuolelle sekä vaiheen 2 yhteenveto. | Vaiheen 2 valmiskriteerit tiedostossa [plan.fi.md](plan.fi.md) täyttyvät; julkaistaan 0.3.0. |

### Vaihe 3: verkkosovellus (tavoiteversio 0.4.0)

Vaihe 3 tuo vaiheen 2 järjestelmän selaimeen: yksi verkkosovellus, jossa on
näkymät tilaajille, havaitsijoille, tarkistajille ja ylläpitäjille, aseman
laatumittari ja julkinen attestaatioselain. Jokainen osapuoli allekirjoittaa
omalla lompakollaan selaimessa, eikä selaimella ole oikeuksia, joita
rajapinta ei anna: säännöt pysyvät palvelussa ja sopimuksissa. Edelleen vain
testiverkko, eikä julkista käyttöönottoa, ellei toisin päätetä.

Suunnitelman valinnat ovat **päätöksiä P3-01–P3-11** tiedostossa
[decisions.md](decisions.md#phase-3-decisions) (englanniksi), ja ne
hyväksyttiin 13.11.2026 ([#46](https://github.com/Haiko-Innovations/orbit-watch/issues/46)). Lyhyesti: **TypeScriptillä ja Reactilla**
tehty yhden sivun sovellus, joka käännetään **Vitellä** ja jota Python-palvelu
tarjoaa, lompakot **viemin** ja **EIP-6963**:n kautta, **Sign-In with
Ethereum** ja istuntoeväste, **Biome** ja **TypeScript 7**, päästä päähän
-testit **Playwrightilla** paikallista ketjua vasten sekä **WCAG 2.2 AA**.

| Vaihe | Sisältö | Valmis, kun |
|---|---|---|
| ✅ **3.1 Verkkoprojekti ja paikallinen ympäristö** ([#47](https://github.com/Haiko-Innovations/orbit-watch/issues/47)) | `web/`: TypeScriptillä ja Reactilla tehty yhden sivun sovellus, joka käännetään Vitellä ja tarkistetaan `tarkistus`-tarkistuksessa (Biome, tyyppitarkistus, yksikkötestit, käännös) npm-asennuksilla, jotka eivät aja skriptejä; `orbit-watch serve --web` tarjoaa sen rajapinnan omasta osoitteesta; paikallinen ympäristö yhdellä komennolla (Anvil, sopimukset, palvelu, simuloidut osapuolet); julkiset sivut verkosta ja avoimista tilauksista. | CI kääntää ja testaa sovelluksen; Playwright-testi avaa sen paikallista ympäristöä vasten; jokainen sivu näyttää testiverkkomerkinnän. |
| ✅ **3.2 Kirjautuminen lompakolla** ([#48](https://github.com/Haiko-Innovations/orbit-watch/issues/48)) | Lompakoiden löytäminen (EIP-6963), oikea ketju, Sign-In with Ethereum (ERC-4361) ja istuntoeväste, uloskirjautuminen; tilaajat ja asemat rekisteröityvät itse. | Päästä päähän -testi kirjautuu testilompakolla; uudelleen käytetyt, vanhentuneet ja vieraat viestit hylätään; mikään avain tai salaisuus ei päädy selaimeen, testattu. |
| ✅ **3.3 Transaktiot selaimessa** ([#49](https://github.com/Haiko-Innovations/orbit-watch/issues/49)) | Yksi kulku jokaiselle valmistellulle transaktiolle: mitä se tekee, lompakko allekirjoittaa ja lähettää, odottava, vahvistettu tai epäonnistunut lohkoselainlinkkeineen; väärä ketju, hylätty allekirjoitus ja peruutus selitetään; saldot ja nostot. | Nosto toimii selaimessa päästä päähän; jokainen virhetilanne näytetään ja testataan. |
| ✅ **3.4 Tilaajan näkymä** ([#50](https://github.com/Haiko-Innovations/orbit-watch/issues/50)) | Tilauksen luonti (kohde sallittujen listalta, aikaikkuna, määräaika, toimitusvaatimukset), jako ja maksut näkyvät ennen rahoitusta, rahoitus, seuranta ja haaste, aineiston ja raportin lataus, maksut ja palautukset. | Päästä päähän: selaimessa luotu ja rahoitettu tilaus toimitetaan ja tilitetään, ja sen raportti ladataan. |
| ✅ **3.5 Havaitsijan näkymä** ([#51](https://github.com/Haiko-Innovations/orbit-watch/issues/51)) | Simuloidun aseman rekisteröinti, avoimet tilaukset ja varaus, havaintojen lähetys (SHA-256 tarkistetaan), syyt toimituksen hyväksymiselle tai hylkäämiselle, haaste, palkkioiden seuranta. | Päästä päähän: varaus ja toimitus selaimessa; hyväksytty ja hylätty toimitus näyttävät syynsä. |
| **3.6 Tarkistajan näkymä** ([#52](https://github.com/Haiko-Innovations/orbit-watch/issues/52)) | Annetut tehtävät, raportti ja tarkistukset, hyväksyntä tai hylkäys perusteluineen EAS-attestaationa allekirjoitettuna, palkkiot ja tarkkuus. | Päästä päähän: selaimessa annetut äänet ovat attestaatioita paikallisessa ketjussa, ja kierros tilitetään. |
| **3.7 Ylläpitäjän näkymä ja julkiset sivut** ([#53](https://github.com/Haiko-Innovations/orbit-watch/issues/53)) | Tilaukset, toimitukset, maksut, virheet ja tapahtumaloki; `tick`; tarkistajarekisteri, aikalukon jono ja Safen omassa sovelluksessa ehdotettavat Safe-transaktiot; simulaattori ja demoaineistot; aseman laatumittari ja julkinen attestaatioselain. | Päästä päähän ylläpitäjälle; näkymä ei voi tehdä mitään, minkä rajapinta kieltää, testattu; julkiset sivut toimivat kirjautumatta. |
| **3.8 Vaiheen 3 demo** ([#54](https://github.com/Haiko-Innovations/orbit-watch/issues/54)) | Koko ketju selaimessa Base Sepoliassa, jokaisella roolilla oma lompakko, jokaisen näkymän saavutettavuuskatselmointi ja vaiheen 3 yhteenveto. | Alla olevat vaiheen 3 valmiskriteerit täyttyvät; julkaisu 0.4.0. |

**Vaiheen 3 valmiskriteerit** ([P3-11](decisions.md#p3-11-phase-3-completion-criteria);
aloitussuunnitelmassa ei ole kriteerejä vaiheelle 3):

1. Verkkosovellus käynnistyy dokumentoiduilla ohjeilla paikallisessa ketjussa
   ja Base Sepoliassa.
2. Jokainen rooli kirjautuu omalla lompakollaan; yksityisavain,
   siemenlause tai palvelimen salaisuus ei päädy selaimeen eikä palveluun,
   testattu.
3. Tilaaja luo, rahoittaa ja seuraa tilausta, lataa sen aineiston ja raportin
   sekä näkee maksut ja palautukset selaimessa.
4. Havaitsija rekisteröi simuloidun aseman, varaa tilauksen, toimittaa ja
   seuraa palkkioita selaimessa.
5. Tarkistaja näkee annetut tehtävät, allekirjoittaa äänet perusteluineen
   EAS-attestaatioina sekä näkee palkkiot ja tarkkuuden selaimessa.
6. Ylläpitäjä näkee tilaukset, toimitukset, maksut, virheet ja tapahtumalokin,
   valmistelee tarkistajamuutokset Safelle ja aikalukolle sekä käynnistää
   simulaattorin ilman oikeuksia, joita rajapinta ei anna, testattu.
7. Odottavat, vahvistetut ja epäonnistuneet transaktiot näytetään erikseen
   lohkoselainlinkkeineen.
8. Aseman laatumittari ja julkinen attestaatioselain toimivat kirjautumatta.
9. Testiverkkomerkintä näkyy jokaisella sivulla, ja simuloitu data on merkitty.
10. Jokaisen roolin päästä päähän -testit ja jokaisen näkymän
    saavutettavuustarkistukset ajetaan CI:ssä paikallista ketjua vasten.

## Miten työskentelemme

- Yksi pull request kerrallaan `main`-haarasta, ja ylläpitäjä yhdistää sen
  squash-mergellä, kun `tarkistus` on mennyt läpi. Ei pinottuja pull
  requesteja: squash-mergen kanssa ne menevät konfliktiin
  ([D-10](decisions.md#d-10-one-pull-request-at-a-time-on-main)).
- Jokainen käyttäjälle näkyvä muutos lisää rivin [muutoslokin](../CHANGELOG.md)
  `Unreleased`-osioon.
- Julkaisut tehdään ohjeen [releasing.md](releasing.md) mukaan: yksi
  minor-versio vaihetta kohden niin kauan kuin versio on 0.x, patch-versiot korjauksille.
