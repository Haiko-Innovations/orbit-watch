# Orbit Watch – aloitussuunnitelma

[English](plan.md) · **Suomi**

> Ensisijainen kieli on englanti. Tämä on suomenkielinen käännös; ristiriidassa englanninkielinen versio pätee.

Haluan rakentaa avoimen lähdekoodin projektin, jonka työnimi on **Orbit Watch**: avoin protokolla ja referenssitoteutus satelliittihavaintojen tilaamiseen, toimittamiseen, riippumattomaan tarkistamiseen ja selvittämiseen.

Tee järkevät tekniset oletukset itsenäisesti ja kerro niistä. Tarkista ajantasaiset viralliset dokumentaatiot (kirjastot, testiverkot, sopimusosoitteet) ennen kuin käytät niitä. Älä kirjoita osoitteita tai versioita muistista.

## 1. Tavoite ja tausta

Projekti on puhtaasti open source. Tavoitteena on kerätä yhteisö, eli harrastajia, tähtitieteilijöitä ja kehittäjiä, eikä liiketoiminta. Repo julkaistaan Haiko Innovationsin GitHub-organisaatiossa, ja projektilla on oma selkeä identiteetti. Lisenssi on **Apache 2.0**, ja datan oletuslisenssi on **CC-BY 4.0**.

**Projektin sydän on tarkistus, ei maksaminen.** Ketju on:

Toimeksianto → (valinnainen rahoitus) → havaintotoimitus → automaattinen tarkistus → haasteaika → hyväksyntä tai hylkäys → (valinnainen) palkkiot tai palautus.

Olemassa olevat hankkeet kattavat ketjusta vain osia:
- SatNOGS: avoin radioverkko;
- IAU CPS SCORE: kirkkaushavainnot;
- SkyMapper: suljettu kaupallinen DePIN;
- TruSat: jäi prototyypiksi.

Avointa, toimittajaneutraalia protokollaa koko ketjulle ei ole. TruSatin opetus on se, että pelkän rekisterin ympärille ei synny yhteisöä. Osallistujan on saatava hyötyä heti.

**Ensimmäinen kohdekäyttäjä on kuutiosatelliittitiimi.** Laukaisun jälkeen kymmenet pikkusatelliitit irtoavat yhtä aikaa, ja tiimit eivät tiedä, mikä julkinen ratatieto on heidän. Tiimi julkaisee pyynnön ("tunnista ja seuraa kohde X ikkunassa Y"), harrastaja-asemat havaitsevat, ja tulos tarkistetaan. Muita asiakkuuksia (operaattorit, SSA-yritykset, viranomaiset) ei ole validoitu, eikä niitä tavoitella tässä vaiheessa.

Projekti ei ohjaa satelliitteja eikä tuota operatiivisia turvallisuussuosituksia.

## 2. Keskeiset rajaukset

- **Kohteet:** vain julkisen GP-luettelon (esim. CelesTrak) siviilikohteet. Järjestelmä torjuu toimeksiannon, jonka kohde ei ole sallittujen listalla. Lista on konfiguroitava, ja oletuksena siitä on rajattu pois sotilas- ja tiedustelukohteet sekä luokitellut kohteet.
- **Ydin toimii ilman lohkoketjua ja ilman rahaa.** Maksaminen on vaihdettava selvityssovitin (luku 6).
- **Ensimmäinen ketjusovitin toimii vain testiverkossa.** Mainnetiä ei käytetä. Maksuina on arvoton testitoken tai testiverkon USDC. Kumpi tahansa, mutta tokenin osoite on asetus eikä kovakoodattu.
- **Ei omaa sijoitus- tai hallintotokenia**, pörssilistausta, vaihtopoolia eikä hintamekanismia.
- **Havaintoaineisto ja simulaattori merkitään selvästi simulaatioiksi.** Tarkistusta ei esitetä tuotantovalmiina tieteellisenä validointina.
- **Kaikki toimii paikallisesti** ilman oikeaa teleskooppia ja ilman maksullisia palveluita.

## 3. Vaiheet

