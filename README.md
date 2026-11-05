# MarketLens

MarketLens – internetinė akcijų, ETF ir kriptovaliutų stebėjimo sistema. Ji pateikia kainų istoriją, techninius rodiklius ir pagal juos sudarytą rinkos krypties vertinimą.

## Funkcijos

- Akcijų, ETF ir kriptovaliutų instrumentų sąrašas.
- Paieška pagal pavadinimą ar simbolį, turto tipo ir mėgstamų instrumentų filtrai.
- Naršyklėje išsaugomas mėgstamų instrumentų sąrašas.
- Tiesioginiai Binance ir Hyperliquid kainų srautai bei Yahoo kainų patikra kas 45 sekundes.
- Paskutinė išsaugota kaina rodoma, kol gaunami nauji duomenys; ryšio sutrikimai pažymimi kortelėje.
- Kainos pokyčio paryškinimas spalva ir vietiniu laiku rodomas kainos gavimo laikas.
- Žvakiniai kainos grafikai ir RSI grafikai su 1h, 4h ir 1d intervalais.
- Gyvas Binance ir Hyperliquid OHLC žvakių, SMA ir RSI grafikų atnaujinimas.
- Automatinė atidaryto puslapio duomenų patikra kas minutę, išsaugant pasirinktą intervalą.
- Laiko rodymas pagal vartotojo naršyklės laiko juostą.
- SMA 20 ir SMA 50 slankieji vidurkiai.
- RSI 14 rodiklis ir jo būsenos vertinimas.
- Kainos krypties, atskirų intervalų ir bendras techninis signalas.
- Išskleidžiami signalų paaiškinimai su kiekvieno indikatoriaus balais bei intervalų svoriais.
- Akcijų P/E, forward P/E, ketvirčio pajamų ir pelno augimas su šaltiniu bei laikotarpiu.
- Duomenų patikros laikas ir vėluojančio atnaujinimo žymėjimas.
- Trijų skaitmenų po kablelio tikslumas užuominose, rodomose užvedus ant žvakės.
- Sujungti kainos ir RSI grafikai su viena matoma laiko ašimi.
- Sinchronizuotas grafikų priartinimas, atitolinimas, slinkimas ir pradinio vaizdo atkūrimas.
- Tamsi ir šviesi tema su naršyklėje išsaugomu pasirinkimu.
- Instrumentų valdymas per Django administravimo sąsają.
- Asmeninių instrumentų pridėjimas bei pašalinimas svetainėje be registracijos.

## Duomenų šaltiniai

| Šaltinis | Duomenys |
| --- | --- |
| Binance | Kriptovaliutų kainos ir žvakės |
| Hyperliquid | Kriptovaliutų kainos ir žvakės |
| Yahoo Finance | Akcijų ir ETF kainos bei kainų istorija |

Yahoo Finance 4h žvakės sudaromos iš valandinių žvakių, atskiriant prekybos sesijas. Paskutinė sesijos žvakė gali apimti trumpesnį laikotarpį. Pradinė išsaugota akcijų ir ETF kaina gaunama iš valandinės žvakės. Atidarytame puslapyje atskirai tikrinama naujausia Yahoo `regularMarketPrice` reikšmė su jos `regularMarketTime` laiku. Dažnesnė patikra negarantuoja realaus laiko biržos duomenų; ne prekybos metu kainos laikas gali likti ankstesnės sesijos.

## Veikimo principas

Periodinė užduotis paleidžia Django komandą `update_market_data`. Komanda gauna rinkos duomenis iš išorinių šaltinių ir išsaugo juos duomenų bazėje.

```text
Periodinė užduotis → rinkos API → duomenų bazė
Naršyklė → Django → duomenų bazė → rodiklių skaičiavimas → puslapis
Binance / Hyperliquid WebSocket → naršyklės kainų laukeliai
Naršyklė → Django /prices/ → Yahoo API ir trumpas kešas → kainų laukeliai
```

