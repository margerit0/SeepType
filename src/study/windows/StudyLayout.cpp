#include "stdafx.h"
#include "StudyLayout.h"
#include <algorithm>
#include <cmath>

namespace study {
void StudyLayout::DoLayout(CDCHandle, weasel::PDWR resources) {
  const float scale = resources->dpiScaleLayout;
  auto px = [&](double dip) { return static_cast<int>(std::lround(dip * scale)); };
  const int count = (std::min)(candidates_count, weasel::MAX_CANDIDATES_COUNT);
  const double add = large_ ? 2 : 0;
  const int height = px(30 + add + (17 + add) * learning_);
  const int textTop = px(7 + (17 + add) * learning_);
  int x = px(4 - scrollDip_);
  for (int i = 0; i < count; ++i) {
    CSize measured{};
    GetTextSizeDW(candidates[i].str, candidates[i].str.size(), resources->pTextFormat, resources, &measured);
    const int width = (std::max)(px(96), static_cast<int>(measured.cx) + px(32));
    _candidateRects[i].SetRect(x, px(4), x + width, px(4) + height);
    _candidateLabelRects[i].SetRect(x + px(7), textTop, x + px(20), textTop + px(24 + add));
    _candidateTextRects[i].SetRect(x + px(25), textTop, x + width - px(7), textTop + px(24 + add));
    _candidateCommentRects[i].SetRect(x + px(25), px(7), x + width - px(7), px(7 + (16 + add) * learning_));
    x += width + (i + 1 < count ? px(2) : 0);
  }
  naturalWidthDip = count ? (x - px(4 - scrollDip_)) / scale : 0;
  const double viewportWidth = viewportDip_ > 0 ? viewportDip_ : naturalWidthDip;
  const int barHeight = height + px(8);
  viewport.SetRect(px(4), px(4), px(4 + viewportWidth), barHeight - px(4));
  for (int i = 0; i < 4; ++i) {
    const int left = px(4 + viewportWidth + 8 + i * 24);
    const int top = (barHeight - px(30)) / 2;
    tools[i].SetRect(left, top, left + px(24), top + px(30));
  }
  _contentSize.SetSize(px(viewportWidth + 112), barHeight);
  _contentRect.SetRect(0, 0, _contentSize.cx, _contentSize.cy);
  _bgRect = _contentRect;
  _highlightRect = count ? _candidateRects[(std::clamp)(id, 0, count - 1)] : CRect(0, 0, 0, 0);
  _preeditRect.SetRectEmpty(); _auxiliaryRect.SetRectEmpty(); _statusIconRect.SetRectEmpty();
  _prePageRect = tools[0]; _nextPageRect = tools[1];
}
int StudyLayout::Hit(POINT point) const {
  for (int i = 0; i < 4; ++i) if (tools[i].PtInRect(point)) return Previous - i;
  if (viewport.PtInRect(point)) {
    for (int i = 0; i < candidates_count && i < weasel::MAX_CANDIDATES_COUNT; ++i)
      if (_candidateRects[i].PtInRect(point)) return i;
  }
  return None;
}
}
