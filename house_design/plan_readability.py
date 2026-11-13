"""Visible legends for static plan copies; original drawing geometry stays intact."""
from __future__ import annotations

import re
import textwrap
from xml.etree import ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"


def legend_entries(root):
    entries = []
    for node in root.iter():
        if node.get("data-furniture-id"):
            title = node.find(NS+"title")
            if title is not None and title.text:
                entries.append(title.text)
        elif node.get("data-hvac-label-id"):
            kind = "冷氣室內機" if node.get("data-hvac-label-type") == "indoor" else "冷氣室外機"
            entries.append(node.get("data-hvac-label-id")+"｜"+kind+"（機型待定）")
    return list(dict.fromkeys(entries))


def readable_svg(data):
    """Append a visible footer outside the old viewBox; no hover is required."""
    root = ET.fromstring(data)
    entries = legend_entries(root)
    if not entries:
        return data, []
    x, y, width, height = map(float, root.get("viewBox").split())
    font = width/43
    line_height = font*1.55
    lines = ["圖例｜編號、中文名稱與代表尺寸（未選品／非實測）"]
    lines += [line for value in entries for line in textwrap.wrap(value, width=38, drop_whitespace=False, replace_whitespace=False)]
    extra = line_height*(len(lines)+2)
    root.set("data-original-viewbox", root.get("viewBox"))
    root.set("viewBox", f"{x:g} {y:g} {width:g} {height+extra:g}")
    if root.get("height") and re.fullmatch(r"[0-9.]+", root.get("height")):
        root.set("height", f"{float(root.get('height'))*(height+extra)/height:g}")
    group = ET.SubElement(root, NS+"g", {"data-visible-equipment-legend": "1"})
    ET.SubElement(group, NS+"rect", {"x":str(x), "y":str(y+height), "width":str(width),
        "height":str(extra), "fill":"#fafbf8", "stroke":"#78978b", "stroke-width":str(font/12)})
    for index, value in enumerate(lines):
        el = ET.SubElement(group, NS+"text", {"x":str(x+font), "y":str(y+height+(index+1.5)*line_height),
            "style":f"font:{font:g}px system-ui,sans-serif;fill:#263e49"})
        el.text = value
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)+b"\n", entries