Puslapis kiekvienam instrumentui perskaito po 100 naujausių kiekvieno intervalo žvakių. Tas pats sąrašas naudojamas grafikui, kainos krypčiai, SMA ir RSI apskaičiuoti. Pradinio puslapio ir grafikų atnaujinimo užklausos apdorojamos naudojant DB duomenis.

Instrumento, intervalo ir žvakės pradžios laiko derinys yra unikalus. Pakartotinis atnaujinimas pataiso esamas žvakes ir įrašo naujas. Ankstesnė istorija išlieka. Nepavykus gauti naujų duomenų, rodomi paskutiniai išsaugoti įrašai.

Binance ir Hyperliquid taip pat siunčia 1h, 4h bei 1d žvakes tiesiai naršyklei. Grafikas sujungia jas su DB istorija pagal žvakės pradžios laiką, palikdamas naujausius 100 taškų. Open, high ir low paimami iš biržos OHLC srauto. Keičiantis žvakei perskaičiuojami grafiko SMA ir Wilder RSI, o pasirinktas priartinimas išlieka. Naršyklės gyvos žvakės į DB nerašomos; istorijos saugojimą tęsia periodinė serverio komanda. Srautui nutrūkus atkuriamos prenumeratos, o turima istorija lieka ekrane.

Grafikų X ašyje pateikiamas žvakės pradžios laikas vartotojo naršyklės laiko juostoje. Taip pat vietiniu laiku rodomi duomenų patikros laikai. Laiko juosta nustatoma automatiškai, naudojant naršyklės Intl API. Duomenų patikros laikas saugomas atskirai. Praėjus daugiau nei 30 minučių nuo paskutinio sėkmingo pilno atnaujinimo, puslapyje parodoma vėlavimo žyma.

Atidarytas puslapis kas minutę gauna atnaujintas instrumentų korteles per Django maršrutą `/data/`. Kainų grafikai, RSI ir signalai atnaujinami neperkraunant viso puslapio. Pasirinktas instrumento intervalas ir priartinta grafikų sritis išsaugomi pagal instrumento ID. Nepavykus užklausai, lieka ankstesni grafikai ir kitą minutę bandoma dar kartą. Kol naršyklės kortelė paslėpta, periodinės užklausos sustabdomos.

Puslapio atnaujinimas ir rinkos duomenų surinkimas yra atskiri procesai. Puslapis tikrina DB kas minutę, o GitHub Actions rinkos duomenų atnaujinimas suplanuotas kas 15 minučių.

Kainų ir žvakių srautus valdo atskiras `prices.js` modulis. Vienas bendras Binance ryšys prenumeruoja instrumentų `miniTicker` ir `kline` srautus, o Hyperliquid `allMids` pateikia vidurines kainas ir `candle` pateikia OHLC žvakes. Binance kainos nurodomos USDT. Nutrūkę ryšiai automatiškai atkuriami, naudojant iki 30 sekundžių didėjantį laukimą. Paslėpus naršyklės kortelę kainų ryšiai ir užklausos sustabdomi, grįžus atnaujinami.

Yahoo kainų JSON maršrutas `/prices/` tikrinamas kas 45 sekundes; sėkmingi atsakymai Django procese laikomi keše 30 sekundžių. Nesėkmės atveju lieka ankstesnė kaina su klaidos žyma. Kainos laikas ir užklausos patikros laikas rodomi atskirai. Naujos kortelių kainos į DB nerašomos. Yahoo grafikai bei signalai atnaujinami iš DB. Minutinis kortelių HTML atnaujinimas išsaugo naujausias srauto kainas, žvakes, pasirinktus filtrus ir išskleistus paaiškinimus.

## Signalų skaičiavimas

Vieno intervalo balą sudaro pirmos ir paskutinės žvakės kryptis, kainos pozicija SMA20 ir SMA50 atžvilgiu bei RSI. Kylanti kryptis prideda 1, krintanti atima 1, šoninė kryptis balo nekeičia. Kaina virš kiekvieno SMA prideda 1, ties juo ar žemiau atima 1. RSI ≥ 55 prideda 1, RSI ≤ 45 atima 1, tarpinės reikšmės balo nekeičia. Tai projekto pasirinktos taisyklės. Reikia bent dviejų indikatorių grupių; abi SMA reikšmės laikomos viena grupe.

