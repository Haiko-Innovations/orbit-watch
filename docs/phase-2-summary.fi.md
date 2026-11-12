# Vaiheen 2 yhteenveto

[English](phase-2-summary.md) · **Suomi**

> Tämä on käännös. Jos englanninkielinen ja suomenkielinen versio eroavat, englanninkielinen versio pätee.

Vaihe 2 (rahallinen tilitys testiverkossa) on valmis versiona **0.3.0**. Tämä
on [suunnitelman](plan.fi.md) pyytämä vaiheen lopun yhteenveto.

> **Vain testiverkko, ei oikeaa arvoa.** Kaikki ketjussa tapahtuva toimii Base
> Sepoliassa Circlen testi-USDC:llä, jolla ei ole rahallista arvoa. Kaikki
> asemat, havainnot, tilaukset ja tarkistajat ovat SIMULOITUJA.

## Mikä toimii

- **Escrow-sopimus** Base Sepoliassa: yksi päivittämätön sopimus pitää
  jokaisen tilauksen talletuksen, lukitun jaon, ehtojen tiivisteen ja
  määräajat. Sillä ei ole omistajaa eikä ylläpitäjää. Raha lähtee vain
  tilityssääntöjen 1.0 mukaan: se hyvitetään, ja kukin osapuoli nostaa omansa.
- **Attestaatiot**: automaattisen tarkistuksen tulos ja jokainen tarkistajan
  ääni ovat EAS-attestaatioita kahdella skeemalla, joiden resolveri on
  escrow-sopimus. Sääntöjen vastaista attestaatiota ei siis voi syntyä.
  Kierroksen kolme tarkistajaa valitaan ketjussa kaavalla, johon kukaan ei voi
  vaikuttaa.
- **Hallinta**: tarkistajarekisteri kuuluu 48 tunnin julkiselle aikalukolle,
  jonka ainoa ehdottaja on Safe-monisignatuuri (2/3).
- **Palvelu ketjussa**: jokainen osapuoli allekirjoittaa omat transaktionsa
  omalla lompakollaan tai salatulla avainsäilöllään, komentoriviltä tai muulla
  lompakolla. Palvelulla on vain tarkistusavain, ja se seuraa escrow-sopimuksen
  tapahtumia, jotka ratkaisevat kierrokset ja maksut. Odottavat, vahvistetut
  ja epäonnistuneet transaktiot näytetään erikseen lohkoselainlinkkeineen.
- **Käyttöönotto** Base Sepoliaan dokumentoidulla ja testatulla skriptillä.
  Lähdekoodi on vahvistettu, ja mukana ovat faucet-ohjeet sekä tieto siitä,
  kuka hallitsee mitäkin avainta ([base-sepolia.md](base-sepolia.md)).
- **Vaiheen 2 demo**: vaiheen 1 demon viisi tilausta Base Sepoliassa, ja
  jokaisella osapuolella on oma lompakkonsa
  ([`examples/phase2/transcript.md`](../examples/phase2/transcript.md)).

### Valmiskriteerit

| Suunnitelman kriteeri | Tila |
|---|---|
| 1. Järjestelmä käynnistyy dokumentoiduilla ohjeilla | ✅ sopimukset vietiin ja palvelu ajettiin [base-sepolia.md](base-sepolia.md):n ohjeilla |
| 2. Eri osapuolet toimivat eri lompakoilla | ✅ demossa tilaaja, neljä asemaa, tarkistajat ja tarkistusavain, jokaisella oma avain |
| 3. Tilauksen voi luoda ja rahoittaa | ✅ rahoitus `approve`- ja `fund`-kutsuilla tilaajan lompakosta |
| 4. Havaitsija voi varata tilauksen ja toimittaa simuloidun aineiston komentoriviltä | ✅ `orbit-watch reserve` ja `orbit-watch submit` aseman avainsäilöllä allekirjoitettuina |
| 5. Automaattinen tarkistus, haastejakso ja haasteen kautta tarkistajakierros toimivat, ja tulokset näkyvät EAS-attestaatioina | ✅ tulokset ja äänet demon attestaatiotaulukossa, EAS Scanissa |
| 6. Hyväksytyn tilauksen palkkiot liikkuvat oikeina testiverkon token-siirtoina | ✅ havaitsijan ja tarkistajien palkkiot nostetaan USDC-siirtoina |
| 7. Hylkäys, määräajan umpeutuminen, riita ja palautus toimivat | ✅ kaikki demossa sekä skenaariosarjassa ketjussa |
| 8. Lohkoselainlinkit näytetään | ✅ jokainen transaktio rajapinnassa, komentorivillä ja transkriptissa |
| 9. Valtuuttamaton osapuoli ei voi hyväksyä työtä eikä nostaa talletusta, testattu | ✅ sopimustestit, palvelutestit rajapinnan kautta ja suoraan ketjussa sekä demon tarkistukset |
| 10. Uusintayritys ei koskaan maksa kahdesti, testattu | ✅ sopimustestit, palvelutestit ja demon tarkistukset |

