from __future__ import annotations

from pathlib import Path
from typing import Any

from house_design.contracts import ContractError


def write_meeting_pdf(report: dict[str, Any], output: Path) -> Path:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import (
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise ContractError("reportlab is required for the meeting PDF; install requirements.txt") from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    font_name = "MSung-Light"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    except Exception as exc:
        raise ContractError(f"Unable to register Traditional Chinese PDF font: {exc}") from exc

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "HouseTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=20,
        leading=28,
        textColor=colors.HexColor("#102a43"),
        alignment=TA_LEFT,
        spaceAfter=6 * mm,
    )
    heading_style = ParagraphStyle(
        "HouseHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#102a43"),
        spaceBefore=4 * mm,
        spaceAfter=2.5 * mm,
    )
    body_style = ParagraphStyle(
        "HouseBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9,
        leading=14,
        textColor=colors.HexColor("#29445d"),
    )
    small_style = ParagraphStyle(
        "HouseSmall",
        parent=body_style,
        fontSize=7.5,
        leading=11,
        textColor=colors.HexColor("#66788a"),
    )

    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"住宅設計檢核報告 {report['revision']['revision_id']}",
        author="house-design review workflow",
    )
    story: list[Any] = []
    revision = report["revision"]
    predesign = report.get("predesign") or {}
    story.append(Paragraph(f"住宅設計檢核報告 · {revision['revision_id']} {revision.get('label') or ''}", title_style))
    conclusion = "可進入專業放行" if report["release"]["eligible"] else "不可宣稱整體合規"
    summary_data = [
        ["基地資料完成度", f"{report['readiness']['percent']}%", "結論", conclusion],
        [
            "前期到期完成度",
            f"{predesign.get('readiness', {}).get('percent', 0)}%",
            "前期硬阻擋",
            str(predesign.get("gate", {}).get("active_blockers", 0)),
        ],
        ["已確認需求", str(report["requirements_summary"]["confirmed"]), "待確認需求", str(report["requirements_summary"]["candidate"])],
        ["報告雜湊", Paragraph(report["report_hash"], small_style), "版次狀態", str(revision.get("status") or "")],
    ]
    summary = Table(summary_data, colWidths=[30 * mm, 55 * mm, 28 * mm, 67 * mm])
    summary.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#29445d")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f7")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eef3f7")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bdcbd6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([summary, Spacer(1, 5 * mm), Paragraph("狀態摘要", heading_style)])
    labels = {
        "fail": "失敗",
        "warning": "警告",
        "unknown": "未知",
        "professional_review": "專業確認",
        "pass": "通過",
        "not_applicable": "不適用",
    }
    counts = [[labels[key], str(report["status_counts"].get(key, 0))] for key in labels]
    count_table = Table(counts, colWidths=[50 * mm, 20 * mm], hAlign="LEFT")
    count_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d6e0e8")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f7f9fb")),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([count_table, PageBreak(), Paragraph("檢核事項", title_style)])

    for index, finding in enumerate(report["findings"], start=1):
        applies = finding.get("applies_to") or {}
        location = "／".join(
            str(applies[key]) for key in ("building_id", "floor_id") if applies.get(key)
        ) or "全專案"
        block = [
            Paragraph(f"{index}. [{finding['status_label']}] {finding['title']}", heading_style),
            Paragraph(f"編號：{finding['finding_id']}　位置：{location}　負責：{finding['responsible_role']}", small_style),
            Paragraph(f"說明：{finding['message']}", body_style),
            Paragraph(f"下一步：{finding['next_action']}", body_style),
            Spacer(1, 2.5 * mm),
        ]
        story.append(KeepTogether(block))

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont(font_name, 7)
        canvas.setFillColor(colors.HexColor("#66788a"))
        canvas.drawString(15 * mm, 8 * mm, f"{revision['revision_id']} · {report['report_hash'][:16]}")
        canvas.drawRightString(195 * mm, 8 * mm, f"第 {doc.page} 頁")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output
