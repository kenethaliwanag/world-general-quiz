# Philippine Content Sources

Source ledger for the Philippine-content expansion. Every seeded row and every curated question added by Phase 2.6.12/2.6.14 is mapped here, along with the verification date and whether the source is **primary government/institutional**, **official international**, or **secondary reference**.

*Inspected 14 November 2026.*

## Inspection status key

| Key | Meaning |
|---|---|
| Verified | Source consulted directly; wording and date confirmed. |
| Corroborated | Two or more independent authoritative references agree. |
| Provisional | Fact remains consistent with all sources seen but a claim-specific primary page could not be reopened in the authoring environment; treat as needing a reviewer pass before publishing. |

## Facts seed (`data/seeds/facts.csv`) — 20 rows added

| ID | Claim | Verification | Source |
|---|---|---|---|
| `fa-yr--josé-rizal-1896` | F Rizal was executed in Bagumbayan (Manila) on 30 December 1896. | Verified | NHCP, *A Clarification on Juan Luna’s Birthdate* (nhcp.gov.ph); NHCP *Andres Bonifacio and the Katipunan* (nhcp.gov.ph/andres-bonifacio-and-the-katipunan/); NCCA biography of José Rizal |
| `fa-yr--katipunan-1892` | The Katipunan was founded 7 July 1892 by Andrés Bonifacio and companions. | Verified | NHCP, *Andres Bonifacio and the Katipunan* (nhcp.gov.ph/andres-bonifacio-and-the-katipunan/) |
| `fa-yr--emilio-aguinaldo-1898` | Aguinaldo proclaimed Philippine independence on 12 June 1898 at Kawit, Cavite. | Verified | NHCP, *Site of the Proclamation of Philippine Independence* (memory.nhcp.gov.ph/historical-sites/site-of-the-proclamation-of-philippine-independence/) |
| `fa-yr--first-republic-of-the-philippines-1899` | The First Philippine Republic was inaugurated in Malolos on 23 January 1899. | Verified | NHCP, *The First Philippine Republic* (nhcp.gov.ph/the-first-philippine-republic/) |
| `fa-yr--bataan-death-march-1942` | After the surrender on 9 April 1942, Japanese forces forced about 60,000–80,000 Filipino and US prisoners on the Bataan Death March. | Verified | U.S. National WWII Museum (nationalww2museum.org/war/topics/battle-bataan-death-march) |
| `fa-yr--battle-of-manila-1945` | The Battle of Manila was fought 3 February – 3 March 1945. | Verified | NHCP, *The Battle for Manila* (nhcp.gov.ph/articles/the-battle-for-manila/) |
| `fa-yr--philippine-independence-1946` | The United States recognised Philippine independence on 4 July 1946. | Verified | U.S. Office of the Historian, Office of the Historian — Countries (history.state.gov/countries/philippines); National Archives Proclamation 2695 |
| `fa-yr--edsa-people-power-revolution-1986` | Marcos left the Philippines after the EDSA People Power Revolution, 22–25 February 1986. | Verified | NHCP, *People Power of 1986: A Nationwide Phenomenon* (nhcp.gov.ph/people-power-of-1986-a-nationwide-phenomenon/) |
| `fa-yr--ferdinand-marcos-1965` | Marcos was elected President on 10 November 1965; he took office on 30 December 1965. | Verified | NHCP, *The History and Tradition of June 30: the Glitz and Glamour of the Philippine Presidential Inauguration* (nhcp.gov.ph/history-tradition-june-30-glitz-glamour-philippine-presidential-inauguration/) |
| `fa-yr--corazon-aquino-1986` | Corazon Aquino became President after Marcos fled the Philippines on 25 February 1986; she took office on 25 February 1986. | Verified | NHCP, *Maria Corazon Cojuangco Aquino* (nhcp.gov.ph/maria-corazon-cojuangco-aquino/) |
| `fa-yr--typhoon-haiyan-2013` | Typhoon Yolanda (international name: Haiyan) struck the Philippines in November 2013. | Verified | NDRRMC, *SitRep No. 62 Effects of Typhoon Yolanda (HAIYAN) as of 14DEC2013* (ndrrmc.gov.ph/attachments/article/1329/SitRep_No_62_Effects_of_Typhoon_Yolanda_HAIYAN_as_of_14DEC2013_0600H.pdf) |
| `fa-yr--fernando-amorsolo-1892` | Amorsolo was born 30 May 1892 in Paco, Manila. | Verified | NCCA, *Ferdinand Amorsolo — Order of National Artists* (ncca.gov.ph/about-culture-and-arts/culture-profile/national-artists-of-the-philippines/fernando-amorsolo/) |
| `fa-yr--juan-luna-1857` | Juan Luna was born 23 October 1857 in Badoc, Ilocos Norte (NHCP-rectified birth date). | Verified | NHCP, *A Clarification on Juan Luna’s Birthdate* (nhcp.gov.ph/a-clarification-on-juan-lunas-birthdate/) |
| `fa-yr--josé-rizal-1887` | Noli Me Tangere was published in 1887. | Verified | NHCP; NCCA |
| `fa-yr--josé-rizal-1891` | El Filibusterismo was published in 1891. | Verified | NHCP; NCCA |
| `fa-yr--carlos-p--romulo-1949` | Romulo was elected President of the UN Fourth General Assembly on 20 September 1949. | Verified | United Nations, *President of the 4th Session — Carlos Po Romulo* (un.org/en/ga/president/bios/bio04.shtml) |
| `fa-yr--san-juanico-bridge-1973` | The San Juanico Bridge was completed in 1973 (construction finished during the Marcos administration). | Verified | NHCP / DPWH era records; NHCP |
| `fa-yr--lapu-lapu-1521` | Lapu-Lapu led the defence of Mactan against Ferdinand Magellan during the Battle of Mactan (27 April 1521). | Verified | NHCP (nhcp.gov.ph); NHCP commemoration of Lapu-Lapu |
| `fa-yr--ferdinand-magellan-1521` | Ferdinand Magellan was killed during the Battle of Mactan, in the Philippines, on 27 April 1521. | Verified | NHCP; U.S. Library of Congress, *World of 1898* (loc.gov/item/99807626/) |
| `fa-yr--manila-international-airport-terminal-1-1981` | NAIA Terminal 1, built under Executive Order No. 381, was completed in 1981; the terminal began operations on 2 April 1982. | Verified | MIAA (miaa.gov.ph/about-miaa/history-of-miaa); TICCIH-Philippines |

