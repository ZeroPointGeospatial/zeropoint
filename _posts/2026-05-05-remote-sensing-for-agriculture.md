---
layout: post
title: "Remote Sensing for Agriculture: How Satellite Data Is Changing Farming in Kenya"
---

# Remote Sensing for Agriculture: How Satellite Data Is Changing Farming in Kenya

In 1972, NASA launched Landsat 1 — the first satellite designed specifically to observe the earth's land surface. The images it returned were revolutionary, even at a resolution of 80 metres per pixel.

Today, a constellation of commercial and government satellites produces imagery at resolutions below 50 centimetres, updated daily, accessible via API, and in many cases free. The same satellite data that intelligence agencies and multinational corporations relied on a decade ago is now available to a county agricultural extension officer with a laptop and an internet connection.

For Kenyan agriculture — which employs over 40% of the workforce and drives the rural economy — this represents a significant shift in what is knowable, and therefore what is possible.

---

## What Remote Sensing Measures

Remote sensing works by detecting electromagnetic energy reflected or emitted from the earth's surface. Different materials reflect different wavelengths of light in characteristic ways — what is called their **spectral signature**.

Healthy green vegetation, for example, strongly reflects near-infrared (NIR) light and absorbs red light. This is the basis for the most widely used vegetation index in agriculture:

### NDVI — Normalised Difference Vegetation Index

NDVI = (NIR - Red) / (NIR + Red)

The result is a number from -1 to +1. High values (above 0.6) indicate dense, healthy vegetation. Low values indicate bare soil, stressed crops, or no vegetation.

NDVI can be calculated from Landsat, Sentinel-2, or commercial satellite data, and provides a consistent measure of crop health and biomass that can be tracked over time.

Other useful indices for agriculture include:

- **NDWI** (Normalised Difference Water Index) — detects water content in vegetation and soil moisture
- **EVI** (Enhanced Vegetation Index) — improved vegetation measure that reduces atmospheric interference
- **SAVI** (Soil-Adjusted Vegetation Index) — NDVI variant that accounts for soil brightness in areas of sparse cover
- **NDRE** (Normalised Difference Red Edge) — sensitive to chlorophyll content, useful for detecting early stress before it is visible to the eye

---

## Satellite Data Sources Available Today

### Sentinel-2 (Free)

The European Space Agency's Sentinel-2 satellites provide 10-metre resolution multispectral imagery, updated every 5 days at the equator. The data is free to download from the Copernicus Open Access Hub.

For most agricultural monitoring applications in Kenya — crop mapping, seasonal change detection, large-scale stress assessment — Sentinel-2 is sufficient and costs nothing.

### Landsat 8/9 (Free)

NASA's Landsat programme provides 30-metre resolution imagery with a 16-day revisit cycle, free from the USGS Earth Explorer. Useful for long-term analysis — the archive goes back to 1972, giving over 50 years of comparable imagery.

### Planet Labs (Commercial)

Planet's constellation of small satellites produces daily imagery at 3–5 metre resolution globally. Commercial pricing, but accessible for project-based work. For monitoring fast-changing situations — locust swarms, flooding, drought onset — the daily update frequency is valuable.

### Drone-Mounted Multispectral (Local)

For farm-scale precision agriculture, drone-mounted multispectral cameras (such as the MicaSense Altum) produce imagery at 5–10cm resolution with 5+ spectral bands. Combined with RTK GPS ground control, this data supports variable-rate fertiliser application, irrigation zoning, and plant-level stress detection.

---

## Applications Across the Agricultural Value Chain

### Crop Type Mapping

By tracking how NDVI evolves through the growing season, it is possible to classify what crops are growing where — and build area estimates without sending enumerators to every field. This is used by county agricultural departments to estimate production, by insurers to define coverage zones, and by input suppliers to target distribution.

The challenge is the diversity of smallholder agriculture. Kenya's mixed smallholder systems — small fields, multiple intercropped species, irregular boundaries — are harder to classify than large monoculture farms. High-resolution imagery and machine learning classification have improved accuracy significantly, but ground truth data collection remains important.

### Drought and Stress Monitoring

When crops are stressed — by drought, pest pressure, nutrient deficiency, or disease — their spectral signature changes before it is visible to the eye. NDVI drops, red-edge reflectance shifts. Satellite monitoring can detect this emerging stress at scale, allowing extension services to target interventions.

During the 2022 Horn of Africa drought, remote sensing data was central to the humanitarian response — mapping affected areas, tracking vegetation recovery, and supporting targeting of food assistance. The same capability applies at county level for early warning and response.

### Irrigation Management

Satellites can estimate evapotranspiration — the water lost from soil and plants — using surface temperature data from thermal bands. This allows irrigation managers to calculate actual crop water requirements across a scheme, identify areas of over- or under-irrigation, and schedule water delivery more efficiently.

Kenya's large irrigation schemes — Mwea, Perkerra, Bunyala — are increasingly using this data to improve water use efficiency.

### Land Use Change Detection

By comparing satellite imagery from different dates, it is straightforward to detect land use change — forest clearing, new agricultural expansion, wetland drainage. This is relevant for:

- County land use planning and enforcement
- Carbon project baseline and monitoring
- Environmental impact assessment
- Investment due diligence (is the farm claim consistent with what the land actually shows?)

---

## Getting Started with Remote Sensing Data

You do not need expensive software or deep technical skills to start using satellite data.

**Google Earth Engine** is a cloud-based platform that provides free access to the full Sentinel and Landsat archives, with a JavaScript and Python API for analysis. It runs in a browser, requires no local data download, and can process country-scale analyses in seconds. It has a learning curve, but tutorials are freely available.

**QGIS with the Semi-Automatic Classification Plugin** allows desktop processing of downloaded satellite imagery, including band calculation, classification, and change detection. Free and well-documented.

**Sentinel Hub** provides a browser interface to Sentinel-2 data with built-in index visualisation — you can view NDVI, NDWI, and other indices over any area of Kenya without downloading anything.

---

## Limitations to Be Honest About

Remote sensing is powerful but not magic.

- **Cloud cover** is a genuine problem in Kenya's high-rainfall areas and during the long rains. Optical imagery is useless under cloud. Radar data (Sentinel-1) penetrates cloud but is harder to interpret.
- **Ground truthing is essential** — satellite analysis always needs validation with field observations to be reliable.
- **Mixed pixels** at 10-metre resolution can contain multiple crop types or land cover classes, complicating classification.
- **Temporal resolution** of free data (5–16 days) may miss important short-duration events.
- **Analysis requires skills** that are not yet widely available in county agriculture departments.

The trajectory is towards better data, cheaper access, and easier tools. But the gap between the technology's potential and its current application in Kenyan agriculture remains large — and bridging it requires investment in skills as much as in data.

---

## The Role of Survey in Remote Sensing

Satellite and drone remote sensing data needs precise georeferencing to be useful for analysis and comparison over time. Ground control points surveyed with RTK GPS are the foundation that ties imagery to real-world coordinates.

Similarly, crop monitoring projects that use satellite data for area or yield estimation need field survey data for validation — accurately located field boundaries, measured yields, and ground-observed crop conditions that can be used to calibrate and verify the remote sensing analysis.

The best agricultural remote sensing projects combine satellite analysis with rigorous field survey. Neither works as well without the other.

---

*ZeroPoint Geospatial provides drone multispectral mapping, RTK ground control survey, and GIS analysis for agricultural projects in Kenya. [Contact us](/contact) to discuss how remote sensing can support your project.*
