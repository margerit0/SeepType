"""Apply one explicit spike-only layout hook to the pinned Weasel checkout."""
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
checkout=ROOT/".cache/src/weasel"
path=checkout/"WeaselUI/WeaselPanel.cpp"
original=subprocess.check_output(["git","show","HEAD:WeaselUI/WeaselPanel.cpp"],cwd=checkout).decode("utf-8").replace("\r\n","\n")
modified=original.replace('#include "HorizontalLayout.h"', '#include "HorizontalLayout.h"\n#ifdef WEASEL_STUDY_SPIKE\n#include "StudyLayout.h"\n#endif',1)
old='      layout = new HorizontalLayout(m_style, m_ctx, m_status, pDWR);'
new='#ifdef WEASEL_STUDY_SPIKE\n      layout = new StudyLayout(m_style, m_ctx, m_status, pDWR);\n#else\n'+old+'\n#endif'
assert old in modified
modified=modified.replace(old,new,1)
layer='void WeaselPanel::_LayerUpdate(const CRect& rc, CDCHandle dc) {'
assert layer in modified
modified=modified.replace(layer,layer+'\n#ifdef WEASEL_STUDY_SPIKE\n  weasel::CaptureStudyFrame(dc, rc.Width(), rc.Height());\n#endif',1)
current=path.read_text(encoding="utf-8")
previous=modified.replace(layer+'\n#ifdef WEASEL_STUDY_SPIKE\n  weasel::CaptureStudyFrame(dc, rc.Width(), rc.Height());\n#endif',layer,1)
if current not in (original,previous,modified):
    raise RuntimeError("Unexpected local changes in cached WeaselPanel.cpp; refusing overwrite")
path.write_text(modified,encoding="utf-8")
(HERE/"patches").mkdir(exist_ok=True)
diff=subprocess.check_output(["git","diff","--","WeaselUI/WeaselPanel.cpp"],cwd=checkout)
(HERE/"patches/weasel-ui-spike.patch").write_bytes(diff)
print("Pinned WeaselPanel: guarded layout selection and own-frame test observer")
