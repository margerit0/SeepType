#pragma once
#include <windows.h>
#include <filesystem>
#include <string>

namespace study {
std::filesystem::path ProductRoot();
std::filesystem::path ProductUserRoot();
std::wstring ProductUserSid();
std::wstring ProductInstanceSuffix();
std::wstring ProductPipeName();
std::wstring ProductStopEvent();
std::wstring ProductMutexName();
bool ProductPipeServerMatchesUser(HANDLE pipe);
bool EnsureProductService();
void PrepareProductUserData();
}
