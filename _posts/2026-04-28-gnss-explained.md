---
layout: post
title: "GNSS Explained: Why Your Phone GPS and a Survey GPS Are Not the Same Thing"
date: 2026-04-28
---

# GNSS Explained: Why Your Phone GPS and a Survey GPS Are Not the Same Thing

When people find out what professional survey equipment costs, the first question is usually some version of: *But my phone has GPS. Why can't you just use that?*

It is a fair question. Your phone does have GPS. It does give you coordinates. It can navigate you across Nairobi with reasonable accuracy. So what exactly is the difference — and why does it matter?

The answer starts with understanding what GPS actually is, and what GNSS is, and why those terms are not quite the same.

---

## GPS vs GNSS: The Terminology

**GPS** — Global Positioning System — is the satellite navigation system operated by the United States Department of Defense. It was the first operational global navigation satellite system and remains the most widely used. The term "GPS" is often used generically, the way "Hoover" is used for vacuum cleaners, but technically GPS refers only to the American system.

**GNSS** — Global Navigation Satellite System — is the broader term for all satellite navigation systems. It includes:

- **GPS** (USA) — 31 operational satellites
- **GLONASS** (Russia) — 24 satellites
- **Galileo** (European Union) — 30 satellites
- **BeiDou** (China) — 35+ satellites
- **NavIC** (India) — regional system
- **QZSS** (Japan) — regional system

Professional survey receivers track signals from multiple constellations simultaneously. A modern RTK receiver might be tracking 30–50 satellites at once from GPS, GLONASS, Galileo, and BeiDou combined. More signals mean better geometry, faster solutions, and more reliable positioning.

Your phone also tracks multiple constellations on modern chipsets — but the similarities largely end there.

---

## How Satellite Navigation Actually Works

Every GNSS satellite broadcasts a signal that contains:

1. The satellite's precise location at the time of transmission
2. A timestamp from an extremely accurate atomic clock

Your receiver picks up signals from multiple satellites simultaneously. By measuring how long each signal took to arrive — and therefore how far away each satellite is — it can calculate your position through trilateration.

The basic principle is simple. The precision of the execution is extraordinarily complex.

### The Sources of Error

Raw GNSS signals are affected by multiple error sources:

**Atmospheric delays** — signals slow down as they pass through the ionosphere and troposphere. The delay varies with atmospheric conditions and satellite elevation angle.

**Multipath** — signals bounce off buildings, vehicles, and terrain before reaching the antenna. The bounced signal arrives slightly later than the direct signal, corrupting the measurement.

**Satellite geometry** — if all visible satellites are clustered in one part of the sky, position geometry is poor. PDOP (Position Dilution of Precision) quantifies this — lower is better.

**Satellite clock errors** — despite atomic clocks, tiny timing errors accumulate.

**Ephemeris errors** — the satellite's broadcast position is not perfectly accurate.

**Receiver noise** — electronic noise in the receiver itself introduces measurement error.

Each of these errors contributes to the total position uncertainty. An uncorrected GPS receiver — like the one in a basic phone — has all of these errors acting together. The result is typical horizontal accuracy of 3–5 metres under good conditions, worse in urban canyons or under tree cover.

---

## How RTK Gets to Centimetre Accuracy

RTK — Real-Time Kinematic — is the technique that takes GNSS from metre-level to centimetre-level accuracy. It does this through a fundamental insight: **most GNSS errors affect all receivers in the same area equally**.

If a base station with a precisely known position is set up near the work area, it can calculate the error in its GNSS measurement at any moment (since it knows exactly where it is). That error correction is broadcast in real time to a rover receiver in the field. The rover applies the correction and eliminates most of the common-mode error — leaving only the measurement of the rover's position relative to the base.

This differential technique reduces horizontal error from metres to 1–3 centimetres.