Jokainen vaihe on julkaistavissa ja katselmoitavissa erikseen. **Aloita vaiheesta 0, ja pysähdy sen valmistumiskriteereihin ennen vaihetta 1.**

### Vaihe 0: avoin ydin (Python)

Tämä on yhteisön ydin, eikä siinä ole kryptoa.

1. **Havaintoformaatti:**
   - oma kevyt JSON-skeema (versioitu, JSON Schema);
   - muuntimet harrastajien **IOD**-formaatista ja **CCSDS TDM** -formaatin rajatusta osajoukosta;
   - formaatin dokumentaatio ja esimerkkitiedostot.
2. **Havaintoaseman simulaattori:**
   - tuottaa paikkahavaintoja (aika, RA/Dec tai az/el, epävarmuus) julkisesta ratatiedosta SGP4:llä;
   - lisää konfiguroitavaa kohinaa, aikavirhettä ja puuttuvia havaintoja;
   - tuottaa testiaineistot: hyväksyttävä, virheellinen, myöhästynyt, kopioitu, väärä kohde ja liian epätarkka.
3. **Tarkistusmoottori (deterministinen, versioitu):**
   - pakolliset kentät ja formaatti;
   - kohteen ja tehtävän vastaavuus;
   - aikaikkuna ja havaintojen vähimmäismäärä;
   - ilmoitettu epävarmuus;
   - tiivisteen vastaavuus;
   - duplikaatin tai uudelleenlähetyksen tunnistus;
   - **ratajäännökset julkiseen vertailurataan nähden**: jäännöstilasto ja raja-arvot.
   - Raportti kertoo menetelmän nimen ja version, syötteiden tiivisteet sekä jokaisen tarkistuksen tuloksen perusteluineen. Kuka tahansa voi ajaa saman tarkistuksen ja saada saman tuloksen.
4. **Aseman laatumittari (osallistujan välitön hyöty):** harrastaja ajaa omat havaintonsa (IOD tai JSON) mittarin läpi. Mittari kertoo, kuinka tarkkoja havainnot ovat julkiseen rataan nähden, missä on systemaattista virhettä (esimerkiksi kellon siirtymä) ja miten tarkkuus kehittyy ajan myötä.
5. **CLI:** `simulate`, `validate`, `score-station`, `convert` ja `submit` (lähettää API:lle, kun API on olemassa).
6. **Testit ja CI:**
   - pytest;
   - kaikki testiaineistot tuottavat odotetun tuloksen;
   - determinismitesti: sama syöte antaa saman raportin tavu tavulta.

**Vaiheen 0 valmistumiskriteerit:**
- `pip install` ja yksi komento tuottavat simuloidun aineiston ja tarkistusraportin.
- Kaikki kuusi testiaineistoa saavat oikean tuloksen ja ymmärrettävän perustelun.
- Laatumittari toimii simuloidulla aineistolla ja yhdellä oikealla julkisella IOD-esimerkillä.
- README kertoo kolmessa minuutissa, mikä projekti on, miten kokeillaan ja miten voi osallistua. Mukana ovat myös CONTRIBUTING, koodin käytännöt, issue-pohjat ja "good first issue" -merkityt tehtävät, esimerkiksi uusi tarkistus, uusi formaatti tai uusi asemaprofiili.

### Vaihe 1: tehtävät, optimistinen tarkistus ja API (Python tai TypeScript, kevyt kanta)

1. **Tehtävän tilakone** (yksiselitteinen, testattu):
   luonnos → avoin → (rahoitettu) → varattu → toimitettu → automaattisesti tarkistettu → **haasteaika** → hyväksytty / hylätty / kiistetty → selvitetty.
   Lisäksi vanhentunut: varaus raukeaa, ei toimitusta tai tarkistus jumissa.
2. **Optimistinen tarkistus:**
   - automaattisen tarkistuksen tulos julkaistaan, ja sen jälkeen alkaa haasteaika (esimerkiksi 24 h, ehdoissa lukittu);
   - jos kukaan ei haasta, tulos on lopullinen;
   - haaste käynnistää tarkistajakierroksen: kolme ennalta hyväksyttyä tarkistajaa, kynnys 2/3, ja sama taho ei saa tarkistaa omaa toimitustaan (protossa avaintasolla hyväksyntälistan kautta);
   - tarkistajat saavat korvauksen valmiista tarkistuksesta lopputuloksesta riippumatta.
