from __future__ import annotations

import export_model_3d as model3d


def test_view_presets_keep_orientation_badge_in_sync() -> None:
    html = model3d.render_html({"compare": {}}, "window.THREE = {};")

    assert 'document.getElementById("compass").innerHTML = kind === "plan"' in html
    assert "<span><b>俯視</b><br />對 HTML 格位</span>" in html
    assert "<span><b>正面</b><br />朝相機；北向推定</span>" in html