There is an additional level of precision available from phase measurements. GNSS signals are carrier waves. Standard positioning uses the signal's code — the timing information. RTK receivers also measure the phase of the carrier wave itself, which has a much shorter wavelength (GPS L1 carrier: ~19cm) and therefore much finer resolution.

Resolving carrier phase ambiguity — figuring out how many full wavelengths separate the satellite from the receiver — is the mathematical challenge at the heart of RTK. Once solved (called "fixing the ambiguity"), the measurement precision is at the millimetre level, and real-world accuracy reaches 1–3cm.

### CORS Networks

Traditionally, RTK required a physical base station in the field. Increasingly, networks of Continuously Operating Reference Stations (CORS) broadcast corrections over mobile data, allowing rovers to achieve RTK accuracy without a local base.

In Kenya, CORS infrastructure is being developed by the Survey of Kenya and various private providers. Coverage is expanding, particularly around major urban centres, and will make RTK survey more accessible over time.

---

## Phone GPS: What It Is and Is Not Doing

Modern smartphones — particularly since Android 7 and iPhone 14 — support dual-frequency GNSS (L1 + L5 on GPS, equivalent on other constellations). Dual frequency helps the receiver model and remove ionospheric delay, significantly improving raw accuracy.

Under ideal conditions, a high-end smartphone with dual-frequency GNSS can achieve horizontal accuracy of 1–2 metres. That is a significant improvement over older single-frequency phones.

But there are fundamental limitations that do not go away with better chipsets:

**Antenna quality** — a professional survey antenna is a precision instrument, designed and calibrated to minimise multipath and have a precisely known phase centre. A phone antenna is a small patch embedded in a device designed primarily for communication. The difference in signal quality is significant.

**No RTK corrections** — standard phone GNSS does not receive RTK correction data. Some specialised apps and accessories enable this, but not by default.

**Multipath environment** — phones are used in hands, pockets, and cars — environments with severe multipath from nearby reflective surfaces.

**Processing** — phone GNSS chipsets are optimised for navigation, not survey. The filtering and averaging that makes navigation smooth degrades the precision of individual measurements.

For navigation, this is all fine. For survey work requiring centimetre accuracy, it is not.

---

## When Phone GPS Is Enough

Not every geospatial application requires centimetre accuracy. Phone GPS is perfectly adequate for:

- Field data collection where 3–5 metre accuracy is acceptable
- Geotagging photographs for approximate location reference
- Reconnaissance and route planning
- Collecting approximate locations of features for GIS inventory work
- Confirming that you are on the right parcel before starting detailed survey

Apps like Collector for ArcGIS, QGIS for Android, and ODK (Open Data Kit) allow structured field data collection with GPS coordinates from a phone. For community mapping, basic asset inventory, and reconnaissance, this is valuable and cost-effective.

The key is knowing the accuracy of what you are collecting and being honest about whether it is sufficient for the intended use.

---

## A Practical Summary

| | Phone GPS | RTK GNSS Survey |
|---|---|---|
| Typical accuracy | 3–5m (good conditions) | 1–3cm |
| Cost | Included in phone | KES 500,000–2,000,000+ |
| Setup time | Instant | 5–30 minutes |
| Legal validity | No | Yes (licensed surveyor) |
| Best for | Navigation, reconnaissance | Boundaries, control, setting out |

The tools serve different purposes. A professional surveyor using an RTK receiver is not doing something a phone user could do with better software — they are making fundamentally different measurements with fundamentally different instruments, to a fundamentally different standard of accuracy and accountability.

That accuracy matters whenever the coordinates will be used to make decisions about land, infrastructure, or resources. And in those cases, the difference between 5 metres and 2 centimetres is not academic. It is the difference between a boundary in the right place and one that crosses into your neighbour's land.

---

*ZeroPoint Geospatial uses multi-constellation RTK GNSS equipment for all survey work, delivering centimetre-accurate positioning tied to the national coordinate framework. [Get in touch](/contact) for a quote on your project.*