3. **Tarkistajien tarkkuuden mittaus:** järjestelmä syöttää sekaan testiaineistoja, joiden oikea tulos tiedetään. Tarkistajan tarkkuus näkyy hänen profiilissaan. Tällä torjutaan kuittaaminen katsomatta.
4. **Ristiriitasääntö:** jos 2/3-tulosta ei synny määräaikaan mennessä, tarkistajat saavat korvauksen valmiista tarkistuksista, havaitsija ei saa palkkiota ja loput palautetaan ostajalle. Ristiriita ei koskaan vapauta havaitsijan palkkiota automaattisesti eikä lukitse varoja ikuisesti.
5. **Varauksen väärinkäyttö:** varauksella on aikakatkaisu. Vakuus on myöhemmän vaiheen asia, ja se kirjataan avoimeksi kysymykseksi.
6. **API ja tallennus:**
   - tehtävät, varaukset, toimitukset (tiedosto ja tiiviste), raportit ja haasteet;
   - asemalla on oma API-avain, joka sallii vain toimittamisen, ei rahansiirtoja;
   - kaikki muuttavat kutsut ovat idempotentteja: sama toimitus, hyväksyntä tai selvityspyyntö ei koskaan tuota kahta vaikutusta.
7. **Selvityssovittimen rajapinta ja oletussovitin "ledger":** ei rahaa, vaan maine- ja pistekirjanpito, joka noudattaa täsmälleen samoja sääntöjä kuin rahallinen selvitys. Näin koko ketju toimii ja on testattavissa ilman lohkoketjua.
8. **Data:** toimitukset ja raportit julkaistaan oletuksena CC-BY-lisenssillä. Ostaja voi valita ehtoihin lyhyen embargon (esimerkiksi enintään 30 päivää). Tiedostot säilytetään ja niille tarjotaan pysyvä latausosoite. Tiiviste ei korvaa säilytystä.

**Vaiheen 1 valmistumiskriteerit:**
- Koko ketju toimii ledger-sovittimella CLI:stä ja API:sta: tehtävä, varaus, simuloitu toimitus, automaattinen tarkistus, haasteaika ja lopputulos.
- Hylkäys, varauksen vanheneminen, haaste ja tarkistajakierros, ristiriita sekä testiaineistojen tarkkuusmittaus on testattu.
- Kaksoistoimitus ja kaksoisselvitys eivät tuota kahta vaikutusta, ja tämä on testattu.

### Vaihe 2: rahallinen selvitys testiverkossa (EVM-L2 + EAS)

**Ketjuvalinta: EVM-yhteensopiva L2-testiverkko**, ensisijaisesti Base Sepolia tai Optimism Sepolia. Valitse se, jossa EAS ja testi-USDC ovat ajantasaisen dokumentaation mukaan saatavilla.

**Perustelut:**
- **Tarkistajien hyväksynnät** tallennetaan **Ethereum Attestation Servicen (EAS)** standardimuotoisina hyväksyntöinä. Niitä voi lukea ja käyttää kuka tahansa ilman Orbit Watchin koodia.
- **Escrow-, monisignatuuri- ja aikalukkologiikka** rakennetaan **OpenZeppelinin** auditoiduista osista. Omaa rahakoodia on mahdollisimman vähän.
- **Solidityn ja TypeScriptin kehittäjäpooli on laajin**, mikä painaa yhteisöprojektissa.
- **Kulut ovat sentin murto-osia tai senttejä**, ja USDC on saatavilla natiivisti.

Solana-sovitin on myöhemmin mahdollinen, koska selvitys on rajapinnan takana.

1. **Escrow-sopimus:**
   - tehtävän tunniste ja ehtojen tiiviste;
   - osapuolten osoitteet;
   - talletus ostajan etukäteen rahoittamasta budjetista;
   - palkkiojako, joka lukitaan rahoitushetkellä: havaitsija, tarkistajat, haastekierroksen varaus ja alustan maksu (oletus 0 open source -projektissa, mutta mekanismi on olemassa);
   - määräajat ja palautussäännöt.
