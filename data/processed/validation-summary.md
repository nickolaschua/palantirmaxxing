# Population validation summary

Dataset: `sg-residents-2020-mp2019-cbb1c395f60918c1`. Status: **partial_coverage**.

388 population rows: 1 national total, 55 planning-area totals, 332 subzones.
332 display zones; 332 matched; 46 unknown population; 275 eligible; 57 excluded.
6 invalid geometries; 7 overlap pairs affecting 11 zones. No repairs.
Known displayed population: 4,044,340; national published total: 4,044,210; difference: +130.
Eligible population: 3,982,190.

See [machine-readable report](validation-report.json) for every exclusion, join result and aggregate source row; [provenance](provenance.json) records checksums and settings.

| Planning area | Published | Known subzone sum | Difference | Unknown zones |
|---|---:|---:|---:|---:|
| Ang Mo Kio | 162280 | 162270 | -10 | 1 |
| Bedok | 276990 | 276990 | 0 | 0 |
| Bishan | 87320 | 87320 | 0 | 0 |
| Boon Lay | 40 | 30 | -10 | 1 |
| Bukit Batok | 158030 | 158050 | 20 | 0 |
| Bukit Merah | 151250 | 151270 | 20 | 0 |
| Bukit Panjang | 138270 | 138280 | 10 | 0 |
| Bukit Timah | 77860 | 77850 | -10 | 0 |
| Central Water Catchment | - | 0 | unknown | 1 |
| Changi | 1850 | 1850 | 0 | 0 |
| Changi Bay | - | 0 | unknown | 1 |
| Choa Chu Kang | 192070 | 192070 | 0 | 0 |
| Clementi | 91990 | 91990 | 0 | 0 |
| Downtown Core | 3190 | 3210 | 20 | 3 |
| Geylang | 110110 | 110100 | -10 | 0 |
| Hougang | 227560 | 227570 | 10 | 1 |
| Jurong East | 78600 | 78600 | 0 | 2 |
| Jurong West | 262730 | 262730 | 0 | 2 |
| Kallang | 101290 | 101290 | 0 | 0 |
| Lim Chu Kang | 110 | 110 | 0 | 0 |
| Mandai | 2090 | 2090 | 0 | 2 |
| Marina East | - | 0 | unknown | 1 |
| Marina South | - | 0 | unknown | 1 |
| Marine Parade | 46220 | 46220 | 0 | 2 |
| Museum | 510 | 520 | 10 | 0 |
| Newton | 8260 | 8270 | 10 | 0 |
| North-Eastern Islands | 50 | 50 | 0 | 0 |
| Novena | 49330 | 49330 | 0 | 0 |
| Orchard | 920 | 920 | 0 | 0 |
| Outram | 18340 | 18330 | -10 | 0 |
| Pasir Ris | 147110 | 147120 | 10 | 0 |
| Paya Lebar | 40 | 40 | 0 | 3 |
| Pioneer | 80 | 70 | -10 | 1 |
| Punggol | 174450 | 174460 | 10 | 2 |
| Queenstown | 95930 | 95960 | 30 | 0 |
| River Valley | 10070 | 10070 | 0 | 0 |
| Rochor | 13120 | 13120 | 0 | 1 |
| Seletar | 300 | 300 | 0 | 2 |
| Sembawang | 102640 | 102640 | 0 | 1 |
| Sengkang | 249370 | 249380 | 10 | 1 |
| Serangoon | 116900 | 116900 | 0 | 0 |
| Simpang | - | 0 | unknown | 4 |
| Singapore River | 3260 | 3270 | 10 | 0 |
| Southern Islands | 1940 | 1940 | 0 | 1 |
| Straits View | - | 0 | unknown | 1 |
| Sungei Kadut | 750 | 750 | 0 | 0 |
| Tampines | 259900 | 259900 | 0 | 0 |
| Tanglin | 21810 | 21810 | 0 | 0 |
| Tengah | 10 | 10 | 0 | 5 |
| Toa Payoh | 121850 | 121840 | -10 | 1 |
| Tuas | 70 | 70 | 0 | 1 |
| Western Islands | 10 | 10 | 0 | 2 |
| Western Water Catchment | 640 | 640 | 0 | 2 |
| Woodlands | 255130 | 255120 | -10 | 0 |
| Yishun | 221610 | 221610 | 0 | 0 |

- Historical resident population (citizens and permanent residents), not everyone physically present or live crowd levels.
- SingStat notes that rounded counts may not add to totals; no values are adjusted to reconcile.
- Source '-' means nil or negligible or not significant; treated as qualified unknown, not numeric zero. No suppressed numeric values are invented.
- Density is an average over supplied zone geometry, including any water in that geometry; no independent water mask was applied.
- Invalid geometry and both participants in every positive-area overlap are excluded without repair; full-resolution source geometry remains in the display artifact.
- The existing city/coastline tiles omit some offshore geometry. Population polygons are independent of that clipping; all boundary extents fit the current camera bounds.
- PEC-candidate coverage is partial, not a claim that the whole dataset is PEC-ready; downstream consumers must respect exclusions and nullable population.