Balas ≥ 2 reiškia Bullish, ≤ -2 Bearish, kitais atvejais Neutral. Bendram balui naudojamas svertinis galiojančių intervalų vidurkis: 1h svoris 1, 4h svoris 2, 1d svoris 3. Bendro signalo ribos yra ±1.5. Išskleidžiamas paaiškinimas rodo kiekvieną priežastį, intervalų skaičių, svorių sumą ir jų sutapimą. Kortelių signalai bei „saved RSI“ remiasi DB istorija; gyvo grafiko rodikliai pažymėti atskirai.

## Akcijų fundamentiniai duomenys

`StockFundamentals` saugo P/E pagal paskutinių 12 mėnesių pelną, forward P/E pagal prognozuojamą pelną ir naujausio pateikto ketvirčio pajamų bei pelno YoY augimą. Augimas DB saugomas dalimis, o puslapyje rodomas procentais. Šie laukai taikomi įmonių akcijoms; ETF ir crypto kortelėse įmonės fundamentinių rodiklių blokas nerodomas.

Duomenys gaunami iš Yahoo Finance naudojant laikiną serverio sesiją. Mokamas API raktas nereikalingas. Rinkos atnaujinimo komanda patikrina ir fundamentalus: po sėkmės naujas gavimas leidžiamas po paros, po nesėkmės – po valandos. Šaltinio sutrikimo metu ankstesnės reikšmės išsaugomos su nesėkmingos patikros žyma. Lentelėje pateikiama šaltinio nuoroda, ketvirčio pabaiga, duomenų išsaugojimo ir patikros laikai. Trūkstami bei neteigiami P/E žymimi „No data“, nulinis ir neigiamas augimas išlieka skaitinėmis reikšmėmis.

## Sąrašo valdymas

`dashboard.js` kartu taiko paiešką, turto tipą ir mėgstamų instrumentų filtrą. Mėgstamų instrumentų ID saugomi localStorage. Kai saugykla neprieinama, pasirinkimas veikia atidarytame puslapyje. Kortelių HTML atnaujinimas nekeičia valdiklių ir atkuria atvertus signalų bei fundamentinių duomenų blokus. Filtrą pakeitus vėl parodyti grafikai perskaičiuoja savo dydį.

Svetainės pridėjimo forma priima Yahoo akcijų bei ETF, Binance USDT porų ir Hyperliquid pagrindinės perpetuals rinkos simbolius. Simbolis tikrinamas pasirinktoje platformoje, o Yahoo akcijos ar ETF tipas nustatomas automatiškai. Pradinė 1h, 4h ir 1d istorija gaunama pridėjimo metu. Jei negaunama pagrindinė 1h istorija, tuščias instrumento įrašas nekuriamas. Dalies intervalų sutrikimo atveju išsaugomi gauti duomenys, o likusius vėliau tikrina periodinė užduotis. Akcijų fundamentalai pirmą kartą gaunami periodinio atnaujinimo metu.

Bendri administratoriaus instrumentai matomi visiems. Papildomi pasirinkimai saugomi vienos naršyklės pasirašytame HttpOnly slapuke, todėl jie atskiri ir puslapyje, ir `/data/` bei `/prices/` atsakymuose. Registracijos nėra; išvalius slapukus arba pakeitus naršyklę asmeninis sąrašas neperkeliamas. Pašalinus instrumentą iš sąrašo kito lankytojo pasirinkimas ir bendra simbolio istorija nepakeičiami.