Sopimukset on testattu Foundrylla: yksikkö-, skenaario-, fuzz- ja
invarianttitestit varmistavat, että jokainen talletus maksetaan tai
palautetaan (talletus = palkkiot + palautukset). Python-puoli testataan CI:ssä
paikallisessa Anvil-ketjussa, mukaan lukien käyttöönottoskripti ja tämä demo.

## Mikä on simuloitua ja mikä testiverkkoa

- Kaikki asemat, havainnot, tilaukset ja tarkistajat. Jokainen simuloitu
  dokumentti kertoo sen itse.
- Raha on Circlen arvotonta testi-USDC:tä Base Sepoliassa, faucetista.
- **Testiverkossa yksi ylläpitäjä hallitsee kaikkia avaimia**: Safen
  allekirjoittajia, tarkistusavainta ja simuloituja osapuolia. Siksi Safen 2/3
  erottaa avaimet mutta ei ihmisiä ([D-24](decisions.md#d-24-the-base-sepolia-deployment)).
- Palvelu toimii paikallisesti; vain sopimukset ja attestaatiot ovat julkisia.

## Näin sen voi ajaa

Ohjeet ovat englanninkielisessä versiossa ([How to run it](phase-2-summary.md#how-to-run-it)).
Demo tarvitsee Base Sepoliassa käynnissä olevan palvelun ja jokaisen osapuolen
avainsäilön, jossa on vähän testi-ETH:ta, sekä tilaajalle testi-USDC:tä. Ajo
kestää noin puoli tuntia, koska määräajat ovat minuutteja pitkiä. Saman demon
voi ajaa myös paikallisessa ketjussa (`core/tests/test_phase2_demo.py`).

## Avoimet ongelmat seuraavaan vaiheeseen

- **Avaimet eri ihmisille**: Safen kolme allekirjoittajaa ja tarkistusavain
  pois ylläpitäjän koneelta ennen kuin mitään käytetään testiverkon ulkopuolella.
- **Kalibrointi ketjussa**: tarkistaja erottaa kalibrointitehtävän oikeasta,
  koska vain oikea ääni on julkinen attestaatio (D-23).
- **Joku muu voi rahoittaa tilaustunnuksen ensin**. Palvelu näyttää sen
  ristiriitana, ja tilaaja tarvitsee uuden tunnuksen. Tilaajakohtainen avain
  korjaisi tämän uudessa escrow-versiossa.
- **Ei taustatyötä**: palvelu tilittää, kun osapuoli raportoi transaktion tai
  ylläpitäjä kutsuu `tick`-toimintoa. Ketjun uudelleenjärjestelyjä ei käsitellä.
- **Vakuudet** varauksille, haasteille ja tarkistajille sekä
  **henkilötiedot** (asemien koordinaatit julkisessa datassa), kuten vaiheen 1
  jälkeen.
- **Vaihe 3**: verkkosovellus, lompakot selaimessa ja palvelun julkinen
  käyttöönotto (TLS, käyttörajat, avainten kierrätys, ylläpito).
- **Oikea IOD-esimerkki** siviilikohteesta luvan kanssa
  ([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).
