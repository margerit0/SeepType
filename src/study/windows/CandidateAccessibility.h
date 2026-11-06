#pragma once
#include <windows.h>
#include <oleacc.h>
#include <memory>
#include <functional>

namespace study {
class CandidateUi;
struct CandidateAccessBinding { CandidateUi* view = nullptr; };
// Simple MSAA children reflect only the current page. A retained accessibility
// object cannot reach a destroyed/recreated view; its DLL reference is explicit.
IAccessible* CreateCandidateAccessible(HWND window, std::shared_ptr<CandidateAccessBinding> binding,
    std::function<void(bool)> lifetime);
}
