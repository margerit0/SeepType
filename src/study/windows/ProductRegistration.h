#pragma once
#include <windows.h>

namespace study {
HRESULT RegisterProductModule(HMODULE module);
HRESULT UnregisterProductModule(HMODULE module);
}
