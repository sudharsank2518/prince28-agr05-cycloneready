# CycloneReady Dataset

## Project data strategy

CycloneReady is a college project focused on cyclone and urban flood preparedness, response and recovery, with particular attention to realistic Tamil Nadu scenarios.

The initial data strategy uses historical cyclone observations together with an original CycloneReady solution document developed by the project team.

The collected corpus includes historical cyclone data and disaster-management guidance documents.
The reuse of each document is subject to its source-specific licence or terms. The project does not assume unrestricted reproduction or redistribution.

- Collector User-Agent: `examate-student-bot/0.1 (student project; +https://github.com/sudharsank2518/prince28-agr05-cycloneready)`

## Collection summary

- Files collected: 5
- PDF pages: 450
- Extracted text tokens (approx.): 4,248,770
- Scanned or text-empty PDF pages: 13
- Files with PDF extraction errors: 0
- Disk usage: 66.56 MB

Token counts are approximate character-based estimates, not exact counts from a language-model tokenizer.

## Source summary

| Source | Files | Pages | Size (MB) | Licence |
|---|---:|---:|---:|---|
| Government of Tamil Nadu | 1 | 76 | 2.42 | Government publication; reuse terms to be checked in the document |
| Gujarat Institute of Disaster Management (GIDM) | 2 | 318 | 13.29 | Free reproduction for non-profit humanitarian, social and environmental purposes; see document disclaimer; Government publication; reuse terms to be checked in the document |
| Humanitarian Data Exchange (HDX) | 1 | 0 | 15.51 | CC BY-IGO |
| National Disaster Management Authority (NDMA) | 1 | 56 | 35.34 | Government publication; reuse terms not stated |

## Document inventory

| Title | Source | URL | Licence | File | Pages | Size (MB) | Fetch time (seconds) | SHA-256 |
|---|---|---|---|---|---:|---:|---:|---|
| IBTrACS Storm Tracks within 2000 km of India | Humanitarian Data Exchange (HDX) | https://data.humdata.org/dataset/9bc88226-8747-499a-b100-d7968da6d9d6/resource/a127656e-7ef8-4b09-9d17-31ce61d199d9/download/ibtracs_all_list_v04r01_ind.csv | CC BY-IGO | data\raw\72ed60c1400ab497f92c982ce737e17b6018f3daef08ec80efb3c3a6ab810e21.csv | 0 | 15.51 | 3.061 | `4f6dbef85c2f1ae30169e35bb2bd47f69a4baa8bb3cf755afd9503bd71bc2c1d` |
| SDRF Guidelines 2026 | National Disaster Management Authority (NDMA) | https://ndma.gov.in/sites/default/files/PDF/SDRF%20Guidelines%202026.pdf | Government publication; reuse terms not stated | data\manual_pdfs\SDRF_Guidelines_2026.pdf | 56 | 35.34 | Not recorded | `a01de3ca56d6b19ba339494998003156780705ca80abd896263ecbf066d22bc1` |
| Training Module on Cyclone Risk Management | Gujarat Institute of Disaster Management (GIDM) | https://gidm.gujarat.gov.in/sites/default/files/educate_your_self_document/Training%20Module%20on%20Cyclone%20Risk%20Management.pdf | Free reproduction for non-profit humanitarian, social and environmental purposes; see document disclaimer | data\manual_pdfs\Cyclone_Risk_Management_Training_Module.pdf | 128 | 3.91 | Not recorded | `ea86604e7aa1ddb07350a9b226bf4f93a5d6c16e7edfbf318dcddeec4f08878c` |
| National Disaster Management Guidelines: Management of Urban Flooding | Gujarat Institute of Disaster Management (GIDM) | https://gidm.gujarat.gov.in/sites/default/files/educate_your_self_document/Guidelines%20on%20Management%20Urban%20Flooding.pdf | Government publication; reuse terms to be checked in the document | data\manual_pdfs\Urban_Flooding_Guidelines.pdf | 190 | 9.38 | Not recorded | `63d8e5d9a578f11c69dba8fec4da06b4a9b824bc7aa8ebe929fcc93b2dfdf6a2` |
| Tamil Nadu State Disaster Management Policy 2023 | Government of Tamil Nadu | https://cdn.s3waas.gov.in/s3bca82e41ee7b0833588399b1fcd177c7/uploads/2023/05/2023051554.pdf | Government publication; reuse terms to be checked in the document | data\manual_pdfs\Tamil_Nadu_State_Disaster_Management_Policy_2023.pdf | 76 | 2.42 | Not recorded | `2ad8f015337d6df2592b4e85af87d881861ddca8abbc77146b7c72a7cf942585` |

## Crawl metrics

- Files requiring more than one attempt: 0
- Duplicate SHA-256 groups: 0
- Records with fetch duration: 3
- Slowest host by cumulative fetch time: data.humdata.org (10.223 seconds total)

## Host fetch durations

| Host | Total recorded fetch time (seconds) |
|---|---:|
| data.humdata.org | 10.223 |
| www.ncei.noaa.gov | 1.029 |

## Duplicate files

- No duplicate file hashes detected.

## Original CycloneReady solution document

The project will develop its own original solution document covering cyclone preparedness, urban flood preparedness, Tamil Nadu scenarios, evacuation, emergency response and recovery.

The document will distinguish verified historical observations, sourced facts, project assumptions and original recommendations.

It is planned project content and is not yet counted as a collected dataset file.

## Known gaps and limitations

- The current collected corpus contains historical cyclone data, not a complete disaster-management knowledge base.
- The original CycloneReady solution document still needs to be authored and reviewed.
- IBTrACS does not independently validate every preparedness or response recommendation.
- Missing wind-speed and pressure values must remain unknown, not be treated as zero.
- The collected dataset includes 450 PDF pages across four PDF documents.
- Thirteen PDF pages are scanned or text-empty and may require OCR.
- Urban flood-specific historical datasets may be added after their sources and licences are reviewed.
- Unknown file formats are not included in extracted text estimates.