2. **Hyväksyntä ja selvitys:**
   - automaattisen tarkistuksen tulos ja tarkistajien äänet tallennetaan EAS-hyväksyntöinä;
   - sopimus vapauttaa varat haasteajan jälkeen tai 2/3-hyväksynnöistä vain sääntöjen mukaan;
   - selvitys on idempotentti, eikä samaa tehtävää voi selvittää kahdesti.
3. **Ei piilotettuja oikeuksia:**
   - sopimuksia **ei tehdä päivitettäviksi** (ei proxy-mallia). Uusi versio on uusi sopimus, ja vanhat tehtävät selvitetään vanhassa;
   - ylläpidolla ei ole nosto-oikeutta asiakkaiden talletuksiin;
   - tarkistajalistan hallinta tapahtuu monisignatuurilla ja julkisella aikalukolla, ja nämä oikeudet dokumentoidaan READMEen.
4. **Lompakot ja avaimet:**
   - jokaisella osapuolella on oma osoite;
   - käyttäjät allekirjoittavat omilla lompakoillaan;
   - seed phraseja tai yksityisiä avaimia ei koskaan pyydetä eikä tallenneta lähdekoodiin;
   - testiautomaation avaimet pidetään erillään;
   - palvelimen salaisuudet eivät päädy selaimeen;
   - testiverkkomerkintä näkyy kaikkialla;
   - testivarojen saamiselle on turvallinen ohje: testiverkon hana ja testitokenin jakelu.
5. **Tapahtumat:** odottava, vahvistettu ja epäonnistunut näytetään erikseen. Maksujen tilan ensisijainen lähde on ketju, ei tietokanta. Jokaisesta tapahtumasta on explorer-linkki.
6. **Testit:**
   - sopimustestit (Foundry tai Hardhat) rahavirroille, oikeuksille, tilasiirtymille, aikakatkaisuille ja uudelleenyrityksille;
   - fuzz-testi sille, ettei varoja synny tai katoa: talletus = palkkiot + palautukset.

**Vaiheen 2 valmistumiskriteerit:**
1. Kokonaisuus käynnistyy dokumentoiduilla ohjeilla.
2. Eri osapuolet toimivat eri lompakoilla.
3. Toimeksiannon voi luoda ja rahoittaa.
4. Havaitsija voi varata tehtävän ja toimittaa simuloidun aineiston CLI:llä.
5. Automaattinen tarkistus, haasteaika ja haasteen kautta tarkistajakierros toimivat, ja tulokset näkyvät EAS-hyväksyntöinä.
6. Hyväksytyn tehtävän palkkiot siirtyvät oikeina testiverkon tokensiirtoina.
7. Hylkäys, määräajan umpeutuminen, ristiriita ja palautus toimivat.
8. Explorer-linkit näkyvät.
9. Luvaton toimija ei voi hyväksyä työtä eikä nostaa talletusta, ja tämä on testattu.
10. Uudelleenyritys ei maksa kahdesti, ja tämä on testattu.

### Vaihe 3: verkkosovellus (myöhemmin)

Yksi verkkosovellus erillisillä roolinäkymillä:

- **Ostaja:** yhdistää lompakon, näkee saldonsa, luo toimeksiannon (kohde, aikaväli, määräaika, toimitusvaatimukset), näkee palkkioiden ja kulujen jaon ennen rahoitusta, rahoittaa tehtävän, seuraa toimitusta ja tarkistusta, lataa aineiston ja raportin ja näkee maksutapahtumat ja palautukset.
- **Havaitsija:** yhdistää lompakon, rekisteröi (simuloidun) aseman, selaa avoimia toimeksiantoja, varaa tehtävän, lähettää aineiston, näkee hyväksynnän tai hylkäyksen perustelut ja seuraa palkkioitaan.
- **Tarkistaja:** yhdistää lompakon, näkee hänelle osoitetut haasteet, ajaa tarkistukset, tarkastelee raporttia, allekirjoittaa hyväksynnän tai hylkäyksen perusteluineen ja näkee palkkionsa ja tarkkuutensa.
- **Ylläpito:** hallitsee tarkistajia (monisignatuuri ja aikalukko), näkee tehtävien, toimitusten ja maksujen tilan, virheet ja tapahtumalokin sekä käynnistää simulaattoreita ja demoaineistoja.

