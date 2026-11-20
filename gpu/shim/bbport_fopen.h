// sotc: fopen of a std::filesystem::path on both platforms (Windows: wide path, so folders
// with non-ASCII names work; Linux: the path's own bytes).
#pragma once
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>

inline std::FILE* BbFopen(const std::filesystem::path& path, const char* mode) {
#ifdef _WIN32
    const std::wstring wide_mode(mode, mode + std::strlen(mode));
    return _wfopen(path.c_str(), wide_mode.c_str());
#else
    return std::fopen(path.c_str(), mode);
#endif
}
