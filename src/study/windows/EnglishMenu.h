#pragma once

#include <windows.h>
#include "../SessionActions.h"

namespace study {

constexpr UINT kInputEnglish = 1;
HMENU CreateEnglishMenu(const EnglishTarget& target);
UINT ShowEnglishMenu(HWND owner, POINT position, const EnglishTarget& target);

}  // namespace study
