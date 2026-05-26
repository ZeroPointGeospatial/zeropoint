---
layout: post
title: "Why Your Map Coordinates Might Be Wrong (And How to Fix It)"
date: 2026-05-12
---

# Why Your Map Coordinates Might Be Wrong (And How to Fix It)

Here is a situation that happens more often than it should:

A client receives a GIS shapefile from one consultant. They bring in another consultant who collects new survey data. When both datasets are loaded into the same GIS, the features are 50 metres apart — even though they are supposed to represent the same things.

Nobody did anything obviously wrong. Both datasets have coordinates. Both were collected with proper equipment. But they are in different coordinate systems, and nobody noticed until the data was combined.

This kind of problem costs time, money, and sometimes causes decisions to be made from incorrect data. It is entirely avoidable once you understand what is happening.

---

## The Core Problem: Multiple Ways to Describe the Same Point

The earth is not a flat surface and it is not a perfect sphere. It is an irregular oblate spheroid — slightly flattened at the poles, with mountains, valleys, and a gravitational field that varies from place to place.

To assign coordinates to points on this surface, we need to:

1. Define a mathematical model of the earth (a **datum** or **ellipsoid**)
2. Define a method of projecting the curved surface onto a flat plane (a **projection**)
3. Agree on a reference point and orientation for the coordinate system

Different countries, different time periods, and different applications have made different choices about all three of these. The result is dozens of coordinate systems in common use — and data that looks correct but does not align when combined.

---

## Geographic vs Projected Coordinates

The first distinction to understand is between geographic and projected coordinates.

**Geographic coordinates** (latitude and longitude) describe position on the curved surface of the earth. Latitude runs from -90° (South Pole) to +90° (North Pole). Longitude runs from -180° to +180° from the Prime Meridian at Greenwich.

Geographic coordinates are universal and intuitive, but they have a problem: degrees are not a fixed unit of distance. One degree of latitude is about 111km anywhere on earth. But one degree of longitude at the equator is 111km, at 30° latitude it is 96km, and at 60° latitude it is only 56km. You cannot measure distances or areas directly from geographic coordinates without trigonometry.

**Projected coordinates** are geographic coordinates mathematically transformed onto a flat plane. The result is coordinates in metres (or feet) that you can use directly for distance and area calculations.

Every projection distorts something — shape, area, distance, or direction — because you cannot flatten a sphere without distortion. Different projections are optimised for different purposes and different parts of the world.

---

## The Datums You Will Encounter in Kenya

### WGS84

World Geodetic System 1984. This is the global standard — the datum used by GPS satellites. When your phone or GPS receiver gives you coordinates, they are in WGS84.

WGS84 is what you should use for most modern GIS work. It is globally consistent and compatible with satellite data sources.

### Arc 1960

This is the legacy datum used for historical survey work in East Africa, including most Survey of Kenya mapping from the mid-20th century. If you are working with old cadastral maps, government title deed coordinates, or data from surveys done before the widespread adoption of GPS, the coordinates are likely in Arc 1960.

**The shift between Arc 1960 and WGS84 in Kenya is approximately 120–170 metres depending on location.** This is the source of many data alignment problems. When someone loads old cadastral data next to GPS-collected data without performing a datum transformation, the features are in the wrong place by roughly this amount.

### EPSG Codes

Every coordinate system has an EPSG code — a number assigned by the European Petroleum Survey Group that uniquely identifies it. When working with GIS data, always record and communicate the EPSG code.

Common codes you will encounter in Kenya:

| Coordinate System | EPSG Code |
|-------------------|-----------|
| WGS84 Geographic | 4326 |
| WGS84 / UTM Zone 37S | 32737 |
| WGS84 / UTM Zone 36S | 32736 |
| Arc 1960 / UTM Zone 37S | 21037 |
| Arc 1960 Geographic | 4210 |

Most of Kenya falls in UTM Zone 37S. The western parts of the country (west of 36°E longitude) fall in Zone 36S.

---

## Projection Choice for Kenyan Projects

For most survey and GIS work in Kenya, the appropriate projection is **WGS84 / UTM Zone 37S (EPSG:32737)**.

This gives you:
- Coordinates in metres, suitable for distance and area calculation
- Coverage of the majority of Kenya
- Compatibility with GPS data
- Support in all major GIS software

For projects in western Kenya, use Zone 36S. For continental or regional-scale analysis, consider using an equal-area projection like Africa Albers Equal Area Conic.

---

## How to Check What Coordinate System Your Data Is In

In QGIS:
- Right-click the layer → Properties → Information tab
- Look for the CRS (Coordinate Reference System) field
- It will show the EPSG code and a description

If your data has no CRS defined, you will need to investigate. Check:
- The metadata or accompanying documentation
- The coordinate values themselves (geographic coordinates are small numbers, -90 to 90 and -180 to 180; projected coordinates in Kenya will be large numbers around 200,000–900,000 easting and 9,000,000–10,500,000 northing for UTM)

---

## Transforming Between Coordinate Systems

Most GIS software can transform data between coordinate systems. In QGIS, use Vector → Data Management Tools → Reproject Layer.

**Important:** Always transform to a standard system rather than mixing systems in the same project. Define your project CRS at the start and ensure all data is transformed to it before use.

When transforming from Arc 1960 to WGS84, use a proper grid shift file if available. QGIS uses the PROJ library for transformations, and the quality of the transformation depends on the transformation parameters used. For critical work, verify that transformed coordinates match field-surveyed WGS84 coordinates.

---

## The Practical Checklist

Before starting any GIS or survey project:

- [ ] Define the coordinate system the project will use (recommend WGS84 UTM 37S for Kenya)
- [ ] Confirm the coordinate system of all incoming data
- [ ] Transform any data not in the project CRS before use
- [ ] Document the CRS in all deliverables and metadata
- [ ] If receiving data from a third party, ask for the EPSG code explicitly

This takes five minutes at the start of a project. Not doing it can cost days of rework.

---

## When to Call a Surveyor

If you are working with legal documents — title deeds, survey plans, subdivision applications — coordinate system questions have legal implications. Survey plans filed with the Survey of Kenya must use the prescribed coordinate systems and datum transformations. Getting this wrong does not just produce misaligned maps. It can invalidate a survey or create boundary disputes.

For any work involving official land documents, work with a licensed surveyor who understands both the technical and regulatory requirements.

---

*ZeroPoint Geospatial delivers all survey data in clearly documented coordinate systems, with datum transformation performed where required. We provide data in your preferred format and CRS. [Contact us](/contact) for survey and GIS services.*
