# Tiekartta ja tilanne

[English](roadmap.md) · **Suomi**

> Tämä on käännös. Jos englanninkielinen ja suomenkielinen versio eroavat, englanninkielinen versio pätee.

Tämä sivu kertoo, missä Orbit Watch on nyt ja mitä seuraavaksi tehdään. Koko
aloitussuunnitelma on tiedostossa [plan.fi.md](plan.fi.md), päätökset
perusteluineen tiedostossa [decisions.md](decisions.md) (englanniksi) ja
julkaistut muutokset [muutoslokissa](../CHANGELOG.md) (englanniksi). Työtä
seurataan [GitHubin milestoneissa](https://github.com/Haiko-Innovations/orbit-watch/milestones).

Jokainen pull request, joka saa tiekartan vaiheen valmiiksi, päivittää myös tämän sivun.

## Tilanne (14.11.2026)

**Vaihe 3 on valmis** ja julkaistu versiona 0.4.0: verkkosovellus. Jokainen
osapuoli kirjautuu ja allekirjoittaa omalla lompakollaan selaimessa; tilaajilla,
havaitsijoilla, tarkistajilla ja ylläpitäjillä on omat näkymänsä; aseman
laatumittari ja attestaatioselain ovat julkisia sivuja; ja jokaisen roolin
päästä päähän -testit sekä jokaisen näkymän saavutettavuuskatselmointi
ajetaan CI:ssä paikallista ketjua vasten. Vaiheen 3 demossa koko ketju
ajettiin selaimessa Base Sepoliassa, jokaisella roolilla oma lompakko. Katso
[vaiheen 3 yhteenveto](phase-3-summary.fi.md). Palvelu toimii yhä vain
paikallisesti ([P3-10](decisions.md#p3-10-no-public-deployment-in-phase-3)).

**Vaihe 4 on suunniteltu**: julkinen testiverkkopalvelu, eli palvelu ja
verkkosovellus verkossa Base Sepoliassa, yhä SIMULOITUNA. Sen päätökset
P4-01–P4-13 odottavat hyväksyntää ([#67](https://github.com/Haiko-Innovations/orbit-watch/issues/67)).

Vaihe 2 julkaistiin versiona 0.3.0 ([vaiheen 2 yhteenveto](phase-2-summary.fi.md)),
vaihe 1 versiona 0.2.0 ([vaiheen 1 yhteenveto](phase-1-summary.fi.md)) ja vaihe 0
[versiona 0.1.0](https://github.com/Haiko-Innovations/orbit-watch/releases/tag/v0.1.0).
Vaiheen 0 ainoa avoin kriteeri, oikea julkinen IOD-esimerkki, on yhä avoinna
([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).

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
| ✅ **3.6 Tarkistajan näkymä** ([#52](https://github.com/Haiko-Innovations/orbit-watch/issues/52)) | Annetut tehtävät, raportti ja tarkistukset, hyväksyntä tai hylkäys perusteluineen EAS-attestaationa allekirjoitettuna, palkkiot ja tarkkuus. | Päästä päähän: selaimessa annetut äänet ovat attestaatioita paikallisessa ketjussa, ja kierros tilitetään. |
| ✅ **3.7 Ylläpitäjän näkymä ja julkiset sivut** ([#53](https://github.com/Haiko-Innovations/orbit-watch/issues/53)) | Tilaukset, toimitukset, maksut, virheet ja tapahtumaloki; `tick`; tarkistajarekisteri, aikalukon jono ja Safen omassa sovelluksessa ehdotettavat Safe-transaktiot; simulaattori ja demoaineistot; aseman laatumittari ja julkinen attestaatioselain. | Päästä päähän ylläpitäjälle; näkymä ei voi tehdä mitään, minkä rajapinta kieltää, testattu; julkiset sivut toimivat kirjautumatta. |
| ✅ **3.8 Vaiheen 3 demo** ([#54](https://github.com/Haiko-Innovations/orbit-watch/issues/54)) | Koko ketju selaimessa Base Sepoliassa, jokaisella roolilla oma lompakko, jokaisen näkymän saavutettavuuskatselmointi ja vaiheen 3 yhteenveto. | Alla olevat vaiheen 3 valmiskriteerit täyttyvät; julkaisu 0.4.0. |

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

### Vaihe 4: julkinen testiverkkopalvelu (tavoiteversio 0.5.0)

Vaihe 4 vie palvelun ja verkkosovelluksen verkkoon, jotta havaitsijat ja
tilaajat voivat kokeilla koko ketjua omilla lompakoillaan asentamatta mitään.
Edelleen vain Base Sepolia -testiverkko, ja kaikki on yhä SIMULOITUA: ei
oikeaa rahaa eikä oikeita havaintoja. Samalla palvelu siirtyy PostgreSQLiin,
muuttuu tilattomaksi ja oppii toimimaan itse. Se saa rajat väärinkäyttöä
vastaan, tietosuojaselosteen ja käyttöehdot, varmuuskopiot, valvonnan ja
katselmoinnin ennen julkistusta.

Suunnitelman valinnat ovat **päätökset P4-01–P4-16** tiedostossa
[decisions.md](decisions.md#phase-4-decisions) (englanniksi). Ne on ehdotettu
issuessa [#67](https://github.com/Haiko-Innovations/orbit-watch/issues/67), ja ne odottavat hyväksyntää. Lyhyesti:
- **Vercel ja Neon** Haiko Innovationsin nykyisillä tasoilla,
  **haikoinnovations.comin aliverkkotunnuksessa**;
- **PostgreSQL kaikkialla, missä palvelu tallentaa tilaa**, SQLiten (P-02)
  tilalle;
- **tilaton palvelu**, joka toimii itse: seuranta 15 minuutin välein ja oma
  RPC-päätepiste;
- **siirrettävä rakenne**: sama julkaisu toimii myös konttina minkä tahansa
  PostgreSQLin kanssa;
- **rajat** ilman kolmannen osapuolen CAPTCHAa sekä **tietosuojaseloste ja
  käyttöehdot**;
- **tietokanta suojattuna** rooleilla ja salaisuuksilla, ja salaisuuksista
  **vain tarkistusavain** palvelulla;
- julkaisut otetaan käyttöön siirtämällä **production-haaraa**,
  **päivittäiset salatut varmuuskopiot** ja **valvonta**;
- **ei mitään, mikä sulkisi tien yhteisön ylläpitämään verkkoon**
  ([decentralisation.md](decentralisation.md), englanniksi).

| Askel | Sisältö | Valmis, kun |
|---|---|---|
| **4.1 PostgreSQL** ([#68](https://github.com/Haiko-Innovations/orbit-watch/issues/68)) | Palvelun tallennus PostgreSQLiin tiedostoineen SQLiten tilalle; paikallinen ympäristö käynnistää PostgreSQLin kontissa; kantaa tarvitsevat testit ajetaan CI:ssä aina ja paikallisesti, kun PostgreSQL on saatavilla. | Jokainen testi menee läpi PostgreSQLillä CI:ssä; paikallinen ympäristö käynnistyy yhdellä komennolla; avoimen ytimen komentorivi ei tarvitse kantaa. |
| **4.2 Tilaton palvelu, joka toimii itse** ([#69](https://github.com/Haiko-Innovations/orbit-watch/issues/69)) | Ei tilaa kannan ulkopuolella: transaktio jokaiselle kutsulle ja advisory lock muutoksille; seuranta todennettuna kutsuna (ajastus, ajastin tai `serve --follow`), joka soveltaa tapahtumat, attestoi, tilittää ja soveltaa määräajat vahvistussyvyyteen asti; terveystarkistus; konttikuva rakennetaan ja testataan CI:ssä. | Kaksi instanssia ei koskaan tee samaa muutosta kahdesti; tilaus tilitetään ja toinen vanhenee ilman `tick`iä; kuva läpäisee päästä päähän -testit; testattu. |
| **4.3 Rajat ja oma RPC-päätepiste** ([#70](https://github.com/Haiko-Innovations/orbit-watch/issues/70)) | Rajat IP-osoitetta ja osapuolta kohden kannassa, Vercelin palomuuri edessä; pyynnöt enintään 4 Mt; ketju luetaan omasta RPC-päätepisteestä, jonka avain on salaisuus. | Jokaisen julkisen ja kirjautumisen päätepisteen rajat testattu; RPC-avain ei koskaan vastauksessa, lokissa tai selaimessa, testattu. |
| **4.4 Tietosuojaseloste ja käyttöehdot** ([#71](https://github.com/Haiko-Innovations/orbit-watch/issues/71)) | Molemmat englanniksi ja suomeksi, linkki jokaiselta sivulta; aseman koordinaatit noin kilometrin tarkkuudella; asemaprofiilin poisto ja istuntojen lopetus; lokien säilytys; istuntoevästeen asema lain mukaan lähteineen. | Sivut toimivat kirjautumatta; poisto ja koordinaattien tarkkuus testattu; tietoluettelo dokumentoitu. |
| **4.5 Vercel ja Neon** ([#72](https://github.com/Haiko-Innovations/orbit-watch/issues/72)) | Vercel-projekti ja Neon-kanta Haiko Innovationsin tileillä, aliverkkotunnus, kannan kaksi roolia, salaisuudet vain tuotannossa, esikatselut ilman niitä, production-haara. | Palvelu vastaa HTTPS:llä, vielä julkistamatta; käyttöönotto ja paluu edelliseen tehty production-haaraa siirtämällä. |
| **4.6 Varmuuskopiot, valvonta ja ohjeet** ([#73](https://github.com/Haiko-Innovations/orbit-watch/issues/73)) | Päivittäinen salattu `pg_dump` GitHub Actionsilla, säilytys 14 päivää; saatavuusvalvonta hälytyksineen; Neonin tuntien seuranta; vain luku -tila; toimintaohjeet. | Palautusharjoitus läpäisty; hälytys tavoitti ylläpitäjän; ohjeet dokumentoitu. |
| **4.7 Avaimet ja katselmointi ennen julkistusta** ([#74](https://github.com/Haiko-Innovations/orbit-watch/issues/74)) | Tarkistusavain tuotannon salaisuudeksi ja pois ylläpitäjän koneelta; Safen allekirjoittajat päätöksen mukaan; tietoturvatarkistuslista, ihmisen tekemä ruudunlukijatesti, oikea lompakkolaajennus. | Katselmointi tehty; jokainen löydös korjattu tai kirjattu. |
| **4.8 Julkistus ja vaiheen 4 yhteenveto** ([#75](https://github.com/Haiko-Innovations/orbit-watch/issues/75)) | Palvelu avataan, ylläpitäjälle lyhyt julkistusteksti; vaiheen 4 yhteenveto. | Alla olevat vaiheen 4 valmiskriteerit täyttyvät; julkaistaan 0.5.0. |

**Vaiheen 4 valmiskriteerit** ([P4-16](decisions.md#p4-16-phase-4-completion-criteria),
ehdotus):

1. Palvelu ja verkkosovellus toimivat julkisesti osoitteessaan HTTPS:llä,
   vain Base Sepoliassa, ja jokaisella sivulla on testiverkkomerkintä ja
   SIMULOITU-merkintä.
2. Tilaukset attestoidaan, tilitetään ja vanhenevat ajallaan ilman, että
   kukaan kutsuu `tick`iä. Palvelulla ei ole tilaa PostgreSQLin ulkopuolella,
   eikä kaksi instanssia koskaan tee samaa muutosta kahdesti, testattu.
3. PostgreSQL on palvelun ainoa tietokanta tuotannossa, paikallisessa
   ympäristössä ja CI:ssä, ja paikallinen ympäristö käynnistyy yhä yhdellä
   komennolla.
4. Sama julkaisu toimii myös konttina minkä tahansa PostgreSQLin kanssa
   dokumentoiduilla komennoilla, ja CI testaa kuvan päästä päähän.
5. Jokaisella julkisella ja kirjautumisen päätepisteellä on dokumentoidut
   rajat, testattu.
6. Tietosuojaseloste ja käyttöehdot ovat linkitettyinä jokaiselta sivulta,
   ja henkilötiedot, niiden säilytys ja poisto on dokumentoitu ja toteutettu.
7. Vain tuotantoympäristöllä on tarkistusavain ja kannan salasana.
   Salaisuuksia ei ole repossa, esikatselussa, kuvassa eikä selaimessa,
   testattu. Ohjeet vuotaneelle avaimelle ja salasanalle on kirjoitettu.
8. Julkaisu otetaan käyttöön siirtämällä production-haaraa, ja paluu
   edelliseen on tehty.
9. Salatut varmuuskopiot tehdään joka päivä Vercelin ja Neonin ulkopuolelle,
   palautusharjoitus on läpäisty, ja valvonta on hälyttänyt ylläpitäjälle
   kerran.
10. Katselmointi ennen julkistusta on tehty ja jokainen löydös korjattu tai
    kirjattu; jokainen CI-tarkistus menee yhä läpi, myös jokaisen roolin
    päästä päähän -testi; julkaistaan 0.5.0.

### Myöhemmin: yhteisön ylläpitämä verkko

Pitkällä aikavälillä Orbit Watchin ei pitäisi riippua yhdestä ihmisestä,
koneesta tai yrityksestä, ja yhteisön pitäisi päättää, miten sen verkkoa
ajetaan: julkinen ehdotusprosessi, Safen allekirjoittajat yhteisöstä,
tilattomat solmut, joita kuka tahansa voi ajaa, ja tarkistussolmut, jotka
sopivat tuloksesta k/n-periaatteella yhden avaimen sijaan. Tämä on suunta,
ei suunnitelma: katso [decentralisation.md](decentralisation.md)
(englanniksi).

## Miten työskentelemme

- Yksi pull request kerrallaan `main`-haarasta, ja ylläpitäjä yhdistää sen
  squash-mergellä, kun `tarkistus` on mennyt läpi. Ei pinottuja pull
  requesteja: squash-mergen kanssa ne menevät konfliktiin
  ([D-10](decisions.md#d-10-one-pull-request-at-a-time-on-main)).
- Jokainen käyttäjälle näkyvä muutos lisää rivin [muutoslokin](../CHANGELOG.md)
  `Unreleased`-osioon.
- Julkaisut tehdään ohjeen [releasing.md](releasing.md) mukaan: yksi
  minor-versio vaihetta kohden niin kauan kuin versio on 0.x, patch-versiot korjauksille.
