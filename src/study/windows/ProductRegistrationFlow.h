#pragma once
#include <windows.h>
#include <cstddef>

namespace study {
// Operations are supplied by the Windows adapter or an in-memory failure test.
// Keep the owned COM class until every TSF reference has been removed, so an
// interrupted cleanup can be retried against the same verified module owner.
template <class Operations>
HRESULT RemoveOwnedRegistration(Operations& operations) {
  HRESULT firstFailure = S_OK;
  for (std::size_t index = 0; index < operations.CategoryCount(); ++index) {
    const HRESULT result = operations.RemoveCategory(index);
    if (FAILED(result) && SUCCEEDED(firstFailure)) firstFailure = result;
  }
  if (FAILED(firstFailure)) return firstFailure;
  const HRESULT result = operations.RemoveProfile();
  if (FAILED(result)) return result;
  return operations.DeleteClass();
}

template <class Operations>
HRESULT AddOwnedRegistration(Operations& operations) {
  bool created = false;
  HRESULT result = operations.CreateClass(created);
  if (FAILED(result)) {
    if (created) {
      const HRESULT cleanup = operations.DeleteClass();
      if (FAILED(cleanup)) return cleanup;
    }
    return result;
  }
  result = operations.AddProfile();
  if (SUCCEEDED(result)) {
    for (std::size_t index = 0; index < operations.CategoryCount(); ++index) {
      result = operations.AddCategory(index);
      if (FAILED(result)) break;
    }
  }
  if (FAILED(result)) {
    // An API can fail after making a partial change. Removal checks presence
    // and includes the operation that failed, not only earlier successes.
    const HRESULT cleanup = RemoveOwnedRegistration(operations);
    if (FAILED(cleanup)) return cleanup;
  }
  return result;
}
}
