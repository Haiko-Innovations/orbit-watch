# Tietosuojaseloste

Orbit Watchin julkinen testiverkkopalvelu · versio 16.11.2026

Tässä selosteessa kerrotaan, mitä henkilötietoja Orbit Watch -palvelu säilyttää, miksi ja kuinka kauan sekä kuka muu niitä käsittelee. Seloste koskee julkista testiverkkopalvelua ja sen verkkosovellusta. Orbit Watch on avointa lähdekoodia: kaikki tämän tekevä koodi on julkista, ja [tietovarannon kuvaus](https://github.com/Haiko-Innovations/orbit-watch/blob/main/docs/personal-data.md) luettelee jokaisen taulun ja lokin tarkemmin (englanniksi).

## Rekisterinpitäjä

Rekisterinpitäjä on **Haiko Innovations Oy**. Kaikissa tietojasi koskevissa asioissa lähetä sähköpostia osoitteeseen [info@haikoinnovations.com](mailto:info@haikoinnovations.com?subject=Orbit%20Watch%20privacy), ja kirjoita aiheeksi "Orbit Watch privacy".

## Mitä palvelu säilyttää

Palvelu säilyttää niin vähän kuin pystyy. Siinä ei ole analytiikkaa, seurantaa, mainontaa eikä muilta sivustoilta ladattavaa sisältöä.

- **Tilisi.** Rekisteröityessä valitsemasi nimi, esimerkiksi `station:SIM-HELSINKI`, joka on julkinen, ja lompakkosi osoite, joka on joka tapauksessa julkinen lohkoketjussa. Palvelu säilyttää myös viestin, jonka allekirjoitit rekisteröityessäsi, ja sen allekirjoituksen. Ne osoittavat, että lompakko on sinun.
- **Kirjautuminen.** Viesti, jonka lompakkosi allekirjoittaa kirjautuessasi: osoitteesi, tämän sivuston osoite ja viestin ajat. Palvelu säilyttää sen tunnin sen vanhenemisen jälkeen. Istuntosi: tilisi, osoitteesi, tämän sivuston osoite sekä istunnon alkamis- ja päättymisaika. Istunto poistetaan, kun kirjaudut ulos tai kun se päättyy viimeistään 12 tunnin kuluttua.
- **Asemasi profiili, jos sinulla on asema.** Aseman nimi, sijainti, korkeus ja sen käyttämä SIMULOITU havaintolaite. Sijainti säilytetään kahden desimaalin tarkkuudella asteina, eli noin kilometrin tarkkuudella, koska asema voi olla jonkun koti. Profiilin näkevät vain sinä ja ylläpitäjät, ja voit poistaa sen sivulla "Your station".
- **Mitä teet palvelussa.** Tilauksesi ja niiden otsikot, toimittamasi havaintotiedostot, tarkistusraportit ja perustelut, jotka annat haastaessasi tuloksen tai arvioidessasi toimituksen. Havaintotiedostossa on asemasi sijainti samalla kahden desimaalin tarkkuudella; palvelu hylkää tätä tarkemmat tiedostot. Näitä tietoja näkevät tilauksen osapuolet ja ylläpitäjät. Kun tilaus on tilitetty ja sen enintään 30 päivän embargo on päättynyt, sen tilaus, havainnot ja raportti julkaistaan kaikille CC BY 4.0 -lisenssillä.
- **Transaktiosi.** Palvelulle ilmoittamiesi transaktioiden tiivisteet ja tila. Itse transaktiot ovat lohkoketjussa.
- **Vastausten kopiot.** Kun muutat jotain, palvelu säilyttää vastauksensa kopion 24 tuntia, jotta muutos ei tapahdu kahdesti, jos selaimesi kysyy uudelleen.
- **IP-osoitteet.** Palvelu ei tallenna IP-osoitettasi. Jotta kukaan ei kuormittaisi palvelua liikaa, se laskee kutsuja osoitteittain ja säilyttää sitä varten vain osoitteen avaimella lasketun tiivisteen. Jokainen laskuri poistetaan aikaikkunansa päättyessä, viimeistään tunnin kuluttua. Palvelu ei kirjoita IP-osoitteita omiin lokeihinsa. Palveluntarjoajamme käsittelee IP-osoitettasi toimittaakseen sivut ja suojatakseen palvelua hyökkäyksiltä, ja sen lokeja säilytetään enintään 30 päivää.
- **Sähköposti.** Jos kirjoitat meille, säilytämme viestiäsi niin kauan kuin sen käsittely vaatii.

Muuta palvelu ei sinusta kerää. Tiliin tarvitset lompakon ja nimen; kaikki muu on sinun päätettävissäsi. Älä kirjoita henkilötietoja otsikoihin, nimiin tai perusteluihin: ne näytetään muille ja ne voidaan julkaista.

## Lohkoketjussa

Palvelu toimii Base Sepoliassa, joka on julkinen testilohkoketju. Mitä teet siellä lompakollasi, on julkista ja pysyvää: lompakkosi osoite, allekirjoittamasi transaktiot sekä attestaatiot ja äänet, jotka nimeävät tilauksesi, tiedostosi ja perustelusi niiden SHA-256-tiivisteillä. **Kukaan, emme mekään, ei voi poistaa tai muuttaa lohkoketjussa olevaa tietoa.** Mieti tätä ennen kuin käytät lompakko-osoitetta, joka liittyy sinuun muualla: voit tehdä uuden lompakon pelkästään kokeilua varten.

## Miksi ja millä perusteella

- Tarjotaksemme palvelua, jota käytät [käyttöehtojen](#/terms/fi) mukaisesti: tilisi, kirjautuminen, asemasi profiili, tilauksesi, toimituksesi ja arviosi sekä tilitettyjen tietojen julkaiseminen ehtojen mukaisesti. Oikeusperuste on sopimus eli käyttöehdot (tietosuoja-asetuksen 6 artiklan 1 kohdan b alakohta).
- Pitääksemme palvelun turvallisena ja käytettävissä: IP-osoitekohtaiset rajat ja palveluntarjoajan lokit. Oikeusperuste on oikeutettu etumme ylläpitää turvallista palvelua (6 artiklan 1 kohdan f alakohta).
- Säilyttääksemme jokaisesta tilauksesta todennettavan tallenteen, jotta kuka tahansa voi tarkistaa, mitä toimitettiin ja mitä päätettiin. Oikeusperuste on oikeutettu etumme avoimeen ja todennettavaan verkkoon (6 artiklan 1 kohdan f alakohta).

Jokainen toimitus tarkistetaan ensin automaattisesti, ja tarkistus ratkaisee, hyväksytäänkö se. Tarkistuksella ei ole sinuun oikeudellisia tai niihin verrattavia vaikutuksia, koska testiverkon tokeneilla ei ole arvoa, ja kuka tahansa osapuoli voi haastaa tuloksen, jolloin toimituksen arvioivat tarkistajat.

## Evästeet

Palvelu asettaa yhden evästeen, `ow_session`, ja vain kun kirjaudut sisään. Se pitää sinut kirjautuneena enintään 12 tuntia. Skriptit eivät voi lukea sitä, ja se lähetetään vain tälle sivustolle. Eväste on välttämätön kirjautumiselle, jota itse pyydät, joten sähköisen viestinnän palveluista annetun lain (917/2014) 205 §:n mukaan se ei vaadi suostumusta. Palvelu ei tallenna selaimeesi mitään muuta. Lompakkolaajennuksesi on omaa ohjelmistoasi ja säilyttää omat tietonsa.

## Kuka muu käsittelee tietojasi

- **Vercel Inc.**, yhdysvaltalainen yhtiö, ylläpitää palvelua ja verkkosovellusta puolestamme. Palvelu toimii Frankfurtissa, ja Vercelin verkko toimittaa sivut sinua lähimmästä toimipisteestään. Se käsittelee IP-osoitettasi ja pyyntöjäsi.
- **Neon**, joka on osa Databricks, Inc. -yhtiötä, ylläpitää palvelun tietokantaa Frankfurtissa puolestamme.
- **GitHub, Inc.** säilyttää tietokannan päivittäiset varmuuskopiot. Ne salataan ennen lähettämistä, joten GitHub ei voi lukea niitä.
- **Lohkoketju.** Base Sepolia ja sen attestaatiopalvelu ovat julkisia: kuka tahansa voi lukea, mitä niissä on. Palvelu lukee lohkoketjua lohkoketjupalvelun tarjoajan kautta, eikä lähetä sille sinusta mitään, mikä ei jo ole julkista ketjussa.

Vercel ja Databricks ovat sitoutuneet EU:n ja Yhdysvaltojen väliseen tietosuojakehykseen (Data Privacy Framework), ja Vercelin ja Databricksin tietojenkäsittelyehdot sisältävät Euroopan komission vakiosopimuslausekkeet. Emme myy tietojasi emmekä luovuta niitä kenellekään muulle.

## Kuinka kauan

- Kirjautumisviestit: tunnin niiden vanhenemisen jälkeen.
- Istunnot: kunnes kirjaudut ulos, enintään 12 tuntia.
- IP-osoitekohtaiset laskurit: aikaikkunansa loppuun, enintään tunnin.
- Vastausten kopiot: 24 tuntia.
- Palveluntarjoajan lokit: enintään 30 päivää.
- Asemasi profiili: kunnes poistat sen.
- Tilisi, tilauksesi, toimituksesi, raporttisi ja perustelusi: niin kauan kuin testiverkkopalvelu toimii, koska ne ovat verkon tallenne. Kun palvelu suljetaan, sen tietokanta poistetaan.
- Varmuuskopiot: jokaista päivittäistä, salattua varmuuskopiota säilytetään 14 päivää, joten palvelusta poistettu tieto katoaa varmuuskopioista 14 päivän kuluttua.
- Julkaistut tiedot: julkaistu CC BY 4.0 -lisenssillä, joten muiden tekemät kopiot jäävät heille.

## Oikeutesi

Voit pyytää kopion tiedoistasi, pyytää niiden oikaisemista tai poistamista, rajoittaa niiden käsittelyä, vastustaa niiden käsittelyä oikeutetun etumme perusteella ja saada antamasi tiedot koneluettavassa muodossa. Lähetä sähköpostia osoitteeseen [info@haikoinnovations.com](mailto:info@haikoinnovations.com?subject=Orbit%20Watch%20privacy). Voimme pyytää sinua allekirjoittamaan viestin lompakollasi osoittaaksesi, että tili on sinun. Vastaamme kuukauden kuluessa.

Kaikkea ei voi poistaa: lohkoketjussa olevaa tietoa eikä muiden tekemiä kopioita julkaistuista tiedoista. Säilytämme tilauksen tallenteen siltä osin kuin sitä tarvitaan tilauksen tilittämiseen tai haasteeseen vastaamiseen.

Voit myös tehdä valituksen Suomen valvontaviranomaiselle eli tietosuojavaltuutetun toimistolle: [tietosuoja.fi](https://tietosuoja.fi).

## Muutokset

Kun seloste muuttuu, sen versiopäivä muuttuu, ja jokaisen muutoksen historia on julkinen [repositoriossa](https://github.com/Haiko-Innovations/orbit-watch/commits/main/docs/legal/privacy-notice.fi.md).
