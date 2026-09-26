from __future__ import annotations

from xml.etree import ElementTree as ET

from backend.schemas import BreakSlot

VMAP_NAMESPACE = "http://www.iab.net/videosuite/vmap"
VAST_NAMESPACE = "http://www.iab.com/VAST"
ET.register_namespace("vmap", VMAP_NAMESPACE)


def format_time_offset(seconds: float) -> str:
    total_milliseconds = round(seconds * 1000)
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}.{milliseconds:03}"


def _absolute_url(value: str, base_url: str) -> str:
    if value.startswith("https://"):
        return value
    return f"{base_url.rstrip('/')}/{value.lstrip('/')}"


def build_vmap(
    job_id: str,
    breaks: list[BreakSlot],
    base_url: str,
) -> str:
    root = ET.Element(f"{{{VMAP_NAMESPACE}}}VMAP", {"version": "1.0"})
    for slot in breaks:
        ad_break = ET.SubElement(
            root,
            f"{{{VMAP_NAMESPACE}}}AdBreak",
            {
                "timeOffset": slot.time_offset,
                "breakType": "linear",
                "breakId": slot.id,
            },
        )
        ad_source = ET.SubElement(
            ad_break,
            f"{{{VMAP_NAMESPACE}}}AdSource",
            {
                "id": f"source-{slot.id}",
                "allowMultipleAds": "false",
                "followRedirects": "true",
            },
        )
        vast_data = ET.SubElement(ad_source, f"{{{VMAP_NAMESPACE}}}VASTAdData")
        vast = ET.SubElement(vast_data, "VAST", {"version": "4.2"})
        ad = ET.SubElement(vast, "Ad", {"id": f"ad-{slot.id}", "adType": "audioVideo"})
        inline = ET.SubElement(ad, "InLine")
        ET.SubElement(inline, "AdSystem", {"version": "1.0"}).text = "Chhondo"
        ET.SubElement(inline, "AdTitle").text = slot.brand.name
        ET.SubElement(inline, "Impression", {"id": "served"}).text = _absolute_url(
            f"/api/impressions/{job_id}/{slot.id}", base_url
        )
        creatives = ET.SubElement(inline, "Creatives")
        creative = ET.SubElement(creatives, "Creative", {"id": f"creative-{slot.id}"})
        linear = ET.SubElement(creative, "Linear")
        ET.SubElement(linear, "Duration").text = format_time_offset(slot.duration)
        media_files = ET.SubElement(linear, "MediaFiles")
        media_file = ET.SubElement(
            media_files,
            "MediaFile",
            {
                "delivery": "progressive",
                "type": "video/mp4",
                "width": "960",
                "height": "540",
                "scalable": "true",
                "maintainAspectRatio": "true",
            },
        )
        media_file.text = _absolute_url(slot.creative_url, base_url)

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    )
