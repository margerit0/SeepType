#include "stdafx.h"
#include "StudyLayout.h"

namespace weasel {
void StudyLayout::DoLayout(CDCHandle dc, PDWR resources) {
  const float scale=resources->dpiScaleLayout;
  auto px=[&](int value){return (int)std::round(value*scale);};
  const bool learning=cmtFontValid && (_style.comment_text_color & 0xff000000);
  const int top=offsetY+real_margin_y;
  int x=offsetX+real_margin_x;
  const int cellHeight=px(learning?47:30);
  const int textTop=top+px(learning?20:3);
  _preeditRect.SetRectEmpty();_auxiliaryRect.SetRectEmpty();_statusIconRect.SetRectEmpty();
  _prePageRect.SetRectEmpty();_nextPageRect.SetRectEmpty();
  if(resources->pCommentTextFormat) {
    DWRITE_TRIMMING trimming={DWRITE_TRIMMING_GRANULARITY_CHARACTER,0,0};
    ComPtr<IDWriteInlineObject> ellipsis;
    resources->pDWFactory->CreateEllipsisTrimmingSign(resources->pCommentTextFormat.Get(),&ellipsis);
    resources->pCommentTextFormat->SetWordWrapping(DWRITE_WORD_WRAPPING_NO_WRAP);
    resources->pCommentTextFormat->SetTrimming(&trimming,ellipsis.Get());
  }
  const int count=min(candidates_count,MAX_CANDIDATES_COUNT);
  for(int i=0;i<count;++i) {
    CSize textSize;
    GetTextSizeDW(candidates[i].str,candidates[i].str.size(),resources->pTextFormat,resources,&textSize);
    const int cellWidth=max(px(96),textSize.cx+px(32));
    _candidateRects[i].SetRect(x,top,x+cellWidth,top+cellHeight);
    _candidateLabelRects[i].SetRect(x+px(7),textTop,x+px(19),textTop+px(24));
    _candidateTextRects[i].SetRect(x+px(25),textTop,x+cellWidth-px(7),textTop+px(24));
    _candidateCommentRects[i].SetRect(x+px(25),top+px(3),x+cellWidth-px(7),top+px(learning?19:3));
    x+=cellWidth+(i+1<count?_style.candidate_spacing:0);
  }
  _contentSize.SetSize(max(x+real_margin_x+offsetX,_style.min_width),cellHeight+2*(real_margin_y+offsetY));
  _contentRect.SetRect(0,0,_contentSize.cx,_contentSize.cy);
  _highlightRect=count?_candidateRects[min(max(id,0),count-1)]:CRect(0,0,0,0);
  _bgRect=_contentRect;_bgRect.DeflateRect(offsetX+1,offsetY+1);
  if(count)_PrepareRoundInfo(dc);
  _contentRect.DeflateRect(offsetX,offsetY);
}
}