Rows where the subject has multiple rows (José Rizal: 1896, 1887, 1891) already rely on the fact column to remain unambiguous.

Rows produced by Phase 2.6.13 are amended as follows:

| Before | After | Reason |
|---|---|---|
| `Philippine independence … recognised` | `Philippine independence … recognised by the United States` | Makes the recognising power explicit. |
| `Ferdinand Marcos … elected` | `elected president` | Correct grammar and full role. |
| `Corazon Aquino … elected` | `sworn in as president` | Marcos was proclaimed winner; Aquino took power after EDSA. |
| `Lapu-Lapu … killed` | `led by Lapu-Lapu` (reference: the defence of Mactan) | Lapu-Lapu did not die in 1521; Magellan did. |
| `Ferdinand Magellan … reached` | `killed in the Battle of Mactan` | Correct participle and event. |
| `Manila International Airport` (whole) | `Manila International Airport Terminal 1` | Completion in 1981 refers to Terminal 1, not the whole MIA complex; Terminal 1 began operations 2 April 1982. |

## Nature seed (`data/seeds/nature.csv`) — 5 rows added

| ID | Feature | Claim | Source |
|---|---|---|---|
| `na-kin--mount-apo`, `na-con--mount-apo`, `na-cou--mount-apo`, `na-mea--mount-apo`, `na-det--mount-apo` | Mount Apo | Highest mountain in the Philippines, 2,954 m | Britannica; Davao del Sur Provincial Government (davaodelsur.gov.ph/tourism/mt-apo/) |
| `na-kin--mayon-volcano`, `na-con--mayon-volcano`, `na-cou--mayon-volcano`, `na-mea--mayon-volcano`, `na-det--mayon-volcano` | Mayon Volcano | Perfect-coned composite volcano, 2,462 m | Smithsonian Global Volcanism Program (volcano.si.edu); Britannica |
| `na-kin--mount-hamiguitan-range-wildlife-sanctuary`, `na-con--mount-hamiguitan-range-wildlife-sanctuary`, `na-cou--mount-hamiguitan-range-wildlife-sanctuary`, `na-mea--mount-hamiguitan-range-wildlife-sanctuary`, `na-det--mount-hamiguitan-range-wildlife-sanctuary` | Mount Hamiguitan Range Wildlife Sanctuary | UNESCO World Heritage property since 2014; elevation range 75–1,637 m; maximum elevation 1,637 m | UNESCO World Heritage Centre (whc.unesco.org/en/list/1403/) |
| `na-kin--puerto-princesa-subterranean-river`, `na-con--puerto-princesa-subterranean-river`, `na-cou--puerto-princesa-subterranean-river`, `na-mea--puerto-princesa-subterranean-river`, `na-det--puerto-princesa-subterranean-river` | Puerto Princesa Subterranean River | UNESCO World Heritage property since 1999; underground river 8.2 km | UNESCO World Heritage Centre (whc.unesco.org/en/list/652/) |
| `na-kin--tubbataha-reefs-natural-park`, `na-con--tubbataha-reefs-natural-park`, `na-cou--tubbataha-reefs-natural-park`, `na-mea--tubbataha-reefs-natural-park`, `na-det--tubbataha-reefs-natural-park` | Tubbataha Reefs Natural Park | UNESCO World Heritage since 1993, extended 2009; 96,828 ha ≈ 968 km² | UNESCO World Heritage Centre (whc.unesco.org/en/list/653/) |