Lisäksi aseman laatumittarin näkymä ja julkinen hyväksyntöjen selain. Ylläpidolla ei ole piilotettuja oikeuksia. Testiverkkomerkintä näkyy kaikkialla.

## 4. Mitä ketjuun ja mitä sen ulkopuolelle

**Ketjuun (vaihe 2):**
- tehtävän tunniste ja ehtojen tiiviste;
- osapuolten osoitteet;
- talletus;
- toimituksen tiiviste;
- automaattisen tarkistuksen ja tarkistajien hyväksynnät (EAS);
- lopullinen jako ja palautukset.

**Ketjun ulkopuolelle:**
- havaintotiedostot ja niiden säilytys;
- raportit;
- tarkistuslaskenta;
- haku ja tehtävien välitys;
- käyttöliittymä.

Sopimus tarkistaa valtuutetut allekirjoitukset ja maksusäännöt. Se ei näe avaruutta eikä todista mittausten fyysistä oikeellisuutta.

## 5. Tekninen kokonaisuus

- **Yksi repository**, monorepo:
  - `core/`: Python (formaatti, simulaattori, tarkistus, laatumittari, CLI);
  - `api/`;
  - `contracts/`: Solidity, Foundry suositeltu;
  - `web/`: vaihe 3.
- **Kielet:** Python ytimessä, koska tähtitieteen yhteisö käyttää sitä (skyfield, sgp4, astropy). TypeScript ja Solidity ketjussa ja webissä.
- **Kevyt tietokanta**, esimerkiksi SQLite kehityksessä, ja tiedostotallennus paikallisesti tai S3-yhteensopivasti.
- **CI** ajaa ytimen, API:n ja sopimusten testit. Lisäksi gitleaks, Dependabot ja SHA-kiinnitetyt actionit (Haiko Innovationsin repokäytäntö).

## 6. Selvityssovittimen rajapinta

Yksi rajapinta, jonka kautta tilakone tekee rahalliset tai pisteperusteiset vaikutukset: `fund`, `reserve`, `attest`, `settle` ja `refund`. Toteutukset:
1. `ledger` (oletus, vaihe 1): ei rahaa, maine ja pisteet, samat säännöt;
2. `evm-testnet` (vaihe 2): escrow-sopimus ja EAS;
3. myöhemmin mahdollinen `solana-devnet` tai muu.

Sääntöjen (jako, aikakatkaisut, ristiriitasääntö) on oltava samat kaikissa sovittimissa. Testaa sama skenaariojoukko kaikkia sovittimia vasten.

## 7. Avoimet kysymykset, kirjataan READMEen

- Nimi: "Orbit Watch" on työnimi. Tavaramerkin ja domainin tarkistus on tekemättä (lähellä ovat "Orbital Watch" ja DARPA OrbitOutlook).
- Varauksen vakuus ja tarkistajien vakuus, eli kannustimet kuittaamista ja yhteistyöhuijausta vastaan.
- Täysi riidanratkaisu.
- Yhteistyö: IAU CPS (SatChecker ja SCORE), Unistellar ja SETI, SatNOGS ja SeeSat-L:n harrastajat.
- Sääntely, jos oikea raha joskus tulee (MiCA, maksupalvelut). Rakenne, jossa sopimus ei säilytä varoja kenenkään puolesta, pidetään voimassa.

## 8. Lopuksi toimitettava

Lyhyt kuvaus jokaisen vaiheen päätteeksi:
- mikä toimii oikeasti (ja missä verkossa);
- mikä on simuloitu;
- miten demo ajetaan;
- mitkä ovat seuraavat ratkaistavat asiat.

**Aloita vaiheesta 0, ja älä jää pelkkään suunnitelmaan.** Pysähdy vaiheen 0 valmistumiskriteereihin ja raportoi ennen vaihetta 1.