Tas pats simbolio ir šaltinio derinys serveryje naudojamas pakartotinai. Svetainės forma leidžia iki 10 asmeninių pasirinkimų naršyklei ir nekuria naujų registro įrašų pasiekus 30 instrumentų bendrą ribą. Privatiems instrumentams saugoma po 100 naujausių kiekvieno intervalo žvakių – iki 300 įrašų vienam instrumentui. Jų kainų bei fundamentinių duomenų atnaujinimas sustabdomas, jei instrumentas per naršyklių sąrašus nebuvo atidarytas 7 dienas. Sugrįžęs lankytojas vėl suaktyvina periodinį atnaujinimą. Šios ribos aprašytos `watchlist.py`; administratoriaus bendros istorijos saugojimo tvarka išlieka ankstesnė.

Grafikų priartinimą ir slinkimą valdo Chart.js zoom papildinys. Priartinimo mygtukai keičia kainos ir RSI grafikų laiko ašį. Temos pasirinkimas saugomas naršyklės localStorage. Pirmą kartą tema parenkama pagal naršyklės sistemos spalvų nuostatą. Pasikeitus temai, pritaikomos ir grafikų spalvos.

## Duomenų modeliai

**Instrument** saugo instrumento pavadinimą, simbolį, tipą, duomenų šaltinį, paskutinę kainą, patikros laikus, bendro rodymo požymį ir paskutinio privataus naudojimo laiką.

**Candle** saugo ryšį su instrumentu, intervalą, pradžios laiką bei atidarymo, didžiausią, mažiausią ir uždarymo kainas. Unikalumo apribojimas apsaugo nuo pasikartojančių žvakių.

**StockFundamentals** turi vienas-su-vienu ryšį su instrumentu ir saugo akcijos fundamentinių rodiklių momentinę kopiją bei atnaujinimo būseną.

## Technologijos

| Dalis | Technologijos |
| --- | --- |
| Serverio logika | Python, Django |
| Duomenų bazė | PostgreSQL, vietiniam darbui SQLite |
| Sąsaja | Django šablonai, Bootstrap, JavaScript |
| Grafikai | Chart.js, chartjs-chart-financial, Luxon datos adapteris |
| API užklausos | Requests |
| Serverio paleidimas ir statiniai failai | Gunicorn, WhiteNoise |
| Paruošta talpinimo konfigūracija | Render ir Neon |
| Paruoštas atnaujinimo tvarkaraštis | GitHub Actions, kas 15 minučių |

Django ORM naudojamas duomenų skaitymui ir rašymui. Duomenų bazės struktūros pakeitimai aprašyti migracijose. Serverio aplinkos kintamieji nustato DB prisijungimą ir produkcinius nustatymus. Render suteiktas domenas įtraukiamas automatiškai.

## Patikros

Automatiniai testai tikrina API atsakymų apdorojimą, žvakių formatą, duomenų atnaujinimą be pasikartojimų, ankstesnių duomenų išsaugojimą po klaidos ir puslapio veikimą iš DB. Atskiri kainų testai tikrina Yahoo metaduomenis, kešą ir JSON maršruto veikimą nekeičiant DB istorijos. Indikatoriai tikrinami žinomomis SMA ir Wilder RSI reikšmėmis, o fundamentalai – su nulinio augimo, trūkstamų laukų ir šaltinio sutrikimo scenarijais.

Asmeninio sąrašo testai naudoja dvi atskiras naršykles. Tikrinama jų duomenų atskirtis, simbolių patikra, bendros istorijos panaudojimas, pašalinimas, CSRF, slapuko parašas, talpos ribos bei neaktyvių instrumentų praleidimas.

```sh
python config/manage.py test dashboard
```

JavaScript patikros naudoja Node.js standartinius modulius, DOM bei tinklo imitacijas. Jos tikrina paiešką, mėgstamus instrumentus, kainų ryšius, gyvų žvakių ir indikatorių atnaujinimą, priartinimą bei HTML atnaujinimą.

```sh
node tests/prices.test.mjs
node tests/dashboard.test.mjs
node tests/charts.test.mjs
```

GitHub Actions `Project checks` paleidžia Python ir JavaScript patikras kiekvienam push bei pull request. Testai naudoja laikiną SQLite ir nesikreipia į produkcinę DB. Node.js naudojamas tik JavaScript patikroms; svetainę aptarnauja Django.