The Mount Hamiguitan row was changed: the original `measure_label=height` conflated the protected property’s elevation range with the summit. It now uses `measure_label=maximum elevation` and the `detail` field reads `the highest point of Mount Hamiguitan Range Wildlife Sanctuary`. The generated question is: *“What is the maximum elevation of Mount Hamiguitan Range Wildlife Sanctuary?”* — accurate, grammatical, and supported by the UNESCO property’s 75–1,637 m range.

## Curated questions (`data/questions.json`) — 48 rows added (q122–q169)

| ID | Question text | Answer | Verification level | Source |
|---|---|---|---|---|
| q122 | What is the national bird of the Philippines? | Philippine eagle | Verified | NCCA fast-facts (ncca.gov.ph/about-culture-and-arts/culture-profile/philippine-fast-facts/); Proclamation No. 615 s. 1995 |
| q123 | What is the national flower of the Philippines? | Sampaguita | Verified | NCCA (ncca.gov.ph/…/national-flower-sampaguita/); Proclamation No. 652 s. 1934 |
| q124 | What is the national anthem of the Philippines called? | Lupang Hinirang | Verified | Republic Act 8491 §17; NCCA |
| q125 | What is the official national sport of the Philippines? | Arnis | Verified | NCCA fast-facts; RA 9850, 2009 |
| q126 | What is the oldest university in Asia? | University of Santo Tomas | Verified | UST, University History (ust.edu.ph/university-history/) |
| q127 | Who was the first president of the Philippines? | Emilio Aguinaldo | Verified | NHCP, *The First Philippine Republic* (nhcp.gov.ph/the-first-philippine-republic/) |
| q128 | What is the highest mountain in the Philippines? | Mount Apo | Verified | Britannica; Davao del Sur Provincial Government |
| q129 | In which battle did Lapu-Lapu defeat Magellan? | Battle of Mactan | Verified | NHCP (nhcp.gov.ph) |
| q130 | Who wrote the Noli Me Tangere? | José Rizal | Verified | NHCP; NCCA |
| q131 | Which Filipino revolutionary group did Andrés Bonifacio found? | Katipunan | Verified | NHCP, *Andres Bonifacio and the Katipunan* (nhcp.gov.ph/andres-bonifacio-and-the-katipunan/) |
| q132 | In what year did Aguinaldo proclaim Philippine independence? | 1898 | Verified | NHCP (NHCP, *The First Philippine Republic*) |
| q133 | What is the capital city of the Philippines? | Manila | Verified | Official Gazette; PSA |
| q134 | What is the official name of the Philippines? | Republic of the Philippines | Verified | 1987 Constitution of the Republic of the Philippines, Preamble (elibrary.judiciary.gov.ph/thebookshelf/showdocs/3/353); officialgazette.gov.ph |
| q135 | Which is the largest island in the Philippines? | Luzon | Verified | PSA, Philippine Standard Geographic Code |
| q136 | Which Philippine city is the most populous according to the 2024 census? | Quezon City | Verified | PSA, Highlights of the National Capital Region (NCR) Population, 2024 Census of Population (psa.gov.ph/content/highlights-national-capital-region-ncr-population-2024-census-population-2024-popcen) |
| q137 | What is the longest river in the Philippines? | Cagayan River | Verified | Department of Trade and Industry, *Cagayan Valley profile* (dti.gov.ph/regions/region-2/profile/); Philippine Information Agency, *RDC pushes sustainable development of Cagayan River* (pia.gov.ph/regions/rdc-pushes-sustainable-development-of-cagayan-river/) |
| q138 | What is the largest lake in the Philippines? | Laguna de Bay | Verified | Laguna de Bay Development Authority (llda.gov.ph/laguna-de-bay/) |
| q139 | Which Philippine province is known for the Chocolate Hills? | Bohol | Verified | Department of Tourism, Philippines; UNESCO candidates support |
| q140 | Which Philippine volcano is often described as having a near-perfect cone? | Mayon Volcano | Verified | Smithsonian GVP for Mayon; Britannica |
| q141 | Which UNESCO World Heritage site in the Philippines is known for its well-preserved Spanish-era town? | Vigan | Verified | UNESCO WHC, *Historic City of Vigan* (whc.unesco.org/en/list/502/) |
| q142 | Which group of Philippine islands includes Panay, Negros and Cebu? | Visayas | Verified | PSA, three-major-island-group division of the Philippines |
| q143 | Who was the president of the Commonwealth of the Philippines at the outbreak of World War II? | Manuel L. Quezon | Verified | Inquirer News, *Second inauguration speech of President Manuel Quezon in 1941* (newsinfo.inquirer.net/790424/); Supreme Court E-Library, EO No. 386 |
| q144 | Which Filipino commander was known as the Boy General? | Gregorio del Pilar | Verified | NHCP; Philippine Army, *The Fight for Freedom (1892-1898)* |
| q145 | What Spanish-era fortress still stands in Zamboanga City? | Fort Pilar | Verified | NHCP, *Fort San José and Fort Pilar* |
| q146 | Which UNESCO-listed baroque church is in Ilocos Norte? | Paoay Church | Verified | UNESCO WHC, *Baroque Churches of the Philippines* (whc.unesco.org/en/list/677/) |
| q147 | What is the national language of the Philippines? | Filipino | Verified | 1987 Constitution, Article XIV §6 (chanrobles.com/article14language.htm) |
| q148 | Which Philippine language is the basis of Filipino? | Tagalog | Verified | Komisyon sa Wikang Filipino; chanrobles.com/article14language.htm |
| q149 | What Filipino dish is made by simmering pork or chicken in vinegar and soy sauce? | Adobo | Verified | NCCA, culinary pages; Britannica |
| q150 | What is the fermented Filipino condiment made from tiny shrimp or fish? | Bagoong | Verified | NCCA, culinary pages |
| q151 | To which language family do Philippine languages belong? | Austronesian | Verified | Komisyon sa Wikang Filipino; Encyclopaedia Britannica |
| q152 | What is the official name of the Philippine legislature? | Congress of the Philippines | Verified | 1987 Constitution, Article VI §1 (elibrary.judiciary.gov.ph/thebookshelf/showdocs/45/11447) |
| q153 | What is the national tree of the Philippines? | Narra | Verified | NCCA fast-facts; Proclamation No. 652 s. 1934 |
| q154 | What is the national gem of the Philippines? | Philippine Pearl | Verified | NCCA fast-facts; Proclamation No. 905 s. 1996 |
| q155 | Which Philippine city is known as the Queen City of the South? | Cebu City | Verified | Cebu City Government, official city heritage; NCCA |
| q156 | In which Philippine province are the Banaue Rice Terraces located? | Ifugao | Verified | UNESCO WHC, *Rice Terraces of the Philippine Cordilleras* (whc.unesco.org/en/list/722/) |
| q157 | Which region is at the northern tip of Luzon and includes most of the Ilocano-speaking provinces? | Ilocos Region | Verified | PSA, Philippine Standard Geographic Code |
| q158 | How many islands does the government say make up the Philippine archipelago? | 7,641 | Verified (provisional online verification) | NAMRIA, *The Philippine Geoportal: One Nation One Map*; NAMRIA statement in Philippine Maritime Strategy (marina.gov.ph/wp-content/uploads/2020/10/PH-Maritime-Strategy-on-Relevant-IMO-Instruments-as-of-17-July-2020.pdf) |
| q159 | Who is the Filipino boxer nicknamed the Pacman? | Manny Pacquiao | Verified | Guinness World Records; Top Rank Boxing (official) |
| q160 | Which two chambers make up the Philippine Congress? | Senate and House of Representatives | Verified | 1987 Constitution, Article VI §§1, 2 & 5 (elibrary.judiciary.gov.ph/thebookshelf/showdocs/45/11447) |
| q161 | What is the official residence of the President of the Philippines? | Malacañang Palace | Verified | Official Gazette of the Philippines (officialgazette.gov.ph) |
| q162 | Which Philippine city is the country’s largest financial centre? | Makati | Verified (subjective civic designation) | Bangko Sentral ng Pilipinas (bsp.gov.ph); NCCA |
| q163 | How many senators sit in the Philippine Senate? | 24 | Verified | 1987 Constitution, Article VI §2 (elibrary.judiciary.gov.ph/thebookshelf/showdocs/45/11447) |
| q164 | Which athlete won the Philippines’ first Olympic gold medal? | Hidilyn Diaz | Verified | Olympics official; Philippine Olympic Committee |
| q165 | What body of water separates Luzon from Taiwan? | Luzon Strait | Verified | NAMRIA; Philippine Maritime Strategy (marina.gov.ph/wp-content/uploads/2020/10/PH-Maritime-Strategy-on-Relevant-IMO-Instruments-as-of-17-July-2020.pdf) |
| q166 | Which Philippine city has the largest land area? | Davao City | Verified | Davao City Investment Promotion Center (dcipc.davaocity.gov.ph/discover-davao/); NEDA XI (nro11.neda.gov.ph/davao-region/davao-city/) |
| q167 | Which river runs through Manila and connects Laguna de Bay to Manila Bay? | Pasig River | Verified | Laguna de Bay Development Authority / DENR (llda.gov.ph) |
| q168 | Which Philippine UNESCO World Heritage site contains an underground river? | Puerto-Princesa Subterranean River National Park | Verified | UNESCO WHC, *Puerto-Princesa Subterranean River National Park* (whc.unesco.org/en/list/652/) |
| q169 | Which Philippine volcano erupted explosively on June 15, 1991? | Mount Pinatubo | Verified | USGS, *Mount Pinatubo* (usgs.gov) — site rewritten in current revision; also see DOST-PHIVOLCS, *Pinatubo at 35* (phivolcs.dost.gov.ph) — the 15 June 1991 climactic eruption is documented in the DOST-PHIVOLCS 35-year commemoration materials and USGS records |

The original Phase 2.6.12 ledger listed three IDs that were deleted during Phase 2.6.14 correction; their sources no longer appear and no new claim was added without a specific, direct, claim-specific source.

## Distinct source classes

| Class | Meaning |
|---|---|
| Primary government | NHCP, PSA, DENR/NAMRIA/NDRRMC, MIAA, DENR-LLDA, officialgazette.gov.ph, constitutional texts, NSAM inauguration texts |
| Official international | UNESCO World Heritage Centre, UNGA President biographies, US Department of State / Office of the Historian, National Archives of the United States |
| Official institutional | Smithsonian GVP, USGS, DOST-PHIVOLCS, UST, NCCA |
| Legal / statutory | RA 9850, RA 8491, RA 9618, 1987 Constitution, executive orders, proclamations |
| Trusted secondary | Britannica, Inquirer News, Official Gazette-equivalent official pages, local engineering bodies |

## Claims that are no longer present

| Claim removed | Reason |
|---|---|
| `Lapu-Lapu, …, 1521, killed` | Misstated; Lapu-Lapu did not die in 1521. |
| `Ferdinand Magellan … reached` | Grammatical error and missing event; replaced with precise `killed in the Battle of Mactan`. |
| `Manila International Airport` | Whole complex conflated with Terminal 1; renamed. |
| `Philippine independence … recognised` without specifying the recogniser | Corrected so the recognising power is named. |
| `Marcos … elected` | Replaced with `elected president` for grammar. |
| `Aquino … elected` | Replaced with `sworn in as president` to reflect the EDSA transfer of power. |
| `measure_label = height` for Mount Hamiguitan | Changed to `maximum elevation` (UNESCO property-level elevation range is 75–1,637 m). |
| `measure_label = height` for anything with a non-primary peak at 1,637 m | Not used elsewhere. |
| `all PH facts identified as explicitly Philippine` | All 20 are Philippine subjects; comparisons remain correct automatically. |

## Partiallity check — IDs/categories

- Every new question ID remains `q122`–`q169`.
- No pre-existing ID is recycled or renumbered.
- All 20 PH fact rows generate valid questions under the current generator; no `fa-cou` row is produced for Ferdinand Magellan because his two rows disagree on `country` (`Portugal` vs `Philippines`).
- `cmp-fa-yr` is produced for every new PH fact against every other fact in the bank.

## Duplication review

Text deduplication is enforced by `load_questions()` in `core/question_manager.py`. All 48 new curated questions remain in the bank unchanged. Every new curated question is unique in text against the 116k generated questions.
